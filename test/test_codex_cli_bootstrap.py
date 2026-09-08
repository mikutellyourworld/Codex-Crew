"""Codex CLI discovery and the owner-triggered one-click bootstrap."""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codex_crew import codex_cli
from codex_crew.agent_sdk import backend_install


def _completed(
    argv: list[str], stdout: str = "codex-cli 1.2.3\n", **_kwargs: object
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


def test_discovery_validates_explicit_codex_path_before_other_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "custom" / "codex.exe"
    explicit.parent.mkdir()
    explicit.write_bytes(b"binary")
    seen: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        seen.append(argv)
        return _completed(argv, "codex-cli 9.8.7\n")

    monkeypatch.setattr(codex_cli.subprocess, "run", run)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        codex_cli.platform_compat, "is_executable_file", lambda path: path.is_file()
    )

    found = codex_cli.find_codex_cli(
        environ={"CODEX_PATH": str(explicit), "PATH": ""},
        home=tmp_path,
        platform_name="win32",
    )

    assert found == codex_cli.CodexCliInstallation(
        path=str(explicit.resolve()), version="9.8.7", source="environment"
    )
    assert seen == [[str(explicit.resolve()), "--version"]]


def test_discovery_finds_versioned_official_windows_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "Local"
    installed = local / "OpenAI" / "Codex" / "bin" / "release-1" / "codex.exe"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"binary")
    monkeypatch.setattr(codex_cli.subprocess, "run", _completed)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        codex_cli.platform_compat, "is_executable_file", lambda path: path.is_file()
    )

    found = codex_cli.find_codex_cli(
        environ={"LOCALAPPDATA": str(local), "PATH": ""},
        home=tmp_path,
        platform_name="win32",
    )

    assert found is not None
    assert found.path == str(installed.resolve())
    assert found.source == "official"


def test_discovery_rejects_a_binary_that_does_not_identify_as_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codex"
    fake.write_bytes(b"binary")
    monkeypatch.setattr(codex_cli.shutil, "which", lambda *_args, **_kwargs: str(fake))
    monkeypatch.setattr(
        codex_cli.platform_compat, "is_executable_file", lambda path: path.is_file()
    )
    monkeypatch.setattr(
        codex_cli.subprocess,
        "run",
        lambda argv, **_kwargs: _completed(argv, "totally-different-tool 1.2.3\n"),
    )

    assert (
        codex_cli.find_codex_cli(
            environ={"PATH": str(tmp_path)}, home=tmp_path, platform_name="linux"
        )
        is None
    )


def test_installer_download_rejects_redirect_outside_openai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.geturl.return_value = "https://example.invalid/install.ps1"
    monkeypatch.setattr(codex_cli.urllib.request, "urlopen", lambda *_a, **_k: response)

    with pytest.raises(codex_cli.CodexInstallError) as raised:
        codex_cli._download_installer(
            codex_cli.OFFICIAL_INSTALL_URL_WINDOWS, tmp_path / "install.ps1"
        )

    assert raised.value.code == "untrusted_installer_redirect"


def test_installer_download_rejects_oversized_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.geturl.return_value = codex_cli.OFFICIAL_INSTALL_URL_POSIX
    response.read.return_value = b"x" * (codex_cli._MAX_INSTALLER_BYTES + 1)
    monkeypatch.setattr(codex_cli.urllib.request, "urlopen", lambda *_a, **_k: response)

    with pytest.raises(codex_cli.CodexInstallError) as raised:
        codex_cli._download_installer(codex_cli.OFFICIAL_INSTALL_URL_POSIX, tmp_path / "install.sh")

    assert raised.value.code == "installer_too_large"


@pytest.mark.parametrize(
    ("platform_name", "script_name", "expected_url", "executable"),
    [
        (
            "win32",
            "install.ps1",
            "https://chatgpt.com/codex/install.ps1",
            "powershell.exe",
        ),
        ("darwin", "install.sh", "https://chatgpt.com/codex/install.sh", "/bin/sh"),
        ("linux", "install.sh", "https://chatgpt.com/codex/install.sh", "/bin/sh"),
    ],
)
def test_official_install_is_downloaded_then_run_non_interactively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    script_name: str,
    expected_url: str,
    executable: str,
) -> None:
    downloads: list[tuple[str, Path]] = []
    runs: list[tuple[list[str], dict[str, str]]] = []

    def download(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        destination.write_text("installer", encoding="utf-8")

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        runs.append((argv, dict(kwargs["env"])))
        return _completed(argv, "installed\n")

    installed = codex_cli.CodexCliInstallation(
        path=str(tmp_path / "codex"), version="1.2.3", source="official"
    )
    monkeypatch.setattr(codex_cli, "_download_installer", download)
    monkeypatch.setattr(codex_cli.subprocess, "run", run)
    monkeypatch.setattr(codex_cli, "find_codex_cli", lambda **_kwargs: installed)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda name, **_kwargs: executable)
    monkeypatch.setattr(
        codex_cli.tempfile, "TemporaryDirectory", lambda **_kwargs: _TempDir(tmp_path)
    )

    result = codex_cli.install_official_codex_cli(
        environ={"PATH": "base"}, platform_name=platform_name
    )

    assert result == installed
    assert downloads == [(expected_url, tmp_path / script_name)]
    argv, env = runs[0]
    assert argv[0] == executable
    assert argv[-1] == str(tmp_path / script_name)
    assert "|" not in argv
    assert env["CODEX_NON_INTERACTIVE"] == "1"


class _TempDir:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> str:
        return str(self.path)

    def __exit__(self, *_args: object) -> None:
        return None


def test_bootstrap_installs_missing_cli_and_adapter_then_clears_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = codex_cli.CodexCliInstallation(
        path=str(tmp_path / "codex"), version="1.2.3", source="official"
    )
    adapter_checks = iter((False, True))
    cleared: list[str] = []
    npm_calls: list[tuple[list[str], Path]] = []

    monkeypatch.setattr(backend_install.codex_cli, "find_codex_cli", lambda: None)
    monkeypatch.setattr(backend_install.codex_cli, "install_official_codex_cli", lambda: installed)
    monkeypatch.setattr(
        backend_install.acp_driver,
        "codex_adapter_resolves",
        lambda: next(adapter_checks),
    )
    monkeypatch.setattr(
        backend_install.acp_driver,
        "clear_codex_resolution_caches",
        lambda: cleared.append("driver"),
    )
    monkeypatch.setattr(backend_install, "config_dir", lambda: tmp_path / "crew-home")
    monkeypatch.setattr(backend_install.shutil, "which", lambda name, path=None: "npm.cmd")

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        npm_calls.append((argv, Path(str(kwargs["cwd"]))))
        prefix = Path(argv[argv.index("--prefix") + 1])
        entry = prefix / "node_modules" / "@agentclientprotocol" / "codex-acp" / "dist" / "index.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("adapter", encoding="utf-8")
        (prefix / "node_modules" / "@agentclientprotocol" / "sdk").mkdir(parents=True)
        return _completed(argv, "adapter installed\n")

    monkeypatch.setattr(backend_install.subprocess, "run", run)

    result = backend_install.bootstrap_codex()

    assert result.ok is True
    assert result.codex_cli == installed
    assert result.adapter_ready is True
    assert cleared == ["driver"]
    assert npm_calls[0][0][-1] == "@agentclientprotocol/codex-acp@1.10.0"
    assert npm_calls[0][1] == tmp_path / "crew-home"


def test_install_endpoint_refuses_non_owner_before_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_crew.dashboard.handlers import acp_backend_status as handler

    request = _request(user="not-owner")
    called: list[str] = []
    monkeypatch.setattr(handler, "sel", lambda: MagicMock())
    monkeypatch.setattr(
        handler,
        "bootstrap_codex",
        lambda: called.append("bootstrap") or MagicMock(),
        raising=False,
    )

    response = asyncio.run(handler.api_codex_install(request))

    assert response.status == 403
    assert json.loads(response.text or "{}")["code"] == "dashboard_owner_required"
    assert called == []


def test_install_endpoint_returns_refreshed_status_without_exposing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codex_crew.dashboard.handlers import acp_backend_status as handler

    installed = codex_cli.CodexCliInstallation(
        path=str(tmp_path / "private" / "codex.exe"),
        version="1.2.3",
        source="official",
    )
    result = backend_install.CodexBootstrapResult(True, installed, True)
    monkeypatch.setattr(handler, "bootstrap_codex", lambda: result, raising=False)
    monkeypatch.setattr(handler, "_snapshot", lambda: [{"id": "codex"}])
    monkeypatch.setattr(handler, "sel", lambda: MagicMock())

    response = asyncio.run(handler.api_codex_install(_request()))

    assert response.status == 200
    payload = json.loads(response.text or "{}")
    assert payload == {
        "ok": True,
        "codex_cli": {"version": "1.2.3", "source": "official"},
        "adapter_ready": True,
        "backends": [{"id": "codex"}],
    }
    assert installed.path not in response.text
    assert handler._codex_install_lock.acquire(blocking=False)
    handler._codex_install_lock.release()


def test_install_endpoint_rejects_a_second_click_while_install_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_crew.dashboard.handlers import acp_backend_status as handler

    lock = threading.Lock()
    lock.acquire()
    monkeypatch.setattr(handler, "_codex_install_lock", lock, raising=False)
    monkeypatch.setattr(handler, "sel", lambda: MagicMock())
    try:
        response = asyncio.run(handler.api_codex_install(_request()))
    finally:
        lock.release()

    assert response.status == 409
    assert json.loads(response.text or "{}")["code"] == "codex_install_in_progress"


def _request(*, user: str = "owner-1", owner: str = "owner-1") -> MagicMock:
    request = MagicMock()
    request.path = "/api/acp-backends/codex/install"
    store = {"app": "", "user": user}
    request.get = lambda key, default=None: store.get(key, default)
    state = MagicMock()
    state.owner_id = owner
    request.app = {"state": state}
    return request
