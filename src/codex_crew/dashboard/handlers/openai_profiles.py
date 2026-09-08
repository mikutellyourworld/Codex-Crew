"""Owner-only management of OpenAI-compatible provider profiles."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from codex_crew.config.loader import CodexCrewConfig, config_dir
from codex_crew.dashboard.handlers.secrets import _owner_only
from codex_crew.openai_profiles import (
    FREECHAIN_PROFILE,
    normalize_profile,
    profiles_with_defaults,
)
from codex_crew.secrets import SecretVault


def profiles_payload(cfg: CodexCrewConfig, key_names: set[str]) -> dict[str, Any]:
    """Return safe profile metadata with only a credential-presence bit."""
    profiles: list[dict[str, Any]] = []
    for raw in profiles_with_defaults(cfg.agent.openai_compatible_profiles):
        profile = {
            "id": raw["id"],
            "name": raw["name"],
            "base_url": raw["base_url"],
            "model": raw["model"],
            "builtin": bool(raw.get("builtin")),
            "key_configured": str(raw["secret_name"]) in key_names,
        }
        if raw.get("source_url"):
            profile["source_url"] = raw["source_url"]
        profiles.append(profile)
    active_ids = {str(profile["id"]) for profile in profiles}
    active = cfg.agent.openai_compatible_profile
    if active not in active_ids:
        active = str(FREECHAIN_PROFILE["id"])
    return {"active": active, "profiles": profiles}


def _profile_key_configured(vault: SecretVault, profile: dict[str, Any]) -> bool:
    """Check key presence without exposing key material to config or responses."""
    try:
        secret = vault.get(str(profile["secret_name"]))
    except (OSError, ValueError):
        return False
    return bool(secret is not None and secret.reveal().strip())


def upsert_custom_profile(cfg: CodexCrewConfig, raw: object) -> dict[str, str]:
    """Insert or replace one custom profile without disturbing its siblings."""
    profile = normalize_profile(raw)
    existing = [
        item for item in cfg.agent.openai_compatible_profiles if item.get("id") != profile["id"]
    ]
    cfg.agent.openai_compatible_profiles = [*existing, profile]
    return profile


async def _refresh_defaults(request: web.Request) -> None:
    state = request.app.get("state")
    sessions = getattr(state, "sessions", None)
    if sessions is not None:
        await sessions.refresh_defaults()


async def api_profiles_get(request: web.Request) -> web.Response:
    denied = await _owner_only(request, "openai_profiles_list")
    if denied is not None:
        return denied
    cfg, names = await asyncio.gather(
        asyncio.to_thread(CodexCrewConfig.load),
        asyncio.to_thread(SecretVault(config_dir()).list_names),
    )
    return web.json_response(profiles_payload(cfg, set(names)))


async def api_profiles_set(request: web.Request) -> web.Response:
    denied = await _owner_only(request, "openai_profiles_set")
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "Request body must be an object"}, status=400)

    api_key = body.pop("api_key", None)
    if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
        return web.json_response({"error": "API key must be a non-empty string"}, status=400)
    if "active" in body and not isinstance(body["active"], bool):
        return web.json_response({"error": "active must be a boolean"}, status=400)
    profile_id = str(body.get("id") or "").strip().lower()
    activate = body.get("active", True)
    vault = SecretVault(config_dir())

    from codex_crew.dashboard.handlers.agents import _get_config_lock

    async with _get_config_lock():
        cfg = await asyncio.to_thread(CodexCrewConfig.load)
        changed = False
        profile: dict[str, Any]
        if profile_id == FREECHAIN_PROFILE["id"]:
            profile = dict(FREECHAIN_PROFILE)
        else:
            try:
                profile = upsert_custom_profile(cfg, body)
            except ValueError as exc:
                return web.json_response({"error": str(exc)}, status=400)
            changed = True
        if (
            activate
            and api_key is None
            and not await asyncio.to_thread(_profile_key_configured, vault, profile)
        ):
            return web.json_response(
                {"error": "An API key is required before selecting this profile"},
                status=409,
            )
        if api_key is not None:
            await vault.set(str(profile["secret_name"]), api_key.strip())
        if activate:
            cfg.agent.openai_compatible_profile = str(profile["id"])
            changed = True
        if changed:
            await asyncio.to_thread(cfg.save)

    await _refresh_defaults(request)
    names = await asyncio.to_thread(vault.list_names)
    return web.json_response(profiles_payload(cfg, set(names)))


async def api_profiles_active(request: web.Request) -> web.Response:
    denied = await _owner_only(request, "openai_profiles_select")
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    if not isinstance(body, dict) or not isinstance(body.get("id"), str):
        return web.json_response({"error": "Profile id is required"}, status=400)
    wanted = body["id"].strip().lower()

    from codex_crew.dashboard.handlers.agents import _get_config_lock

    async with _get_config_lock():
        cfg = await asyncio.to_thread(CodexCrewConfig.load)
        profiles = profiles_with_defaults(cfg.agent.openai_compatible_profiles)
        profile = next((item for item in profiles if str(item["id"]) == wanted), None)
        if profile is None:
            return web.json_response({"error": "Profile not found"}, status=404)
        vault = SecretVault(config_dir())
        if not await asyncio.to_thread(_profile_key_configured, vault, profile):
            return web.json_response(
                {"error": "An API key is required before selecting this profile"},
                status=409,
            )
        cfg.agent.openai_compatible_profile = wanted
        await asyncio.to_thread(cfg.save)
    await _refresh_defaults(request)
    names = await asyncio.to_thread(vault.list_names)
    return web.json_response(profiles_payload(cfg, set(names)))


async def api_profiles_delete(request: web.Request) -> web.Response:
    denied = await _owner_only(request, "openai_profiles_delete")
    if denied is not None:
        return denied
    profile_id = request.match_info["profile_id"].strip().lower()
    if profile_id == FREECHAIN_PROFILE["id"]:
        return web.json_response(
            {"error": "The built-in FreeChain profile cannot be deleted"}, status=409
        )

    from codex_crew.dashboard.handlers.agents import _get_config_lock

    async with _get_config_lock():
        cfg = await asyncio.to_thread(CodexCrewConfig.load)
        target = next(
            (item for item in cfg.agent.openai_compatible_profiles if item.get("id") == profile_id),
            None,
        )
        if target is None:
            return web.json_response({"error": "Profile not found"}, status=404)
        cfg.agent.openai_compatible_profiles = [
            item for item in cfg.agent.openai_compatible_profiles if item.get("id") != profile_id
        ]
        if cfg.agent.openai_compatible_profile == profile_id:
            cfg.agent.openai_compatible_profile = str(FREECHAIN_PROFILE["id"])
        await asyncio.to_thread(cfg.save)

    await SecretVault(config_dir()).delete(str(target["secret_name"]))
    await _refresh_defaults(request)
    names = await asyncio.to_thread(SecretVault(config_dir()).list_names)
    return web.json_response(profiles_payload(cfg, set(names)))


def setup_openai_profile_routes(app: web.Application) -> None:
    app.router.add_get("/api/openai-profiles", api_profiles_get)
    app.router.add_post("/api/openai-profiles", api_profiles_set)
    app.router.add_put("/api/openai-profiles/active", api_profiles_active)
    app.router.add_delete("/api/openai-profiles/{profile_id}", api_profiles_delete)


__all__ = ["profiles_payload", "setup_openai_profile_routes", "upsert_custom_profile"]
