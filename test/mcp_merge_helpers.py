"""Shared fixtures for tests that drive ``install_agent``'s MCP merge.

Extracted from ``test_agent`` so a second test module can drive the same rebuild
without importing a test module. The repo's convention is a dedicated
``*_helpers.py`` imported by bare name (see ``spawn_test_helpers``,
``chat_test_helpers``); no ``test_*`` module imports another, and a
``from test.test_agent import ...`` form does not resolve under CI's rootdir at
all -- ``test`` is not an importable package there.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from codex_crew.agent import install_agent


def bundled_defaults(tmp_path: Path) -> Path:
    """Write a minimal bundled defaults.json and return its parent dir."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    defaults = {
        "model": "claude-default",
        "tools": ["ReadFile"],
        "allowedTools": ["ReadFile"],
        "mcpServers": {},
        "toolsSettings": {"execute_bash": {"deniedCommands": ["rm -rf /"]}},
        "hooks": {"preToolUse": "audit"},
    }
    (cfg_dir / "defaults.json").write_text(json.dumps(defaults))
    (cfg_dir / "prompt.md").write_text("system prompt")
    return cfg_dir


DEFAULT_MANAGED_MCPS = {
    "codexcrew-cron": {"command": "/usr/bin/codexcrew", "args": ["mcp-cron"]},
    "codexcrew-core": {"command": "/usr/bin/codexcrew", "args": ["mcp-core"]},
}


def run_install_mcp_merge(
    tmp_path: Path,
    cfg_dir: Path,
    *,
    cc_servers: dict,
    kiro_servers: dict,
    codexcrew_servers: dict | None = None,
    which_side_effect=lambda c, **kw: c,
) -> dict:
    """Run install_agent with CC-global and Kiro-global mcp.json seeded and a
    customizable shutil.which. Returns the parsed codexcrew.json config."""
    kiro_dir = tmp_path / "kiro_agents"
    kiro_dir.mkdir(exist_ok=True)
    prompt = cfg_dir / "prompt.md"
    mc_config = tmp_path / "empty_mc_config.json"
    if not mc_config.exists():
        mc_config.write_text(json.dumps({"agent": {"kiro_hooks_autoimport": False}}))
    kiro_mcp = tmp_path / "fake_kiro_mcp.json"
    cc_mcp = tmp_path / "fake_cc_mcp.json"
    kiro_mcp.write_text(json.dumps({"mcpServers": kiro_servers}))
    cc_mcp.write_text(json.dumps({"mcpServers": cc_servers}))
    if codexcrew_servers is not None:
        kc_home = tmp_path / "codexcrew_home"
        kc_home.mkdir(parents=True, exist_ok=True)
        (kc_home / "mcp.json").write_text(json.dumps({"mcpServers": codexcrew_servers}))

    _user_home = tmp_path / "codexcrew_home"
    patches = [
        patch.multiple(
            "codex_crew.agent",
            KIRO_AGENTS_DIR=kiro_dir,
            _BUNDLED_CFG_DIR=cfg_dir,
            _CODEXCREW_BIN="/usr/bin/codexcrew",
            _MANAGED_MCP_SERVERS=DEFAULT_MANAGED_MCPS,
            _KIRO_MCP_JSON=kiro_mcp,
            _CC_MCP_JSON=cc_mcp,
        ),
        patch("codex_crew.agent._user_dir", lambda: _user_home),
        patch("codex_crew.agent._prompt_path", return_value=prompt),
        patch("codex_crew.agent._shipped_defaults", return_value=cfg_dir / "defaults.json"),
        patch("codex_crew.agent._project_dir", return_value=None),
        patch("codex_crew.agent._aim_skill_paths", return_value=[]),
        patch("codex_crew.agent.shutil.which", side_effect=which_side_effect),
        patch("codex_crew.agent._mc_config_path", return_value=mc_config),
        # A companion contributes the Claude Code scope via the CPP seam — the
        # core no longer reads ~/.claude.json directly at rebuild time (OSS is
        # Kiro-only). Point the seam at cc_mcp so these merge-priority tests
        # exercise the seam-routed provider-global merge.
        patch("codex_crew.agent._extra_mcp_scope_globals", return_value=[cc_mcp]),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        path = install_agent()
    return json.loads(path.read_text(encoding="utf-8"))
