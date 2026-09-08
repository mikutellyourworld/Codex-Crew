"""Release-contract tests for the public Codex Crew distribution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _probe(script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "CODEXCREW_HOME": str(tmp_path / "codex-crew-home"),
        "KIROCREW_HOME": str(tmp_path / "wrong-product-home"),
    }
    env.pop("CODEXCREW_PORT", None)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_distribution_exposes_codex_crew_identity() -> None:
    """A wheel build must publish the fork's own package and CLI identities."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["name"] == "codexcrew"
    assert project["version"] == "0.7.0"
    assert project["scripts"] == {"codexcrew": "codex_crew._bootstrap:main"}
    assert project["urls"]["Homepage"].endswith("/mikutellyourworld/Codex-Crew")

    desktop = json.loads((ROOT / "website" / "electron" / "package.json").read_text())
    assert desktop["name"] == "codexcrew-desktop"
    assert desktop["build"]["appId"] == "io.github.mikutellyourworld.codexcrew"
    assert desktop["build"]["productName"] == "Codex Crew"
    assert desktop["build"]["win"]["executableName"] == "codexcrew-desktop"


def test_runtime_defaults_are_codex_only_and_use_an_isolated_home(tmp_path: Path) -> None:
    """A clean runtime must ignore the old product's home and backend defaults."""
    result = _probe(
        """
import json
from codex_crew.acp_backends import DEFAULT_ACP_BACKEND, selectable_backends
from codex_crew.config.loader import DASHBOARD_PORT
from codex_crew.config.paths import config_dir

print(json.dumps({
    "backend": DEFAULT_ACP_BACKEND,
    "selectable": sorted(selectable_backends()),
    "home": str(config_dir()),
    "port": DASHBOARD_PORT,
}))
""",
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "backend": "codex",
        "selectable": ["codex", "openai_compatible"],
        "home": str(tmp_path / "codex-crew-home"),
        "port": 5486,
    }


def test_drive_sentinel_ships_enabled_with_an_isolated_backend(tmp_path: Path) -> None:
    """Fresh installs must discover the bundled drive guard under its new identity."""
    result = _probe(
        """
import json
from codex_crew.apps.discovery import discover_builtin_apps

apps = {app["name"]: app for app in discover_builtin_apps()}
app = apps["drive-sentinel"]
print(json.dumps({
    "displayName": app["displayName"],
    "defaultEnabled": app["defaultEnabled"],
    "entryPoint": app["backend"]["entryPoint"],
}))
""",
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "displayName": "Drive Sentinel",
        "defaultEnabled": True,
        "entryPoint": "codex_crew.apps.builtins.drive_sentinel.backend",
    }
    manifest = json.loads(
        (ROOT / "src/codex_crew/apps/builtins/drive_sentinel/app.json").read_text()
    )
    assert manifest["backend"]["port"] == "auto"
    assert manifest["backend"]["healthCheck"] == "/health"


def test_drive_sentinel_uses_the_app_managers_allocated_port(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The backend must bind the safe port selected by the app manager."""
    monkeypatch.setenv("PORT", "9194")

    result = _probe(
        """
from codex_crew.apps.builtins.drive_sentinel.backend import PORT
print(PORT)
""",
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "9194"


def test_desktop_bundle_stages_the_pinned_codex_adapter() -> None:
    build_script = (ROOT / "packaging" / "build-desktop.sh").read_text(encoding="utf-8")

    assert "stage_codex_adapter" in build_script
    assert '"@agentclientprotocol/codex-acp@1.10.0"' in build_script
    supervisor = (ROOT / "website" / "electron" / "gateway-supervisor.js").read_text(
        encoding="utf-8"
    )
    assert "CODEXCREW_NODE_EXECUTABLE" in supervisor


def test_source_bootstraps_install_only_the_codex_adapter() -> None:
    scripts = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("setup.sh", "minimal_install.sh", "packaging/build-desktop.sh")
    ).lower()

    assert "@agentclientprotocol/codex-acp@1.10.0" in scripts
    assert "@agentclientprotocol/" + "claude-agent-acp" not in scripts
    assert "npm install -g " + "kiro-cli" not in scripts
    assert "npm install -g " + "kimi" not in scripts


def test_stale_portable_builder_is_not_a_public_release_surface() -> None:
    assert not (ROOT / "build-zip.ps1").exists()
