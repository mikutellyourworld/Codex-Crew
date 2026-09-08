"""Every script Windows executes directly must be pure ASCII.

Windows PowerShell 5.1 (``powershell.exe``, still the interpreter WSH and the Start
Menu reach first), ``cmd.exe`` and WSH all decode a BOM-less script with a legacy
code page -- ANSI for ``.ps1``/``.vbs``, OEM for ``.bat``/``.cmd`` -- not as UTF-8.
So a UTF-8 character in one of those files reaches the operator re-decoded: the tray
balloon that read ``Starting gateway…`` shipped as ``Starting gatewayâ€¦``, and
``install.ps1``'s banner em dash as ``â€"``. Comments corrupt just as readably to
anyone reading the file, and in a ``.bat`` a mangled byte can break parsing outright.

ASCII rather than "ASCII or a UTF-8 BOM": a BOM does fix PowerShell, but WSH treats a
BOM-led ``.vbs`` as ANSI text beginning with three junk characters, so the accepting
rule differs per extension and gets one wrong. ASCII is the single rule that holds on
every code page and in every one of these hosts.

This reads bytes rather than running anything, so it holds on every platform in the
matrix -- which is the point. The corruption is invisible on the machine that authors
the file, and a UTF-8-first editor is exactly where it gets introduced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Extensions Windows hands to an interpreter that predates UTF-8 defaults.
_WINDOWS_EXECUTED = frozenset({".ps1", ".psm1", ".bat", ".cmd", ".vbs"})

#: Directory names that hold code we do not author. Matched on any path component.
#: ``backend-dist`` is the bundled Python runtime the Electron build stages, so it
#: carries the stdlib's and venv's own ``.bat``/``.ps1`` scripts; policing those would
#: put this gate at the mercy of an interpreter upgrade for files nobody here wrote.
_NOT_OURS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "backend-dist",
        "build",
        "dist",
        "out",
        "release",
        "site",
        ".pytest_cache",
        ".hypothesis",
        "__pycache__",
        "_vendor",
    }
)


def _windows_scripts() -> list[Path]:
    found = [
        p
        for p in _REPO_ROOT.rglob("*")
        if p.suffix.lower() in _WINDOWS_EXECUTED
        and p.is_file()
        and not _NOT_OURS & set(p.relative_to(_REPO_ROOT).parts)
    ]
    assert found, "found no Windows-executed scripts at all -- the walk is broken"
    return sorted(found)


@pytest.mark.parametrize("script", _windows_scripts(), ids=lambda p: p.name)
def test_windows_script_is_ascii(script: Path) -> None:
    raw = script.read_bytes()
    high = {b for b in raw if b > 0x7F}
    assert not high, (
        f"{script.relative_to(_REPO_ROOT)} holds non-ASCII bytes "
        f"{sorted(hex(b) for b in high)}. Windows decodes this file with a legacy code "
        f"page, so those bytes reach the operator as mojibake. Use an ASCII spelling "
        f"('...' for an ellipsis, '-' for a dash)."
    )
