"""Discover and install the official Codex CLI without an agent in the loop."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from codex_crew import platform_compat
from codex_crew.env import augmented_path
from codex_crew.subprocess_utf8 import UTF8_TEXT

CODEX_BIN = "codex"
CODEX_PATH_ENV = "CODEX_PATH"
OFFICIAL_INSTALL_URL_POSIX = "https://chatgpt.com/codex/install.sh"
OFFICIAL_INSTALL_URL_WINDOWS = "https://chatgpt.com/codex/install.ps1"

_VERSION_RE = re.compile(r"^codex-cli\s+([^\s]+)", re.IGNORECASE)
_VERSION_TIMEOUT_SECONDS = 8
_INSTALL_TIMEOUT_SECONDS = 300
_DOWNLOAD_TIMEOUT_SECONDS = 30
_MAX_INSTALLER_BYTES = 1024 * 1024
_TRUSTED_INSTALL_HOSTS = frozenset({"chatgpt.com", "releases.openai.com"})


@dataclass(frozen=True)
class CodexCliInstallation:
    """A validated Codex executable and its user-visible version."""

    path: str
    version: str
    source: str


class CodexInstallError(RuntimeError):
    """A bounded, user-actionable failure from the official installer path."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _candidate_paths(
    environ: Mapping[str, str], home: Path, platform_name: str
) -> list[tuple[Path, str]]:
    """Return bounded, known Codex locations in precedence order."""

    candidates: list[tuple[Path, str]] = []
    explicit = environ.get(CODEX_PATH_ENV, "").strip()
    if explicit:
        candidates.append((Path(explicit).expanduser(), "environment"))

    if platform_name == "win32":
        local = environ.get("LOCALAPPDATA", "").strip()
        if local:
            local_root = Path(local)
            versioned_root = local_root / "OpenAI" / "Codex" / "bin"
            if versioned_root.is_dir():
                candidates.extend(
                    (path, "official")
                    for path in sorted(versioned_root.glob("*/codex.exe"), reverse=True)
                )
            candidates.extend(
                [
                    (
                        local_root / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe",
                        "official",
                    ),
                    (local_root / "OpenAI" / "Codex" / "bin" / "codex.exe", "official"),
                ]
            )
        roaming = environ.get("APPDATA", "").strip()
        if roaming:
            candidates.append((Path(roaming) / "npm" / "codex.cmd", "npm"))
        candidates.extend(
            [
                (home / ".local" / "bin" / "codex.exe", "user"),
                (home / ".local" / "bin" / "codex.cmd", "user"),
            ]
        )
    else:
        candidates.append((home / ".local" / "bin" / "codex", "user"))
        candidates.append((home / ".npm-global" / "bin" / "codex", "npm"))
        if platform_name == "darwin":
            candidates.append((Path("/opt/homebrew/bin/codex"), "homebrew"))
        else:
            candidates.append((Path("/home/linuxbrew/.linuxbrew/bin/codex"), "homebrew"))
        candidates.append((Path("/usr/local/bin/codex"), "system"))

    search_path = augmented_path(environ.get("PATH", ""), home=str(home))
    on_path = shutil.which(CODEX_BIN, path=search_path)
    if on_path:
        candidates.append((Path(on_path), "path"))

    deduplicated: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in candidates:
        if not path.is_absolute():
            continue
        key = os.path.normcase(os.path.normpath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append((path, source))
    return deduplicated


def _probe_candidate(path: Path, source: str) -> CodexCliInstallation | None:
    """Accept only a runnable executable that identifies itself as Codex CLI."""

    try:
        resolved = path.resolve()
        if not platform_compat.is_executable_file(resolved):
            return None
        result = subprocess.run(  # noqa: S603 - fixed executable plus fixed flag
            [str(resolved), "--version"],
            capture_output=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
            **UTF8_TEXT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    first_line = (result.stdout or result.stderr or "").strip().splitlines()[:1]
    match = _VERSION_RE.match(first_line[0]) if first_line else None
    if match is None:
        return None
    return CodexCliInstallation(str(resolved), match.group(1), source)


def find_codex_cli(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> CodexCliInstallation | None:
    """Find and validate an existing Codex CLI on Windows, macOS, or Linux."""

    resolved_environ = os.environ if environ is None else environ
    resolved_home = Path.home() if home is None else home
    resolved_platform = sys.platform if platform_name is None else platform_name
    for path, source in _candidate_paths(resolved_environ, resolved_home, resolved_platform):
        installation = _probe_candidate(path, source)
        if installation is not None:
            return installation
    return None


def _trusted_install_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _TRUSTED_INSTALL_HOSTS or host.endswith(".openai.com")


def _download_installer(url: str, destination: Path) -> None:
    """Download one small official installer script to a temporary file."""

    request = urllib.request.Request(url, headers={"User-Agent": "Codex-Crew/0.7"})
    try:
        with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if not _trusted_install_url(final_url):
                raise CodexInstallError(
                    "untrusted_installer_redirect", "Codex installer redirected off OpenAI."
                )
            payload = response.read(_MAX_INSTALLER_BYTES + 1)
    except CodexInstallError:
        raise
    except (OSError, ValueError) as exc:
        raise CodexInstallError(
            "installer_download_failed", "Could not download the official Codex installer."
        ) from exc
    if len(payload) > _MAX_INSTALLER_BYTES:
        raise CodexInstallError(
            "installer_too_large", "The Codex installer was larger than expected."
        )
    destination.write_bytes(payload)


def _installer_argv(platform_name: str, search_path: str, script: Path) -> list[str]:
    if platform_name == "win32":
        shell = shutil.which("powershell.exe", path=search_path) or shutil.which(
            "pwsh.exe", path=search_path
        )
        if not shell:
            raise CodexInstallError(
                "powershell_missing", "PowerShell is required to install Codex CLI."
            )
        return [
            shell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
    shell = "/bin/sh" if Path("/bin/sh").is_file() else shutil.which("sh", path=search_path)
    if not shell:
        raise CodexInstallError("shell_missing", "A POSIX shell is required to install Codex CLI.")
    return [shell, str(script)]


def install_official_codex_cli(
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> CodexCliInstallation:
    """Download, run, and verify OpenAI's non-interactive installer."""

    resolved_platform = sys.platform if platform_name is None else platform_name
    if resolved_platform not in {"win32", "darwin", "linux"}:
        raise CodexInstallError(
            "unsupported_platform", "One-click Codex installation is not supported here."
        )
    resolved_environ = dict(os.environ if environ is None else environ)
    resolved_environ["CODEX_NON_INTERACTIVE"] = "1"
    search_path = augmented_path(resolved_environ.get("PATH", ""))
    script_name = "install.ps1" if resolved_platform == "win32" else "install.sh"
    url = (
        OFFICIAL_INSTALL_URL_WINDOWS if resolved_platform == "win32" else OFFICIAL_INSTALL_URL_POSIX
    )

    with tempfile.TemporaryDirectory(prefix="codexcrew-codex-install-") as temp_dir:
        script = Path(temp_dir) / script_name
        _download_installer(url, script)
        argv = _installer_argv(resolved_platform, search_path, script)
        try:
            result = subprocess.run(  # noqa: S603 - fixed official installer argv
                argv,
                cwd=temp_dir,
                env=resolved_environ,
                capture_output=True,
                timeout=_INSTALL_TIMEOUT_SECONDS,
                check=False,
                **UTF8_TEXT,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CodexInstallError(
                "installer_launch_failed", "Could not run the official Codex installer."
            ) from exc
        if result.returncode != 0:
            raise CodexInstallError(
                "installer_failed", "The official Codex installer did not complete."
            )

    installation = find_codex_cli(environ=resolved_environ, platform_name=resolved_platform)
    if installation is None:
        raise CodexInstallError(
            "installed_cli_not_found", "Codex CLI installed, but its executable was not found."
        )
    return installation


__all__ = [
    "CODEX_PATH_ENV",
    "CodexCliInstallation",
    "CodexInstallError",
    "find_codex_cli",
    "install_official_codex_cli",
]
