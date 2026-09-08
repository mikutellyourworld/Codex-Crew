"""Bridge Codex PreToolUse hooks into Codex Crew's security policy."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
from typing import Any


class CodexToolGateConfigError(ValueError):
    """Raised when existing Codex config cannot be extended safely."""


_SHELL_TOOLS = {
    "bash",
    "exec_command",
    "powershell",
    "shell",
    "shell_command",
    "terminal",
    "unified_exec",
}


def _hook_command(python_executable: str, agent: str) -> str:
    argv = [python_executable, "-m", "codex_crew.codex_tool_gate", "--agent", agent]
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def build_codex_config(
    existing_json: str | None,
    *,
    python_executable: str,
    agent: str,
) -> str:
    """Preserve operator Codex config and append the mandatory Crew hook."""
    try:
        config = json.loads(existing_json) if existing_json else {}
    except (TypeError, json.JSONDecodeError) as exc:
        raise CodexToolGateConfigError("CODEX_CONFIG must be valid JSON") from exc
    if not isinstance(config, dict):
        raise CodexToolGateConfigError("CODEX_CONFIG must contain a JSON object")

    features = config.setdefault("features", {})
    if not isinstance(features, dict):
        raise CodexToolGateConfigError("CODEX_CONFIG.features must be an object")
    features["hooks"] = True

    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise CodexToolGateConfigError("CODEX_CONFIG.hooks must be an object")
    groups = hooks.setdefault("PreToolUse", [])
    if not isinstance(groups, list):
        raise CodexToolGateConfigError("CODEX_CONFIG.hooks.PreToolUse must be a list")
    groups.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": _hook_command(python_executable, agent),
                    "statusMessage": "Checking Codex Crew security policy",
                }
            ]
        }
    )
    return json.dumps(config, separators=(",", ":"))


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _tool_kind(tool_name: str) -> str:
    normalized = tool_name.casefold()
    if normalized in _SHELL_TOOLS:
        return "execute"
    if normalized in {"apply_patch", "write_file", "edit_file"}:
        return "edit"
    if normalized in {"read_file", "list_dir", "glob", "grep", "search"}:
        return "read"
    if "web" in normalized or "fetch" in normalized:
        return "fetch"
    return normalized


def evaluate_pre_tool_use(
    payload: object,
    *,
    session_key: str,
    agent: str,
) -> dict[str, Any] | None:
    """Return a Codex deny response, or ``None`` to retain Codex policy."""
    if not isinstance(payload, dict):
        return _deny("Blocked: malformed tool request")
    event_name = payload.get("hook_event_name")
    if event_name not in (None, "PreToolUse"):
        return _deny("Blocked: unexpected tool hook event")
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return _deny("Blocked: tool identity could not be verified")
    if not isinstance(tool_input, dict):
        return _deny("Blocked: tool arguments could not be verified")

    normalized = tool_name.casefold()
    is_shell = normalized in _SHELL_TOOLS
    command = tool_input.get("command") if is_shell else None
    if is_shell and (not isinstance(command, str) or not command.strip()):
        return _deny("Blocked: shell command could not be verified")

    from codex_crew.config import CodexCrewConfig
    from codex_crew.hooks import TOOL_DENY, HookManager, hooks_config_from_config_dict

    config = CodexCrewConfig.load()
    manager = HookManager(hooks_config_from_config_dict(config.hooks))
    result = manager.on_tool_call(
        tool_name,
        session_key=session_key,
        agent=agent,
        app="codex",
        tool_kind=_tool_kind(tool_name),
        raw_params=tool_input,
        command=command if isinstance(command, str) else None,
        is_shell=is_shell,
        mcp_tool_name=tool_name,
        resolved_agent=agent,
    )
    if result.action == TOOL_DENY:
        return _deny(result.reason or "Blocked by Codex Crew security policy")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="codexcrew")
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()):
            decision = evaluate_pre_tool_use(
                payload,
                session_key=os.environ.get("CODEXCREW_SESSION_KEY", "codex"),
                agent=args.agent,
            )
    except Exception:
        decision = _deny("Blocked: Codex Crew could not verify this tool request")
    if decision is not None:
        json.dump(decision, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
