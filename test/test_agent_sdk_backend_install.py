"""Machine-local readiness checks for the two public backends."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from codex_crew.acp_backends import (
    ACP_BACKEND_CODEX,
    ACP_BACKEND_OPENAI_COMPATIBLE,
    ACP_BACKENDS_KNOWN,
)
from codex_crew.agent_sdk import backend_install as probe


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> None:
    probe.clear_probe_cache()


def test_codex_probe_names_the_adapter_and_real_install_command(monkeypatch) -> None:
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_resolves", lambda: False)
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_cached_negative", lambda: False)
    monkeypatch.setattr(
        probe.acp_driver,
        "codex_adapter_install_command",
        lambda: "npm i -g @zed-industries/codex-acp",
    )

    state = probe.probe_backend(ACP_BACKEND_CODEX)

    assert state.installed == probe.MISSING
    assert state.missing_components == (probe.COMPONENT_CODEX_ACP_ADAPTER,)
    assert state.install_command == "npm i -g @zed-industries/codex-acp"


def test_codex_probe_reports_a_resolved_adapter(monkeypatch) -> None:
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_resolves", lambda: True)
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_cached_negative", lambda: False)

    state = probe.probe_backend(ACP_BACKEND_CODEX)

    assert state.installed == probe.INSTALLED
    assert state.missing_components == ()
    assert state.install_command == ""


def test_openai_compatible_adapter_is_bundled() -> None:
    state = probe.probe_backend(ACP_BACKEND_OPENAI_COMPATIBLE)

    assert state.installed == probe.INSTALLED
    assert state.missing_components == ()


def test_removed_backend_has_no_remediation() -> None:
    state = probe.probe_backend("removed-backend")

    assert state.installed == probe.UNKNOWN
    assert state.missing_components == ()
    assert state.install_command == ""


def test_probe_rows_cover_only_the_public_registry(monkeypatch) -> None:
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_resolves", lambda: True)
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_cached_negative", lambda: False)

    rows = probe.probe_backends()

    assert {row.backend for row in rows} == set(ACP_BACKENDS_KNOWN)
    assert [row.policy_id for row in rows] == ["codex", "openai_compatible"]


def _request(*, app: str = "", user: str = "owner-1", owner: str = "owner-1"):
    request = MagicMock()
    request.path = "/api/acp-backends"
    store = {"app": app, "user": user}
    request.get = lambda key, default=None: store.get(key, default)
    state = MagicMock()
    state.owner_id = owner
    request.app = {"state": state}
    return request


def test_status_endpoint_refuses_non_owner_before_probing(monkeypatch) -> None:
    from codex_crew.dashboard.handlers import acp_backend_status as handler

    monkeypatch.setattr(handler, "sel", lambda: MagicMock())
    called: list[str] = []
    monkeypatch.setattr(handler, "_snapshot", lambda: called.append("probed") or [])

    response = asyncio.run(handler.api_acp_backend_status(_request(user="not-owner")))

    assert response.status == 403
    assert json.loads(response.text or "{}")["code"] == "dashboard_owner_required"
    assert called == []


def test_status_endpoint_returns_codex_and_openai_compatible(monkeypatch) -> None:
    from codex_crew.dashboard.handlers import acp_backend_status as handler
    import codex_crew.dashboard.handlers.core as core

    monkeypatch.setattr(probe.acp_driver, "codex_adapter_resolves", lambda: True)
    monkeypatch.setattr(probe.acp_driver, "codex_adapter_cached_negative", lambda: False)
    monkeypatch.setattr(
        core,
        "_selectable_acp_backends",
        lambda: ["codex", "openai_compatible"],
    )

    response = asyncio.run(handler.api_acp_backend_status(_request()))

    assert response.status == 200
    rows = json.loads(response.text or "{}")["backends"]
    assert [row["policy_id"] for row in rows] == ["codex", "openai_compatible"]
    assert all(row["selectable"] for row in rows)
