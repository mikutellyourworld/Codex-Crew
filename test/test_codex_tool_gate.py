"""Codex-native PreToolUse bridge into Codex Crew's security gate."""

from __future__ import annotations

import json

import pytest


def test_codex_config_preserves_operator_settings_and_appends_gate() -> None:
    from codex_crew.codex_tool_gate import build_codex_config

    original = json.dumps(
        {
            "model": "gpt-test",
            "features": {"browser_use": True, "hooks": False},
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "^custom$",
                        "hooks": [{"type": "command", "command": "custom-hook"}],
                    }
                ]
            },
        }
    )

    merged = json.loads(
        build_codex_config(
            original,
            python_executable=r"C:\Program Files\Python\python.exe",
            agent="codexcrew",
        )
    )

    assert merged["model"] == "gpt-test"
    assert merged["features"] == {"browser_use": True, "hooks": True}
    groups = merged["hooks"]["PreToolUse"]
    assert groups[0]["hooks"][0]["command"] == "custom-hook"
    assert len(groups) == 2
    command = groups[1]["hooks"][0]["command"]
    assert "codex_crew.codex_tool_gate" in command
    assert "codexcrew" in command


@pytest.mark.parametrize(
    "raw",
    (
        "[]",
        '"not-an-object"',
        '{"hooks": []}',
        '{"features": []}',
        '{"hooks": {"PreToolUse": {}}}',
    ),
)
def test_codex_config_rejects_shapes_that_could_drop_the_gate(raw: str) -> None:
    from codex_crew.codex_tool_gate import CodexToolGateConfigError, build_codex_config

    with pytest.raises(CodexToolGateConfigError):
        build_codex_config(raw, python_executable="python", agent="codexcrew")


def test_sensitive_shell_read_is_denied_by_the_real_gate() -> None:
    from codex_crew.codex_tool_gate import evaluate_pre_tool_use

    decision = evaluate_pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "Get-Content $HOME\\.aws\\credentials"},
        },
        session_key="codex-test",
        agent="codexcrew",
    )

    assert decision is not None
    specific = decision["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    assert "sensitive" in specific["permissionDecisionReason"].lower()


def test_benign_shell_read_falls_through_to_codex_approval_policy() -> None:
    from codex_crew.codex_tool_gate import evaluate_pre_tool_use

    decision = evaluate_pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "Get-ChildItem ."},
        },
        session_key="codex-test",
        agent="codexcrew",
    )

    assert decision is None


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}},
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": "not-an-object",
        },
    ),
)
def test_malformed_or_unverifiable_tool_payload_fails_closed(payload: dict) -> None:
    from codex_crew.codex_tool_gate import evaluate_pre_tool_use

    decision = evaluate_pre_tool_use(payload, session_key="codex-test", agent="codexcrew")

    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
