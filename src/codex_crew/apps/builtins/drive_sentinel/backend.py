#!/usr/bin/env python3
"""Drive Sentinel - live local-volume manager with measured cloud roots.

Three faces over ONE engine (the Index class), so the GUI, the CLI and an
agent all see identical numbers:

  GUI   Codex Crew app proxy        -> authenticated local dashboard
  CLI   python warden.py <command>  -> plain text or --json for machines
  API   the same HTTP routes the GUI uses, listed below

Stdlib only (no pip installs on a disk this full). Binds to 127.0.0.1 only.

CLI commands
  serve                     run the web GUI + API (default when no command)
  status                    drive free/used + index freshness, one line
  scan [root]               index synchronously and print the top folders
  tree <path> [-n N]        biggest children of a folder
  top [-n N]                biggest individual files on disk
  targets                   every reclaim candidate with size + risk
  dehydrate [-n N] [--apply]  ZERO-LOSS reclaim: biggest OneDrive folders still
                            holding local bytes. Plan by default; --apply frees
                            them (reversible with `keep`).
  sweep [--min-free-gb N]   purge every SAFE target; no-op if already above N
  log [-n N]                every action this tool took, newest first
  undo <id>                 reverse a logged action (dehydrations only; a
                            purge removed bytes and says so instead)
  free <path>               dehydrate a OneDrive path (frees local bytes)
  keep <path>               rehydrate a OneDrive path (downloads, keeps local)
  Add --json to any command for machine-readable output.

HTTP API (GET unless noted)
  /api/drive     live free/total/used bytes + the OneDrive roots
  /api/volumes   attached fixed/removable volumes + current indexed root
  /api/cloud     measured OneDrive and Google Drive providers and roots
  /api/status    index progress: scanning, files, dirs, elapsed, done_at
  /api/tree?path= one folder's children with on-disk / cloud-only split
  /api/top       biggest individual files
  /api/ext       size grouped by file extension
  /api/targets   reclaim candidates, each with a server-issued purge id
  /api/dehydrate zero-loss reclaim list: OneDrive folders holding local bytes
  /api/log       every action taken, with its reverse recorded on each entry
  POST /api/undo   {"id": N}   replay a logged entry's recorded reverse

RECLAIM ORDER - dehydrate first, delete last:
  1. DEHYDRATE (/api/pin mode=free) - reversible, keeps the data in OneDrive.
     Always the first move. Success is judged by FREE SPACE, not attributes.
  2. PURGE a safe target - regenerates itself, but the bytes really go.
  3. review / danger tiers - only on an explicit instruction.

Every byte-changing action is appended to activity.jsonl BEFORE the caller is
told it worked, each entry carrying the exact call that reverses it - or a null
reverse plus a recovery note when the bytes are physically gone.
  POST /api/scan   {"root": "D:\\\\"}          index one attached volume
  POST /api/pin    {"path": ..., "mode": "free"|"pin"}   OneDrive dehydrate/rehydrate
  POST /api/purge  {"id": "<id from /api/targets>"}      empty one target

Safety model - everything is read-only except two guarded write routes:
  /api/pin    REFUSED outside a OneDrive root, so it can never alter the
              pin state of ordinary local files.
  /api/purge  takes a SERVER-ISSUED id, never a client path, so a caller
              cannot name its own victim; report-only targets refuse outright
              and in-use files are skipped rather than forced.

Freshness: after the operator explicitly starts the first scan, the index
self-refreshes every REFRESH_MIN minutes (default 15). No drive is scanned just
because Codex Crew starts. The free-space gauge remains a live syscall.
"""

import ctypes
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from codex_crew.apps.proxy_auth import verify_proxy_request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", os.environ.get("DRIVE_SENTINEL_PORT", "7894")))
DRIVE = os.environ.get("DRIVE_SENTINEL_DRIVE", "C:\\")
# How often the server re-indexes on its own. The point of the tool is
# immediate shedding, so an index older than this is treated as untrustworthy.
REFRESH_MIN = float(os.environ.get("DRIVE_SENTINEL_REFRESH_MIN", "15"))
# `sweep` does nothing while free space is already above this. Keeps a
# scheduled sweep from deleting caches for no reason.
SWEEP_MIN_FREE_GB = float(os.environ.get("DRIVE_SENTINEL_MIN_FREE_GB", "25"))

# --- Windows file attributes we care about -------------------------------
A_REPARSE = 0x00000400  # SOME kind of reparse point - see SKIP_TAGS
A_OFFLINE = 0x00001000
A_RECALL_OPEN = 0x00040000  # cloud placeholder (may or may not be local)
A_PINNED = 0x00080000  # "Always keep on this device"
A_UNPINNED = 0x00100000  # "Free up space" requested
A_RECALL_DATA = 0x00400000  # dehydrated: metadata only, ZERO local bytes

# The reparse ATTRIBUTE BIT alone is not enough to decide what to do, and
# treating it as "skip" was a real bug that hid ~40 GB:
#   - a junction / symlink is a NAME SURROGATE. Descending it double-counts the
#     target and can trap the walk in a cycle, so it is skipped.
#   - a OneDrive folder carries a CLOUD tag (0x9000?01A) and is a REAL
#     directory holding real bytes. `C:\Users\<me>\OneDrive - x` is tag
#     0x9000701A, so skipping every reparse point excluded the ENTIRE OneDrive
#     tree - precisely the tree dehydration targets. It MUST be descended.
# Note os.stat() normalises cloud tags away (it follows them and reports the
# target), while scandir returns the RAW attributes - so only trust the
# DirEntry view here.
TAG_MOUNT_POINT = 0xA0000003
TAG_SYMLINK = 0xA000000C
SKIP_TAGS = (TAG_MOUNT_POINT, TAG_SYMLINK)

# Never walk into these: they churn, are volatile, or are another volume.
SKIP_DIRS = {
    "$recycle.bin",
    "system volume information",
    "$windows.~ws",
    "$windows.~bt",
    "config.msi",
}

# Build/cache directory names worth reclaiming, found for free during the walk.
BUILD_DIRS = {
    "target": "Rust/Cargo build output",
    "node_modules": "npm packages",
    "__pycache__": "Python bytecode",
    ".next": "Next.js build",
    ".gradle": "Gradle cache",
    ".pytest_cache": "pytest cache",
    "build": "build output",
    "dist": "build output",
    ".mypy_cache": "mypy cache",
    ".ruff_cache": "ruff cache",
}


def onedrive_roots():
    roots = []
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            n = os.path.normcase(os.path.abspath(v))
            if n not in roots:
                roots.append(n)
    return roots


ONEDRIVE = onedrive_roots()


def path_in_roots(path, roots):
    """Return true only when path is a root or is contained by one."""
    n = os.path.normcase(os.path.abspath(path))
    return any(
        n == r or n.startswith(r.rstrip("\\") + "\\")
        for r in (os.path.normcase(os.path.abspath(p)) for p in roots)
    )


def _logical_drive_roots():
    """List local Windows drive roots without touching disconnected shares."""
    if os.name != "nt":
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    roots = []
    for i in range(26):
        if not mask & (1 << i):
            continue
        root = "%s:\\" % chr(ord("A") + i)
        # DRIVE_REMOTE can block on a disconnected share. Google Drive for
        # desktop reports a mounted streaming volume through a local drive.
        if ctypes.windll.kernel32.GetDriveTypeW(root) != 4:
            roots.append(root)
    return roots


def _safe_cloud_title(title):
    """Keep account addresses out of API responses and logs."""
    return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "account", title or "")


DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
SUPPORTED_VOLUME_TYPES = {
    DRIVE_REMOVABLE: "removable",
    DRIVE_FIXED: "fixed",
}


def volume_root_for_path(path):
    """Return a normalized drive root for an absolute Windows path."""
    match = re.match(r"^([A-Za-z]):[\\/]", str(path or "").strip())
    return match.group(1).upper() + ":\\" if match else None


def system_volume_root():
    """Return the Windows system volume without accepting a directory path."""
    drive = str(os.environ.get("SystemDrive", "C:")).strip()
    match = re.fullmatch(r"([A-Za-z]):", drive)
    return match.group(1).upper() + ":\\" if match else "C:\\"


def _volume_label(root):
    """Read one local volume label; failure is an ordinary empty label."""
    label = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root), label, len(label), None, None, None, None, 0
    )
    return _safe_cloud_title(label.value).strip() if ok else ""


def mounted_volumes(drive_roots=None, drive_type=None, label_reader=None, space_reader=None):
    """List attached fixed/removable volumes with live capacity readings."""
    roots = _logical_drive_roots() if drive_roots is None else drive_roots
    if not roots:
        return []
    get_type = drive_type or ctypes.windll.kernel32.GetDriveTypeW
    get_label = label_reader or _volume_label
    get_space = space_reader or drive_space
    volumes = []
    for candidate in roots:
        root = volume_root_for_path(candidate)
        if root != str(candidate).replace("/", "\\").upper():
            continue
        kind = SUPPORTED_VOLUME_TYPES.get(get_type(root))
        if not kind:
            continue
        space = get_space(root)
        volumes.append(
            {
                "root": root,
                "label": _safe_cloud_title(get_label(root)).strip(),
                "kind": kind,
                "total": int(space.get("total", 0)),
                "free": int(space.get("free", 0)),
                "used": int(space.get("used", 0)),
            }
        )
    return sorted(volumes, key=lambda volume: volume["root"])


def selectable_volume_root(root, volumes=None):
    """Accept only an exact root present in the current local inventory."""
    normalized = volume_root_for_path(root)
    if normalized != str(root or "").strip().replace("/", "\\").upper():
        return None
    inventory = mounted_volumes() if volumes is None else volumes
    allowed = {str(volume.get("root", "")).upper() for volume in inventory}
    return normalized if normalized in allowed else None


def google_drive_roots(preference_db=None, drive_roots=None):
    """Discover existing Google Drive roots without changing DriveFS state.

    The preference database is an internal Drive for desktop detail, so every
    failure is treated as an empty result. Only path and display fields are
    read; account tokens and metadata blobs never leave the database.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    database = preference_db or os.path.join(
        local, "Google", "DriveFS", "root_preference_sqlite.db"
    )
    found = []
    seen = set()

    def add(path, title, mode, source):
        if not path or not os.path.isdir(path):
            return
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen:
            return
        seen.add(normalized)
        found.append(
            {"path": normalized, "title": _safe_cloud_title(title), "mode": mode, "source": source}
        )

    if os.path.isfile(database):
        try:
            uri = "file:%s?mode=ro" % os.path.abspath(database).replace("\\", "/")
            connection = sqlite3.connect(uri, uri=True)
            try:
                rows = connection.execute(
                    "SELECT title, root_path, last_seen_absolute_path FROM roots"
                )
                for title, root_path, last_seen in rows:
                    current = root_path if os.path.isdir(root_path or "") else last_seen
                    add(
                        current,
                        title or "Google Drive",
                        "configured",
                        "Drive for desktop preferences",
                    )
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            # ponytail: DriveFS owns this schema. If it changes, mounted-volume
            # discovery still works; upgrade only when Google exposes a stable
            # supported discovery API.
            pass

    roots = _logical_drive_roots() if drive_roots is None else drive_roots
    for root in roots:
        if os.path.isdir(os.path.join(root, "My Drive")) or os.path.isdir(
            os.path.join(root, "Shared drives")
        ):
            add(root, "Google Drive", "stream", "mounted volume")
    return found


def in_google_drive(path):
    return path_in_roots(path, [root["path"] for root in google_drive_roots()])


def cloud_provider_for_path(path):
    if path_in_roots(path, ONEDRIVE):
        return "onedrive"
    if in_google_drive(path):
        return "google_drive"
    return None


def drive_space(drive=DRIVE):
    free, total, avail = (ctypes.c_ulonglong() for _ in range(3))
    ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        ctypes.c_wchar_p(drive), ctypes.byref(avail), ctypes.byref(total), ctypes.byref(free)
    )
    if not ok:
        return {"total": 0, "free": 0, "used": 0}
    return {"total": total.value, "free": avail.value, "used": total.value - avail.value}


# What KIND of data a folder holds, and therefore what may be done with it.
# Ordered: first match wins, so put the specific patterns before the generic.
# verdict values: regen (rebuilt automatically) | dehydrate (push to OneDrive)
#                 | rebuild (costs a build/download) | keep (real data)
#                 | admin (needs an elevated tool) | unknown
LABELS = [
    ("target", "build output", "regen"),
    ("node_modules", "package deps", "regen"),
    ("__pycache__", "bytecode", "regen"),
    (".gradle", "build cache", "rebuild"),
    (".m2", "package cache", "rebuild"),
    (".nuget", "package cache", "rebuild"),
    (".cargo", "package cache", "rebuild"),
    (".rustup", "toolchain", "rebuild"),
    ("site-packages", "python env", "rebuild"),
    ("venv", "python env", "regen"),
    (".venv", "python env", "regen"),
    ("cache", "cache", "regen"),
    ("temp", "temp", "regen"),
    ("tmp", "temp", "regen"),
    ("logs", "logs", "regen"),
    ("crashdumps", "crash dumps", "regen"),
    ("winsxs", "component store", "admin"),
    ("installer", "installer cache", "admin"),
    ("windows.old", "old windows", "admin"),
    ("softwaredistribution", "update cache", "regen"),
    ("$recycle.bin", "recycle bin", "regen"),
    ("onedrive", "cloud-synced", "dehydrate"),
]
# Extensions that mark a folder as bulk media / images worth dehydrating
# rather than deleting.
BULK_EXT = {
    ".iso",
    ".vhd",
    ".vhdx",
    ".vmdk",
    ".zip",
    ".7z",
    ".msi",
    ".exe",
    ".mp4",
    ".mov",
    ".mkv",
    ".psd",
    ".bak",
    ".pdb",
}


def classify(path, node=None):
    """Label a folder: what kind of data it holds and what can be done to it.

    Cheap and honest: name-based, plus the cloud/local split the index already
    knows. Returns {"kind", "verdict"}. A folder we cannot recognise is
    reported as unknown rather than guessed into a delete verdict.
    """
    if in_google_drive(path):
        return {"kind": "google drive", "verdict": "keep"}
    low = os.path.normcase(path)
    parts = [p for p in low.split("\\") if p]
    leaf = parts[-1] if parts else low
    for needle, kind, verdict in LABELS:
        if needle == leaf or needle in parts:
            # Inside OneDrive, a regen folder is still better dehydrated than
            # deleted: it costs nothing and is reversible.
            if verdict == "regen" and in_onedrive(path):
                return {"kind": kind, "verdict": "dehydrate"}
            return {"kind": kind, "verdict": verdict}
    if in_onedrive(path):
        return {"kind": "cloud-synced", "verdict": "dehydrate"}
    if node is not None and node.cloud > 0:
        return {"kind": "partly cloud", "verdict": "dehydrate"}
    return {"kind": "user data", "verdict": "keep"}


# --- the index ----------------------------------------------------------
class Node:
    """One directory. Files are aggregated, never stored individually."""

    __slots__ = (
        "name",
        "kids",
        "own_logical",
        "own_disk",
        "own_cloud",
        "own_files",
        "logical",
        "disk",
        "cloud",
        "files",
        "dirs",
        "state",
        "err",
    )

    def __init__(self, name):
        self.name = name
        self.kids = {}
        self.own_logical = self.own_disk = self.own_cloud = self.own_files = 0
        self.logical = self.disk = self.cloud = self.files = self.dirs = 0
        self.state = ""  # "" | "cloud" | "local" | "mixed"
        self.err = 0


class Index:
    def __init__(self):
        self.root = None
        self.root_path = ""
        self.scanning = False
        self.done_at = 0.0
        self.seen_files = 0
        self.seen_bytes = 0
        self.seen_dirs = 0
        self.errors = 0
        self.cur = ""
        self.elapsed = 0.0
        self.top_files = []  # [[disk, logical, path, cloud]]
        self.ext = {}  # ext -> [disk, logical, count]
        self.builds = []  # [[disk, path, kind]]
        self.targets = {}  # id -> {...} the ONLY purgeable set
        self.dehydrate = []  # OneDrive folders still holding local bytes
        # Realpaths of already-walked reparse dirs: stops a cloud/unknown tag
        # from being counted twice or cycling.
        self.seen_links = set()

    # -- scan ------------------------------------------------------------
    def scan(self, root, include_system_targets=None):
        self.__init__()
        self.root_path = os.path.abspath(root)
        if include_system_targets is None:
            include_system_targets = volume_root_for_path(self.root_path) == system_volume_root()
        self.scanning = True
        t0 = time.monotonic()
        try:
            self.root = self._walk(self.root_path)
            self._rollup(self.root)
            self._harvest(include_system_targets=include_system_targets)
        finally:
            self.elapsed = time.monotonic() - t0
            self.scanning = False
            self.done_at = time.time()

    def _walk(self, path):
        """Iterative post-order walk. One Node per directory, files aggregated."""
        root = Node(os.path.basename(path.rstrip("\\/")) or path)
        stack = [(path, root)]
        top = self.top_files
        while stack:
            cur_path, node = stack.pop()
            self.cur = cur_path
            self.seen_dirs += 1
            try:
                it = os.scandir(cur_path)
            except OSError:
                node.err = 1
                self.errors += 1
                continue
            with it:
                while True:
                    try:
                        entry = next(it)
                    except StopIteration:
                        break
                    except OSError:
                        node.err = 1
                        self.errors += 1
                        break
                    try:
                        st = entry.stat(follow_symlinks=False)
                        attrs = st.st_file_attributes
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        node.err = 1
                        self.errors += 1
                        continue
                    # Skip ONLY name surrogates (junctions / symlinks): those
                    # double-count their target and can cycle. A cloud
                    # placeholder folder is a real directory and must be
                    # walked, or the whole OneDrive tree goes missing.
                    if attrs & A_REPARSE:
                        tag = getattr(st, "st_reparse_tag", 0)
                        if tag in SKIP_TAGS:
                            continue
                        if is_dir:
                            # Unknown/cloud tag: walk it, but never twice.
                            # Cheap because reparse dirs are a handful.
                            try:
                                real = os.path.normcase(os.path.realpath(entry.path))
                            except OSError:
                                real = os.path.normcase(entry.path)
                            if real in self.seen_links:
                                continue
                            self.seen_links.add(real)
                    if is_dir:
                        if entry.name.lower() in SKIP_DIRS:
                            continue
                        child = Node(entry.name)
                        node.kids[entry.name] = child
                        stack.append((entry.path, child))
                        continue
                    logical = st.st_size
                    # ponytail: on-disk == logical unless the file is a
                    # dehydrated cloud placeholder (then it is 0). Ignores NTFS
                    # compression and sparse files, which would each need a
                    # per-file GetCompressedFileSizeW call (~1M extra syscalls).
                    # Upgrade path: only do that for files > 64 MB if the
                    # totals ever need to match `dir /a` exactly.
                    cloud = bool(attrs & A_RECALL_DATA)
                    disk = 0 if cloud else logical
                    node.own_logical += logical
                    node.own_disk += disk
                    node.own_files += 1
                    if cloud:
                        node.own_cloud += logical
                    self.seen_files += 1
                    self.seen_bytes += disk
                    ext = os.path.splitext(entry.name)[1].lower()[:12] or "(none)"
                    e = self.ext.get(ext)
                    if e is None:
                        self.ext[ext] = [disk, logical, 1]
                    else:
                        e[0] += disk
                        e[1] += logical
                        e[2] += 1
                    if disk > 20_000_000:
                        top.append([disk, logical, entry.path, cloud])
                        if len(top) > 4000:
                            top.sort(reverse=True)
                            del top[500:]
        return root

    def _rollup(self, root):
        """Post-order totals, iterative so depth cannot blow the stack."""
        order, stack = [], [root]
        while stack:
            n = stack.pop()
            order.append(n)
            stack.extend(n.kids.values())
        for n in reversed(order):
            n.logical, n.disk = n.own_logical, n.own_disk
            n.cloud, n.files = n.own_cloud, n.own_files
            n.dirs = len(n.kids)
            for k in n.kids.values():
                n.logical += k.logical
                n.disk += k.disk
                n.cloud += k.cloud
                n.files += k.files
                n.dirs += k.dirs
            if n.logical == 0:
                n.state = ""
            elif n.cloud >= n.logical:
                n.state = "cloud"
            elif n.cloud > 0:
                n.state = "mixed"
            else:
                n.state = "local"

    def _harvest_dehydrate(self):
        """Rank OneDrive folders by LOCAL bytes - the zero-loss reclaim list.

        Dehydrating keeps the file in OneDrive and drops only the local copy,
        so unlike a delete this is reversible (`keep` pulls it back). Roll-up
        makes 'local' free to compute: local = total on disk (cloud-only files
        already contribute 0).

        Granularity matters more than completeness here. The OneDrive ROOT is
        deliberately never a candidate: "dehydrate all 53 GB of OneDrive" is
        not a decision anyone can safely make. Candidates start one level
        below a root and nested ones are dropped, so the list is a handful of
        real folders and the total never double-counts.
        """
        out = []
        if not self.root or not ONEDRIVE:
            self.dehydrate = []
            return
        MIN = 200_000_000  # below ~200 MB it is not worth a click
        roots = [r.rstrip("\\") + "\\" for r in ONEDRIVE]

        def rel_depth(path):
            """How far below a OneDrive root this path sits, or -1 if outside."""
            n = os.path.normcase(path)
            for r in roots:
                if n.rstrip("\\") + "\\" == r:
                    return 0
                if n.startswith(r):
                    return n[len(r) :].strip("\\").count("\\") + 1
            return -1

        def visit(node, path):
            d = rel_depth(path)
            # Emit the DEEPEST meaningful unit, not the shallowest. Emitting
            # shallow made the whole list collapse to one row ("dehydrate all
            # of OneDrive"), which is not a decision anyone can safely make.
            # So a folder is offered only when no CHILD is big enough to be
            # offered instead, or we have hit the depth cap.
            big_kids = [k for k in node.kids.values() if k.disk >= MIN]
            if d >= 1 and node.disk >= MIN and (not big_kids or d >= 4):
                out.append(
                    {
                        "path": path,
                        "local": node.disk,
                        "logical": node.logical,
                        "cloud": node.cloud,
                        "pct_local": round(node.disk / float(node.logical or 1) * 100, 1),
                        "files": node.files,
                        "depth": d,
                        "kind": classify(path, node),
                    }
                )
                return
            for name, kid in node.kids.items():
                if d < 0 or kid.disk >= MIN:
                    visit(kid, os.path.join(path, name))

        visit(self.root, self.root_path)
        out.sort(key=lambda c: -c["local"])
        # Drop any ANCESTOR of a kept candidate: the children are the offer, and
        # counting a parent too would double-count the same bytes.
        kept = []
        for c in out:
            n = os.path.normcase(c["path"]).rstrip("\\") + "\\"
            if any(
                os.path.normcase(k["path"]).rstrip("\\").startswith(n.rstrip("\\") + "\\")
                for k in out
                if k is not c
            ):
                continue  # something deeper covers these bytes
            kept.append(c)
            if len(kept) >= 40:
                break
        self.dehydrate = kept

    def _harvest(self, include_system_targets=True):
        """Build the purgeable target registry from the index + known caches."""
        self.top_files.sort(reverse=True)
        del self.top_files[300:]

        builds = []

        def visit(node, path):
            for name, kid in node.kids.items():
                p = os.path.join(path, name)
                kind = BUILD_DIRS.get(name.lower())
                if kind and kid.disk > 50_000_000:
                    builds.append([kid.disk, p, kind])
                    continue  # do not descend into a reclaim unit
                visit(kid, p)

        if self.root:
            visit(self.root, self.root_path)
        builds.sort(reverse=True)
        self.builds = builds[:60]
        self._harvest_dehydrate()

        targets = {}
        for i, (disk, path, kind) in enumerate(self.builds):
            targets["build%d" % i] = {
                "id": "build%d" % i,
                "label": os.path.basename(path),
                "path": path,
                "bytes": disk,
                "kind": kind,
                "risk": "review",
                "action": "delete",
                "note": "Regenerated by the next build. Delete only if you are "
                "not mid-build in this project.",
                "automatable": True,
            }
        if include_system_targets:
            for i, t in enumerate(self._cache_targets()):
                t["id"] = "cache%d" % i
                targets[t["id"]] = t
        self.targets = targets

    def _cache_targets(self):
        la = os.environ.get("LOCALAPPDATA", "")
        ra = os.environ.get("APPDATA", "")
        up = os.path.expanduser("~")
        win = os.environ.get("SystemRoot", "C:\\Windows")
        spec = [
            (
                os.path.join(la, "Temp"),
                "User temp",
                "safe",
                "delete",
                "Locked in-use files are skipped automatically.",
                True,
            ),
            (
                os.path.join(win, "Temp"),
                "Windows temp",
                "safe",
                "delete",
                "Some entries need admin; those are skipped.",
                True,
            ),
            (
                os.path.join(win, "SoftwareDistribution", "Download"),
                "Windows Update downloads",
                "safe",
                "delete",
                "Re-downloaded on demand if an update still needs them.",
                True,
            ),
            (
                os.path.join(la, "CrashDumps"),
                "Crash dumps",
                "safe",
                "delete",
                "Only needed if you are debugging a crash right now.",
                True,
            ),
            (
                os.path.join(la, "pip", "cache"),
                "pip wheel cache",
                "safe",
                "delete",
                "Re-downloaded on next pip install.",
                True,
            ),
            (
                os.path.join(la, "npm-cache"),
                "npm cache",
                "safe",
                "delete",
                "Re-downloaded on next npm install.",
                True,
            ),
            (
                os.path.join(ra, "npm-cache"),
                "npm cache (roaming)",
                "safe",
                "delete",
                "Re-downloaded on next npm install.",
                True,
            ),
            (
                os.path.join(up, ".cargo", "registry", "cache"),
                "Cargo download cache",
                "safe",
                "delete",
                "Re-downloaded on next cargo build.",
                True,
            ),
            (
                os.path.join(up, ".cargo", "registry", "src"),
                "Cargo unpacked sources",
                "safe",
                "delete",
                "Re-extracted from the cache on next build.",
                True,
            ),
            (
                os.path.join(la, "Microsoft", "Windows", "INetCache"),
                "Internet cache",
                "safe",
                "delete",
                "Browser/IE cached content.",
                True,
            ),
            (
                os.path.join(la, "Microsoft", "Windows", "Explorer"),
                "Thumbnail cache",
                "safe",
                "delete",
                "Explorer rebuilds it.",
                True,
            ),
            (
                os.path.join(la, "NVIDIA", "DXCache"),
                "NVIDIA shader cache",
                "safe",
                "delete",
                "Rebuilt by the driver.",
                True,
            ),
            (
                os.path.join(la, "D3DSCache"),
                "DirectX shader cache",
                "safe",
                "delete",
                "Rebuilt on demand.",
                True,
            ),
            (
                os.path.join(la, "Google", "Chrome", "User Data", "Default", "Cache"),
                "Chrome cache",
                "safe",
                "delete",
                "Close Chrome first or in-use files are skipped.",
                True,
            ),
            (
                os.path.join(la, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cache"),
                "Brave cache",
                "safe",
                "delete",
                "Close Brave first or in-use files are skipped.",
                True,
            ),
            (
                os.path.join(la, "Microsoft", "Edge", "User Data", "Default", "Cache"),
                "Edge cache",
                "safe",
                "delete",
                "Close Edge first or in-use files are skipped.",
                True,
            ),
            (
                os.path.join(la, "Temp", "chocolatey"),
                "Chocolatey temp",
                "safe",
                "delete",
                "Installer leftovers.",
                True,
            ),
            (
                os.path.join(la, "Yarn", "Cache"),
                "Yarn cache",
                "safe",
                "delete",
                "Re-downloaded on next yarn install.",
                True,
            ),
            (
                os.path.join(up, ".gradle", "caches"),
                "Gradle caches",
                "review",
                "delete",
                "Large re-download on next Gradle build.",
                False,
            ),
            (
                os.path.join(up, ".m2", "repository"),
                "Maven repository",
                "review",
                "delete",
                "Large re-download on next Maven build.",
                False,
            ),
            (
                os.path.join(up, ".nuget", "packages"),
                "NuGet packages",
                "review",
                "delete",
                "Re-downloaded on next restore.",
                False,
            ),
            (
                os.path.join(up, ".docker"),
                "Docker data",
                "review",
                "report",
                "Reclaim with `docker system prune`, not by deleting files.",
                False,
            ),
            (
                os.path.join(win, "Installer"),
                "Windows Installer cache",
                "danger",
                "report",
                "Never bulk-delete: breaks repair/uninstall of installed apps.",
                False,
            ),
            (
                os.path.join(win, "WinSxS"),
                "Component store (WinSxS)",
                "danger",
                "report",
                "Shrink only via `Dism /Online /Cleanup-Image " "/StartComponentCleanup` as admin.",
                False,
            ),
            (
                os.path.join("C:\\", "Windows.old"),
                "Previous Windows install",
                "review",
                "report",
                "Remove via Settings > System > Storage > Cleanup "
                "recommendations (needs admin).",
                False,
            ),
        ]
        out = []
        for path, label, risk, action, note, auto in spec:
            if not path or not os.path.isdir(path):
                continue
            b = dir_bytes(path)
            if b < 1_000_000 and action == "delete":
                continue
            out.append(
                {
                    "label": label,
                    "path": path,
                    "bytes": b,
                    "risk": risk,
                    "action": action,
                    "note": note,
                    "automatable": auto,
                    "kind": "cache",
                }
            )
        for extra in ("hiberfil.sys", "pagefile.sys", "swapfile.sys"):
            p = os.path.join(DRIVE, extra)
            try:
                b = os.stat(p).st_size
            except OSError:
                continue
            note = (
                "Disable with `powercfg /h off` as admin (loses fast " "startup)."
                if extra == "hiberfil.sys"
                else "Managed by Windows; shrink via virtual memory settings."
            )
            out.append(
                {
                    "label": extra,
                    "path": p,
                    "bytes": b,
                    "risk": "danger",
                    "action": "report",
                    "note": note,
                    "automatable": False,
                    "kind": "system",
                }
            )
        out.sort(key=lambda t: -t["bytes"])
        return out

    # -- reads -----------------------------------------------------------
    def find(self, path):
        if not self.root:
            return None
        base = os.path.normcase(os.path.abspath(self.root_path))
        want = os.path.normcase(os.path.abspath(path))
        if want == base:
            return self.root
        if not want.startswith(base.rstrip("\\") + "\\"):
            return None
        node = self.root
        for part in want[len(base.rstrip("\\")) + 1 :].split("\\"):
            if not part:
                continue
            nxt = None
            for name, kid in node.kids.items():
                if os.path.normcase(name) == part:
                    nxt = kid
                    break
            if nxt is None:
                return None
            node = nxt
        return node

    def children(self, path):
        node = self.find(path)
        if node is None:
            return None
        kids = [
            {
                "name": n,
                "path": os.path.join(path, n),
                "dir": True,
                "disk": k.disk,
                "logical": k.logical,
                "cloud": k.cloud,
                "files": k.files,
                "dirs": k.dirs,
                "state": k.state,
                "onedrive": in_onedrive(os.path.join(path, n)),
                "label": classify(os.path.join(path, n), k),
            }
            for n, k in node.kids.items()
        ]
        if node.own_disk or node.own_files:
            kids.append(
                {
                    "name": "(files in this folder)",
                    "path": path,
                    "dir": False,
                    "disk": node.own_disk,
                    "logical": node.own_logical,
                    "cloud": node.own_cloud,
                    "files": node.own_files,
                    "dirs": 0,
                    "state": (
                        "cloud"
                        if node.own_cloud >= node.own_logical and node.own_logical
                        else "local"
                    ),
                    "onedrive": in_onedrive(path),
                }
            )
        kids.sort(key=lambda c: -c["disk"])
        return {
            "path": path,
            "disk": node.disk,
            "logical": node.logical,
            "cloud": node.cloud,
            "files": node.files,
            "dirs": node.dirs,
            "onedrive": in_onedrive(path),
            "children": kids,
        }

    def status(self):
        return {
            "scanning": self.scanning,
            "root": self.root_path,
            "files": self.seen_files,
            "bytes": self.seen_bytes,
            "dirs": self.seen_dirs,
            "errors": self.errors,
            "cur": self.cur,
            "elapsed": round(self.elapsed, 2),
            "done_at": self.done_at,
            "has_index": self.root is not None,
        }


IDX = Index()


def dir_bytes(path):
    """Local bytes under path. Cloud-only files count as 0.

    Same reparse rule as the main walk: skip name surrogates, walk cloud tags.
    """
    total, stack, seen = 0, [path], set()
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                        attrs = st.st_file_attributes
                        if attrs & A_REPARSE:
                            if getattr(st, "st_reparse_tag", 0) in SKIP_TAGS:
                                continue
                            real = os.path.normcase(e.path)
                            if real in seen:
                                continue
                            seen.add(real)
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif not attrs & A_RECALL_DATA:
                            total += st.st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def in_onedrive(path):
    return path_in_roots(path, ONEDRIVE)


def cloud_providers(index=None):
    """Report cloud roots and indexed local bytes without changing state."""

    def measured(root):
        if index is None or index.root is None:
            return None
        node = index.find(root)
        return node.disk if node is not None else None

    one_roots = [
        {
            "path": root,
            "title": "OneDrive",
            "mode": "files-on-demand",
            "source": "Windows environment",
            "local_bytes": measured(root),
        }
        for root in ONEDRIVE
    ]
    google_roots = google_drive_roots()
    for root in google_roots:
        root["local_bytes"] = measured(root["path"])

    local = os.environ.get("LOCALAPPDATA", "")
    drivefs_home = os.path.join(local, "Google", "DriveFS")
    drivefs_install = os.path.join(
        os.environ.get("ProgramFiles", r"C:\Program Files"), "Google", "Drive File Stream"
    )
    cache = None
    if os.path.isdir(drivefs_home):
        cache = {
            "path": drivefs_home,
            "local_bytes": measured(drivefs_home),
            "action": "measure-only",
        }
    return {
        "providers": [
            {
                "id": "onedrive",
                "name": "OneDrive",
                "installed": bool(one_roots),
                "measure_only": False,
                "supports_pin": True,
                "roots": one_roots,
                "note": "Free up space and Keep on device are guarded to these roots.",
            },
            {
                "id": "google_drive",
                "name": "Google Drive",
                "installed": os.path.isdir(drivefs_install) or os.path.isdir(drivefs_home),
                "measure_only": True,
                "supports_pin": False,
                "roots": google_roots,
                "cache": cache,
                "note": "Drive Sentinel measures Google Drive. Change offline access in Drive for desktop.",
            },
        ]
    }


# --- activity log -------------------------------------------------------
# Append-only JSONL. EVERY action that changes bytes on disk lands here before
# the caller is told it worked, so nothing this tool does is invisible and
# anything physically reversible can be reversed from the record alone.
_LOG_LOCK = threading.Lock()


def activity_log_path():
    """Return the audit log beneath this Codex Crew instance's data home."""
    home = os.environ.get("CODEXCREW_HOME") or os.path.join(os.path.expanduser("~"), ".codex-crew")
    return os.path.join(os.path.abspath(home), "apps", "drive-sentinel", "activity.jsonl")


def ensure_audit_log_writable():
    """Refuse byte-changing work unless its durable audit destination opens."""
    path = activity_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8"):
        pass
    return path


def audit(action, path, reverse=None, **fields):
    """Record one action. `reverse` is the exact call that undoes it, or None.

    None means PHYSICALLY irreversible (bytes are gone), not "not implemented".
    Being honest about that is the point: a log that implies a delete can be
    undone is worse than no log.
    """
    entry = {
        "ts": time.time(),
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "path": path,
        "reverse": reverse,
    }
    entry.update(fields)
    line = json.dumps(entry) + "\n"
    with _LOG_LOCK:
        log_path = ensure_audit_log_writable()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    return entry


def read_log(limit=200):
    """Newest-first log entries, each tagged with its line id for undo."""
    try:
        with open(activity_log_path(), "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        e["id"] = i
        e["reversible"] = bool(e.get("reverse"))
        out.append(e)
    out.reverse()
    return out[:limit]


def run_hidden(args):
    """Run a console tool without flashing a window at the user."""
    return subprocess.run(
        args, capture_output=True, text=True, shell=False, creationflags=0x08000000
    )  # CREATE_NO_WINDOW


def set_pin(path, mode):
    """mode 'free' -> dehydrate to OneDrive; 'pin' -> rehydrate and keep local.

    Refused outside a OneDrive root: attrib +U on a plain local file is a
    no-op at best, and this keeps the write surface provably tiny.

    Success is judged by FREE SPACE, never by file attributes. A folder whose
    files are not yet uploaded to the cloud accepts the flag happily and frees
    nothing, and the attribute view still reads "done" (the unpinned-but-local
    state shows UNPINNED + REPARSE_POINT but NOT RECALL_ON_DATA_ACCESS). So a
    delta of ~0 is reported as UNVERIFIED rather than success.
    """
    path = os.path.abspath(path)
    if in_google_drive(path):
        return {
            "ok": False,
            "provider": "google_drive",
            "measure_only": True,
            "error": "Google Drive is measure-only in Drive Sentinel. Change "
            "offline access in Drive for desktop.",
        }
    if not in_onedrive(path):
        return {"ok": False, "error": "Not inside a OneDrive root: " + path}
    if not os.path.exists(path):
        return {"ok": False, "error": "No such path: " + path}
    ensure_audit_log_writable()
    flags = ["+U", "-P"] if mode == "free" else ["+P", "-U"]
    before = drive_space()["free"]
    args = ["attrib"] + flags + [path]
    if os.path.isdir(path):
        args = ["attrib"] + flags + [os.path.join(path, "*")] + ["/S", "/D"]
    r = run_hidden(args)
    time.sleep(2.0)  # OneDrive acts asynchronously; give it a beat to start
    moved = drive_space()["free"] - before
    ok = r.returncode == 0
    # 'free' should GAIN space; 'pin' should LOSE it as bytes come back down.
    if ok and mode == "free" and moved < 8_000_000:
        verdict = (
            "unverified: free space did not move. Those files are "
            "probably not uploaded to OneDrive yet, so there is no "
            "cloud copy to fall back to and nothing can be freed. "
            "Re-check in a few minutes; do not retry in a loop."
        )
    else:
        verdict = "ok"
    out = {
        "ok": ok,
        "mode": mode,
        "path": path,
        "freed_so_far": moved,
        "verified": verdict == "ok",
        "note": verdict,
        "stderr": (r.stderr or "").strip()[:400],
    }
    # Reversible in both directions: dehydrate <-> rehydrate is the whole point.
    audit(
        "dehydrate" if mode == "free" else "rehydrate",
        path,
        reverse={
            "api": "/api/pin",
            "body": {"path": path, "mode": "pin" if mode == "free" else "free"},
        },
        ok=ok,
        freed=moved,
        verified=out["verified"],
        note=verdict,
    )
    return out


def purge(target):
    """Empty one cleanup target. Locked files are skipped, never forced."""
    ensure_audit_log_writable()
    path = target["path"]
    volume = volume_root_for_path(path) or DRIVE
    before = drive_space(volume)["free"]
    removed = skipped = 0
    if target.get("kind") == "cache":
        try:
            entries = list(os.scandir(path))
        except OSError as e:
            return {"ok": False, "error": str(e)}
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    shutil.rmtree(e.path, ignore_errors=False)
                else:
                    os.remove(e.path)
                removed += 1
            except OSError:
                skipped += 1
    else:
        try:
            shutil.rmtree(path, onexc=lambda *_: None)
            removed = 1
        except OSError as e:
            return {"ok": False, "error": str(e)}
    time.sleep(0.4)
    freed = drive_space(volume)["free"] - before
    # reverse=None on purpose: these bytes are GONE. The label says how they
    # come back (a rebuild / re-download), which is not the same as an undo.
    audit(
        "purge",
        path,
        reverse=None,
        label=target.get("label"),
        kind=target.get("kind"),
        risk=target.get("risk"),
        freed=freed,
        removed=removed,
        skipped=skipped,
        recovery=target.get("note", "regenerated on next use"),
    )
    return {
        "ok": True,
        "path": path,
        "removed": removed,
        "skipped": skipped,
        "freed": freed,
        "reversible": False,
    }


# --- HTTP ---------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "Drive Sentinel"

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name, ctype):
        try:
            with open(os.path.join(HERE, name), "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, method, raw_body=b""):
        """Accept only same-origin requests signed by the Codex Crew proxy."""
        fetch_site = self.headers.get("Sec-Fetch-Site", "").strip().lower()
        if fetch_site not in ("", "none", "same-origin"):
            self._send({"error": "cross-site request refused"}, 403)
            return False
        if verify_proxy_request(
            self.headers.get("X-CodexCrew-Proxy", ""),
            method=method,
            target=self.path,
            body=raw_body,
        ):
            return True
        self._send({"error": "unauthorized"}, 401)
        return False

    def _mutation(self, callback):
        try:
            return self._send(callback())
        except OSError:
            return self._send(
                {
                    "error": "audit log unavailable; the operation was refused or could not be confirmed",
                    "code": "audit_unavailable",
                },
                503,
            )

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        if p == "/health":
            return self._send({"status": "ok", "app": "drive-sentinel"})
        if not self._authorized("GET"):
            return
        if p in ("/", "/index.html"):
            return self._file("ui.html", "text/html; charset=utf-8")
        if p == "/api/drive":
            volumes = mounted_volumes()
            requested = unquote(q.get("root", [IDX.root_path or DRIVE])[0])
            root = selectable_volume_root(requested, volumes)
            if root is None:
                return self._send({"error": "not an attached local volume"}, 400)
            d = dict(next(volume for volume in volumes if volume["root"] == root))
            d["t"] = time.time()
            d["onedrive_roots"] = ONEDRIVE
            return self._send(d)
        if p == "/api/volumes":
            return self._send({"volumes": mounted_volumes(), "indexed_root": IDX.root_path})
        if p == "/api/cloud":
            return self._send(cloud_providers(IDX))
        if p == "/api/status":
            return self._send(IDX.status())
        if p == "/api/tree":
            path = unquote(q.get("path", [IDX.root_path])[0])
            got = IDX.children(path)
            if got is None:
                return self._send({"error": "not in index: " + path}, 404)
            return self._send(got)
        if p == "/api/top":
            return self._send(
                {
                    "files": [
                        {
                            "disk": d,
                            "logical": l,
                            "path": pa,
                            "cloud": c,
                            "onedrive": in_onedrive(pa),
                        }
                        for d, l, pa, c in IDX.top_files
                    ]
                }
            )
        if p == "/api/ext":
            rows = sorted(((k, v) for k, v in IDX.ext.items()), key=lambda kv: -kv[1][0])[:40]
            return self._send(
                {"ext": [{"ext": k, "disk": v[0], "logical": v[1], "count": v[2]} for k, v in rows]}
            )
        if p == "/api/dehydrate":
            # Zero-loss reclaim list: local bytes inside OneDrive. Read-only;
            # actually freeing them still goes through POST /api/pin.
            return self._send(
                {"candidates": IDX.dehydrate, "reclaimable": sum(c["local"] for c in IDX.dehydrate)}
            )
        if p == "/api/log":
            # Full history of everything this tool has changed, newest first.
            n = int((q.get("limit", ["200"])[0]) or 200)
            rows = read_log(n)
            return self._send(
                {
                    "entries": rows,
                    "total_freed": sum(r.get("freed") or 0 for r in rows),
                    "reversible": sum(1 for r in rows if r["reversible"]),
                    "path": activity_log_path(),
                }
            )
        if p == "/api/targets":
            ts = sorted(IDX.targets.values(), key=lambda t: -t["bytes"])
            return self._send(
                {
                    "targets": ts,
                    "reclaimable": sum(t["bytes"] for t in ts if t["action"] == "delete"),
                }
            )
        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return self._send({"error": "Content-Type must be application/json"}, 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > 1_000_000:
                return self._send({"error": "request body is too large"}, 413)
            raw_body = self.rfile.read(n)
        except (ValueError, TypeError):
            return self._send({"error": "bad json"}, 400)
        if not self._authorized("POST", raw_body):
            return
        try:
            body = json.loads(raw_body or b"{}")
        except (ValueError, TypeError):
            return self._send({"error": "bad json"}, 400)
        if not isinstance(body, dict):
            return self._send({"error": "request body must be an object"}, 400)
        if u.path == "/api/scan":
            if IDX.scanning:
                return self._send({"error": "already scanning"}, 409)
            root = selectable_volume_root(body.get("root") or DRIVE)
            if root is None:
                return self._send({"error": "root must be an attached local volume"}, 400)
            threading.Thread(target=IDX.scan, args=(root,), daemon=True).start()
            return self._send({"ok": True, "root": root})
        if u.path == "/api/pin":
            mode = body.get("mode")
            if mode not in ("free", "pin"):
                return self._send({"error": "mode must be free|pin"}, 400)
            return self._mutation(lambda: set_pin(body.get("path", ""), mode))
        if u.path == "/api/undo":
            # Replays the `reverse` recorded ON the log entry itself, so undo
            # can never invent an action the log did not sanction.
            rows = read_log(100000)
            match = [r for r in rows if r["id"] == body.get("id")]
            if not match:
                return self._send({"error": "no such log id"}, 404)
            e = match[0]
            rev = e.get("reverse")
            if not rev:
                return self._send(
                    {
                        "error": "not reversible: %s removed bytes permanently. "
                        "Recovery path: %s" % (e.get("action"), e.get("recovery", "rebuild")),
                        "entry": e,
                    },
                    400,
                )
            if rev.get("api") != "/api/pin":
                return self._send({"error": "unsupported reverse target"}, 400)
            b = rev["body"]
            return self._mutation(lambda: {"undid": e, "result": set_pin(b["path"], b["mode"])})
        if u.path == "/api/sweep":
            # Only ever purges risk=safe/automatable targets - see sweep().
            dry_run = body.get("dry_run", True)
            if not isinstance(dry_run, bool):
                return self._send({"error": "dry_run must be a boolean"}, 400)
            return self._mutation(
                lambda: sweep(float(body.get("min_free_gb", SWEEP_MIN_FREE_GB)), dry=dry_run)
            )
        if u.path == "/api/purge":
            t = IDX.targets.get(body.get("id"))
            if not t:
                return self._send({"error": "unknown target id"}, 400)
            requested_root = selectable_volume_root(body.get("root") or "")
            indexed_root = volume_root_for_path(IDX.root_path)
            if (
                requested_root is None
                or indexed_root is None
                or os.path.normcase(requested_root) != os.path.normcase(indexed_root)
            ):
                return self._send(
                    {
                        "error": "selected drive does not match the current index",
                        "code": "indexed_root_mismatch",
                    },
                    409,
                )
            if t["action"] != "delete":
                return self._send({"error": "target is report-only: " + t["note"]}, 400)
            return self._mutation(lambda: purge(t))
        self.send_error(404)


def sweep(min_free_gb=SWEEP_MIN_FREE_GB, dry=False):
    """Purge every target marked risk=safe, cheapest-to-regenerate first.

    Unattended-safe by construction: only 'safe' + action='delete' targets are
    touched, locked files are skipped, and the whole thing is a no-op while
    free space is already above min_free_gb, so a daily schedule does not
    delete caches the machine did not need reclaimed.
    """
    if IDX.root is None:
        IDX.scan(DRIVE)  # sweep must never act on no data
    root = volume_root_for_path(IDX.root_path) or DRIVE
    system_root = (os.environ.get("SystemDrive") or "C:").rstrip("\\/") + "\\"
    if not dry and os.path.normcase(root) != os.path.normcase(system_root):
        return {
            "ok": False,
            "code": "unattended_system_drive_only",
            "error": "unattended cleanup is restricted to the system drive",
            "root": root,
        }
    before = drive_space(root)["free"]
    need = min_free_gb * (1 << 30)
    if before >= need:
        return {
            "ok": True,
            "skipped": True,
            "free": before,
            "reason": "free space already above %.0f GB" % min_free_gb,
            "freed": 0,
            "purged": [],
            "root": root,
        }
    done, freed = [], 0
    for t in sorted(IDX.targets.values(), key=lambda t: -t["bytes"]):
        if t["risk"] != "safe" or t["action"] != "delete":
            continue  # review/danger are never swept
        if not t.get("automatable"):
            continue
        if dry:
            done.append({"label": t["label"], "path": t["path"], "would_free": t["bytes"]})
            freed += t["bytes"]
            continue
        r = purge(t)
        if r.get("ok"):
            freed += r["freed"]
            done.append(
                {
                    "label": t["label"],
                    "path": t["path"],
                    "freed": r["freed"],
                    "skipped": r["skipped"],
                }
            )
        if drive_space(root)["free"] >= need:
            break  # stop as soon as the goal is met
    return {
        "ok": True,
        "skipped": False,
        "dry": dry,
        "freed": freed,
        "free_before": before,
        "free_after": drive_space(root)["free"],
        "purged": done,
        "root": root,
    }


def refresher():
    """Refresh only a root the operator has already scanned explicitly."""
    while True:
        time.sleep(max(REFRESH_MIN, 1) * 60)
        if not IDX.scanning and IDX.root_path:
            try:
                IDX.scan(IDX.root_path)
            except Exception:  # a refresh must never kill serve
                pass


# --- CLI ----------------------------------------------------------------
def _gb(n):
    """Bytes -> short human string. Handles NEGATIVE values, because a
    dehydration that went backwards is exactly what the log must show clearly.
    """
    sign, v = ("-" if n < 0 else ""), abs(float(n))
    u, i = ["B", "KB", "MB", "GB", "TB"], 0
    while v >= 1024 and i < 4:
        v /= 1024
        i += 1
    return sign + ("%.1f %s" % (v, u[i]) if i and v < 10 else "%.0f %s" % (v, u[i]))


def cli(argv):
    """Text/JSON front end over the same Index the GUI and API use."""
    cmd = argv[0] if argv else "serve"
    args = argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    n = 20
    if "-n" in args:
        i = args.index("-n")
        n = int(args[i + 1])
        del args[i : i + 2]

    def out(obj, text):
        print(json.dumps(obj, indent=2) if as_json else text)

    if cmd in ("serve", "gui"):
        return serve()

    if cmd == "status":
        d = drive_space()
        s = IDX.status()
        age = "never" if not s["done_at"] else "%.0f s ago" % (time.time() - s["done_at"])
        d.update(s)
        return out(
            d,
            "C:\\ %s free of %s (%.1f%%) | index: %s files, %s, %s"
            % (
                _gb(d["free"]),
                _gb(d["total"]),
                100.0 * d["free"] / (d["total"] or 1),
                s["files"],
                _gb(s["bytes"]),
                age,
            ),
        )

    if cmd == "scan":
        IDX.scan(args[0] if args else DRIVE)
        s = IDX.status()
        t = IDX.children(IDX.root_path)
        rows = "\n".join("  %10s  %s" % (_gb(c["disk"]), c["name"]) for c in t["children"][:n])
        return out(
            {"status": s, "children": t["children"][:n]},
            "indexed %s files in %ss\n%s" % (s["files"], s["elapsed"], rows),
        )

    if cmd == "tree":
        if IDX.root is None:
            IDX.scan(DRIVE)
        t = IDX.children(args[0] if args else DRIVE)
        if t is None:
            return out({"error": "not in index"}, "not in index")
        return out(
            t,
            "\n".join(
                "  %10s  %10s cloud  %s" % (_gb(c["disk"]), _gb(c["cloud"]), c["name"])
                for c in t["children"][:n]
            ),
        )

    if cmd == "top":
        if IDX.root is None:
            IDX.scan(DRIVE)
        files = IDX.top_files[:n]
        return out(
            {"files": [{"disk": d, "path": p, "cloud": c} for d, l, p, c in files]},
            "\n".join(
                "  %10s %s%s" % (_gb(d), p, "  [cloud]" if c else "") for d, l, p, c in files
            ),
        )

    if cmd == "targets":
        if IDX.root is None:
            IDX.scan(DRIVE)
        ts = sorted(IDX.targets.values(), key=lambda t: -t["bytes"])
        total = sum(t["bytes"] for t in ts if t["action"] == "delete")
        return out(
            {"targets": ts, "reclaimable": total},
            "\n".join(
                "  %-8s %10s  %-34s %s" % (t["risk"], _gb(t["bytes"]), t["label"][:34], t["path"])
                for t in ts
            )
            + "\n  reclaimable: %s" % _gb(total),
        )

    if cmd == "sweep":
        mg = SWEEP_MIN_FREE_GB
        if "--min-free-gb" in args:
            mg = float(args[args.index("--min-free-gb") + 1])
        r = sweep(mg, dry="--dry-run" in args)
        if r["skipped"]:
            return out(r, "nothing to do: " + r["reason"])
        return out(
            r,
            "freed %s (%s -> %s)\n%s"
            % (
                _gb(r["freed"]),
                _gb(r["free_before"]),
                _gb(r["free_after"]),
                "\n".join(
                    "  %10s  %s" % (_gb(p.get("freed", p.get("would_free", 0))), p["label"])
                    for p in r["purged"]
                ),
            ),
        )

    if cmd == "dehydrate":
        # Zero-loss reclaim: push local OneDrive copies back to the cloud.
        # Read-only unless --apply is passed, so the default is always a plan.
        if IDX.root is None:
            IDX.scan(DRIVE)
        cands = IDX.dehydrate[:n]
        total = sum(c["local"] for c in cands)
        if "--apply" not in args:
            return out(
                {"candidates": cands, "reclaimable": total},
                "\n".join(
                    "  %10s  %5s%% local  %-14s %s"
                    % (_gb(c["local"]), c["pct_local"], c["kind"]["kind"], c["path"])
                    for c in cands
                )
                + "\n  would free: %s   (add --apply to do it)" % _gb(total),
            )
        before = drive_space()["free"]
        done = []
        for c in cands:
            r = set_pin(c["path"], "free")
            done.append({"path": c["path"], "ok": r["ok"], "error": r.get("error")})
        # OneDrive dehydrates asynchronously; the number here is a floor.
        time.sleep(5)
        after = drive_space()["free"]
        return out(
            {"applied": done, "freed_so_far": after - before},
            "requested %d dehydrations, freed %s so far (OneDrive keeps "
            "working in the background)" % (len(done), _gb(after - before)),
        )

    if cmd == "log":
        rows = read_log(n if n != 20 else 40)
        return out(
            {"entries": rows, "path": activity_log_path()},
            "\n".join(
                "  #%-4d %s  %-11s %9s  %s%s"
                % (
                    r["id"],
                    r.get("when"),
                    r.get("action"),
                    _gb(r.get("freed") or 0),
                    str(r.get("path"))[:60],
                    "" if r["reversible"] else "  [permanent]",
                )
                for r in rows
            )
            + "\n  log: %s" % activity_log_path(),
        )

    if cmd == "undo":
        if not args:
            return out({"error": "id required"}, "usage: undo <id>  (see `log`)")
        rows = [r for r in read_log(100000) if r["id"] == int(args[0])]
        if not rows:
            return out({"error": "no such id"}, "no such log id")
        e = rows[0]
        if not e.get("reverse"):
            return out(
                {"error": "not reversible", "entry": e},
                "#%s (%s) removed bytes permanently - cannot undo.\n"
                "  recovery: %s" % (e["id"], e["action"], e.get("recovery", "rebuild")),
            )
        b = e["reverse"]["body"]
        r = set_pin(b["path"], b["mode"])
        return out(
            r, ("undid #%s: %s -> %s\n  %s" % (e["id"], e["action"], b["mode"], r.get("note")))
        )

    if cmd in ("free", "keep"):
        if not args:
            return out({"error": "path required"}, "usage: %s <path>" % cmd)
        r = set_pin(args[0], "free" if cmd == "free" else "pin")
        return out(
            r, ("ok" if r["ok"] else "FAILED: " + str(r.get("error"))) + " " + cmd + " " + args[0]
        )

    print(__doc__)
    return 2


def serve():
    """Start the GUI/API server plus the background freshness loop."""
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=refresher, daemon=True).start()
    print("Drive Sentinel on http://127.0.0.1:%d  (Ctrl+C to stop)" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("Drive Sentinel is Windows-only (uses NTFS/OneDrive attributes).")
    sys.exit(cli(sys.argv[1:]) or 0)
