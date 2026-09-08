"""Validated metadata for OpenAI-compatible Chat Completions providers.

Credentials never belong in these records. Each profile points at a SecretVault
entry by name, so configuration and API responses can be shared without exposing
the key itself.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
_SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")

FREECHAIN_PROFILE: dict[str, str | bool] = {
    "id": "freechain",
    "name": "FreeChain",
    "base_url": "http://127.0.0.1:4853/v1",
    "model": "auto",
    "secret_name": "FREECHAIN_ACCESS_KEY",
    "source_url": "https://github.com/BarnsL/FreeChain-API",
    "builtin": True,
}


def _loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_base_url(value: object) -> str:
    """Return a safe API root, allowing plain HTTP only on loopback."""
    if not isinstance(value, str):
        raise ValueError("base_url must be a string")
    clean = value.strip().rstrip("/")
    parsed = urlsplit(clean)
    if not parsed.netloc or parsed.scheme not in {"http", "https"}:
        raise ValueError("base_url must be an HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain a query or fragment")
    if parsed.scheme == "http" and not _loopback_host(parsed.hostname):
        raise ValueError("plain HTTP is allowed only for localhost providers")
    return clean


def normalize_profile(raw: object) -> dict[str, str]:
    """Validate one user-defined profile and return its persisted metadata."""
    if not isinstance(raw, Mapping):
        raise ValueError("profile must be an object")
    if "api_key" in raw:
        raise ValueError("api_key must be stored in the encrypted secret vault")

    profile_id = str(raw.get("id") or "").strip().lower()
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError("id must start with a letter and use lowercase letters, numbers, _ or -")
    if profile_id == FREECHAIN_PROFILE["id"]:
        raise ValueError("the built-in FreeChain profile cannot be replaced")

    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 80:
        raise ValueError("name is required and must be at most 80 characters")

    model = str(raw.get("model") or "auto").strip() or "auto"
    if len(model) > 200 or any(ord(char) < 32 for char in model):
        raise ValueError("model must be at most 200 printable characters")

    secret_name = str(raw.get("secret_name") or f"OPENAI_PROFILE_{profile_id.upper()}")
    secret_name = secret_name.strip().upper().replace("-", "_")
    if not _SECRET_NAME_RE.fullmatch(secret_name):
        raise ValueError("secret_name must be an uppercase environment-style name")

    return {
        "id": profile_id,
        "name": name,
        "base_url": validate_base_url(raw.get("base_url")),
        "model": model,
        "secret_name": secret_name,
    }


def normalize_profiles(raw: object) -> list[dict[str, str]]:
    """Validate a bounded list, keeping the first occurrence of each id."""
    if not isinstance(raw, list):
        return []
    profiles: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw[:50]:
        try:
            profile = normalize_profile(item)
        except ValueError:
            continue
        if profile["id"] in seen:
            continue
        seen.add(profile["id"])
        profiles.append(profile)
    return profiles


def profiles_with_defaults(raw: object) -> list[dict[str, Any]]:
    """Return FreeChain followed by every valid user-defined profile."""
    return [dict(FREECHAIN_PROFILE), *normalize_profiles(raw)]


def profile_by_id(raw: object, profile_id: object) -> dict[str, Any]:
    """Resolve a profile id, falling back to the built-in FreeChain entry."""
    wanted = str(profile_id or FREECHAIN_PROFILE["id"])
    return next(
        (profile for profile in profiles_with_defaults(raw) if profile["id"] == wanted),
        dict(FREECHAIN_PROFILE),
    )


__all__ = [
    "FREECHAIN_PROFILE",
    "normalize_profile",
    "normalize_profiles",
    "profile_by_id",
    "profiles_with_defaults",
    "validate_base_url",
]
