"""Dashboard contracts for OpenAI-compatible profile management."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web

from codex_crew.config.loader import CodexCrewConfig
from codex_crew.dashboard.handlers.openai_profiles import (
    api_profiles_active,
    profiles_payload,
    setup_openai_profile_routes,
    upsert_custom_profile,
)
from codex_crew.secrets import SecretVault


class _Request:
    app: dict = {}

    async def json(self) -> dict[str, str]:
        return {"id": "freechain"}


class _AsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def test_payload_exposes_key_presence_but_never_key_material() -> None:
    cfg = CodexCrewConfig()
    payload = profiles_payload(cfg, {"FREECHAIN_ACCESS_KEY"})
    freechain = payload["profiles"][0]
    assert freechain["id"] == "freechain"
    assert freechain["key_configured"] is True
    assert "api_key" not in repr(payload)
    assert "secret" not in freechain


def test_upsert_keeps_more_than_one_custom_profile() -> None:
    cfg = CodexCrewConfig()
    upsert_custom_profile(
        cfg,
        {"id": "one", "name": "One", "base_url": "https://one.test/v1"},
    )
    upsert_custom_profile(
        cfg,
        {"id": "two", "name": "Two", "base_url": "https://two.test/v1"},
    )
    assert [profile["id"] for profile in cfg.agent.openai_compatible_profiles] == ["one", "two"]


def test_routes_are_registered() -> None:
    app = web.Application()
    setup_openai_profile_routes(app)
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}
    assert ("GET", "/api/openai-profiles") in routes
    assert ("POST", "/api/openai-profiles") in routes
    assert ("PUT", "/api/openai-profiles/active") in routes
    assert ("DELETE", "/api/openai-profiles/{profile_id}") in routes


def test_active_profile_selection_refuses_a_missing_key(tmp_path) -> None:
    cfg = CodexCrewConfig()
    cfg.save = Mock()

    with (
        patch(
            "codex_crew.dashboard.handlers.openai_profiles._owner_only",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "codex_crew.dashboard.handlers.openai_profiles.CodexCrewConfig.load",
            return_value=cfg,
        ),
        patch("codex_crew.dashboard.handlers.openai_profiles.config_dir", return_value=tmp_path),
        patch(
            "codex_crew.dashboard.handlers.agents._get_config_lock",
            return_value=_AsyncLock(),
        ),
    ):
        response = asyncio.run(api_profiles_active(_Request()))

    assert response.status == 409
    assert (
        json.loads(response.text)["error"] == "An API key is required before selecting this profile"
    )
    cfg.save.assert_not_called()


def test_active_profile_selection_accepts_a_vault_key(tmp_path) -> None:
    cfg = CodexCrewConfig()
    cfg.save = Mock()
    SecretVault(tmp_path).set_sync("FREECHAIN_ACCESS_KEY", "configured-key")

    with (
        patch(
            "codex_crew.dashboard.handlers.openai_profiles._owner_only",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "codex_crew.dashboard.handlers.openai_profiles.CodexCrewConfig.load",
            return_value=cfg,
        ),
        patch("codex_crew.dashboard.handlers.openai_profiles.config_dir", return_value=tmp_path),
        patch(
            "codex_crew.dashboard.handlers.agents._get_config_lock",
            return_value=_AsyncLock(),
        ),
    ):
        response = asyncio.run(api_profiles_active(_Request()))

    assert response.status == 200
    assert json.loads(response.text)["active"] == "freechain"
    cfg.save.assert_called_once_with()
