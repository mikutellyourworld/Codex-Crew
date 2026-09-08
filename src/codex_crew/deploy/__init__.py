"""CodexCrew core deploy module — AWS deploy engine, profiles, and route handlers.

Core owns the AWS deploy layer directly; the "Artifact Deploy" page lives
at ``/artifacts/deploy`` in the main dashboard.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
from pathlib import Path

from codex_crew import platform_compat
from codex_crew.config.paths import config_dir

logger = logging.getLogger(__name__)


def _force_rmtree(path: Path) -> None:
    """Remove a directory tree, tolerating Windows read-only entries.

    On Windows ``shutil.rmtree`` raises ``PermissionError`` (WinError 5) on any
    entry carrying the read-only attribute — which OneDrive routinely sets on
    synced files, so a skills tree that was ever synced cannot be replaced and
    the whole gateway startup crashes. The error handler clears the read-only
    bit and retries the delete. ``onexc`` is the Python 3.12 spelling; ``onerror``
    is kept for older interpreters.
    """

    def _clear_readonly_and_retry(func, p, _exc):  # type: ignore[no-untyped-def]
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            pass
        func(p)

    try:
        shutil.rmtree(path, onexc=_clear_readonly_and_retry)  # type: ignore[call-arg]
    except TypeError:
        # Python < 3.12 has no onexc; onerror takes (func, path, exc_info).
        shutil.rmtree(
            path,
            onerror=lambda func, p, _ei: _clear_readonly_and_retry(func, p, None),
        )


_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


_MANAGED_MARKER = ".codexcrew-managed"


def _register_core_skills() -> None:
    """Idempotently install deploy skills into <home>/skills/.

    Always copies (never symlinks) so that _find_skills' realpath containment
    check sees the skill files as living inside the skill root. A symlink whose
    target is in site-packages resolves outside the root and gets pruned.

    Called at gateway startup. Uses config_dir() so pods/tests isolate correctly.

    Safety: only removes/replaces directories that contain a `.codexcrew-managed`
    marker file (written by us on creation). User-placed directories with the
    same name are left untouched with a warning.
    """
    target = config_dir() / "skills"
    target.mkdir(parents=True, exist_ok=True)

    for skill_dir in _SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        link = target / skill_dir.name

        # Migration: if an existing entry is a symlink OR a Windows junction
        # (from older versions), unlink the reparse point itself and replace it
        # with a fresh copy. path.is_symlink() is False for a junction, so use
        # the platform_compat helpers (see AGENTS.md cross-platform table) —
        # otherwise a junction falls through to rmtree and recurses into / wipes
        # the link target.
        if platform_compat.is_link_or_junction(link):
            platform_compat.unlink_link_or_junction(link)
        elif link.exists():
            # Real directory exists at that name — only remove if we created it
            if not (link / _MANAGED_MARKER).exists():
                logger.warning(
                    "Skipping deploy skill %s: user-placed directory at %s "
                    "(remove it manually to allow CodexCrew to manage this skill)",
                    skill_dir.name,
                    link,
                )
                continue
            _force_rmtree(link)

        # Always copy (not symlink) so realpath stays within skill root.
        try:
            shutil.copytree(skill_dir, link)
            # Write the managed marker so future refreshes know it's ours
            (link / _MANAGED_MARKER).write_text("")
            logger.debug("Copied deploy skill %s", skill_dir.name)
        except OSError:
            logger.error("Failed to install deploy skill %s", skill_dir.name)
            raise
