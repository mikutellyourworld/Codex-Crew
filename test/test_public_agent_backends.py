"""Public multi-agent backend defaults and local CLI resolution."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codex_crew.acp.client import AcpClient
from codex_crew.acp_backends import (
    ACP_BACKEND_CODEX,
    ACP_BACKEND_OPENAI_COMPATIBLE,
    BASELINE_SELECTABLE_BACKENDS,
    DEFAULT_ACP_BACKEND,
    resolve_selected_backend,
)
from codex_crew.config.loader import CodexCrewConfig
from codex_crew.agent_sdk.backend_install import UNKNOWN, probe_backend


def test_public_default_is_codex_and_legacy_kiro_is_not_offered() -> None:
    assert DEFAULT_ACP_BACKEND == ACP_BACKEND_CODEX
    assert resolve_selected_backend(None) == ACP_BACKEND_CODEX
    assert CodexCrewConfig().agent.acp_backend == ACP_BACKEND_CODEX
    assert BASELINE_SELECTABLE_BACKENDS == frozenset(
        {
            ACP_BACKEND_CODEX,
            ACP_BACKEND_OPENAI_COMPATIBLE,
        }
    )


def test_removed_backends_have_no_install_remediation() -> None:
    """A removed runtime must not retain an installer or readiness claim."""
    for backend in ("", "kas", "claude", "kimi"):
        state = probe_backend(backend)
        assert state.installed == UNKNOWN
        assert state.missing_components == ()
        assert state.install_command == ""


@pytest.mark.asyncio
async def test_openai_compatible_backend_spawns_bundled_adapter(tmp_path) -> None:
    client = AcpClient(
        work_dir=tmp_path,
        acp_backend=ACP_BACKEND_OPENAI_COMPATIBLE,
        extra_env={
            "CODEXCREW_OPENAI_BASE_URL": "http://127.0.0.1:4853/v1",
            "CODEXCREW_OPENAI_MODEL": "auto",
            "CODEXCREW_OPENAI_API_KEY": "local-test-key",
        },
    )
    process = MagicMock()
    process.pid = 12345
    process.returncode = None

    with (
        patch(
            "codex_crew.acp.client.wrap_argv",
            side_effect=lambda argv, mode, **kwargs: (argv, None),
        ),
        patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ) as spawn,
        patch("codex_crew.session._track_pid"),
        patch("codex_crew.session._track_session_pid"),
    ):
        await client._spawn()

    argv = list(spawn.call_args.args)
    assert argv[:3] == [
        sys.executable,
        "-m",
        "codex_crew.acp_adapters.openai_compatible_server",
    ]
    env = spawn.call_args.kwargs["env"]
    assert env["CODEXCREW_OPENAI_BASE_URL"] == "http://127.0.0.1:4853/v1"
    assert env["CODEXCREW_OPENAI_API_KEY"] == "local-test-key"
    if client._stderr_task is not None:
        client._stderr_task.cancel()
