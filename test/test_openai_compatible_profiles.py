"""OpenAI-compatible profile validation and FreeChain defaults."""

from __future__ import annotations

import pytest

from codex_crew.openai_profiles import (
    FREECHAIN_PROFILE,
    normalize_profile,
    profiles_with_defaults,
)


def test_freechain_is_always_available_as_the_first_profile() -> None:
    profiles = profiles_with_defaults([])
    assert profiles[0] == FREECHAIN_PROFILE
    assert profiles[0]["id"] == "freechain"
    assert profiles[0]["base_url"] == "http://127.0.0.1:4853/v1"
    assert profiles[0]["model"] == "auto"
    assert profiles[0]["secret_name"] == "FREECHAIN_ACCESS_KEY"
    assert profiles[0]["source_url"] == "https://github.com/BarnsL/FreeChain-API"


def test_multiple_custom_profiles_are_retained() -> None:
    profiles = profiles_with_defaults(
        [
            {
                "id": "local-a",
                "name": "Local A",
                "base_url": "http://localhost:9001/v1",
                "model": "auto",
                "secret_name": "OPENAI_PROFILE_LOCAL_A",
            },
            {
                "id": "hosted-b",
                "name": "Hosted B",
                "base_url": "https://models.example.test/v1",
                "model": "provider-model",
                "secret_name": "OPENAI_PROFILE_HOSTED_B",
            },
        ]
    )
    assert [profile["id"] for profile in profiles] == ["freechain", "local-a", "hosted-b"]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://models.example.test/v1",
        "ftp://127.0.0.1/models",
        "https://user:pass@example.test/v1",
        "https://example.test/v1#fragment",
    ],
)
def test_profile_rejects_unsafe_provider_urls(base_url: str) -> None:
    with pytest.raises(ValueError):
        normalize_profile(
            {
                "id": "unsafe",
                "name": "Unsafe",
                "base_url": base_url,
                "model": "auto",
                "secret_name": "OPENAI_PROFILE_UNSAFE",
            }
        )


def test_profile_payload_never_accepts_an_inline_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        normalize_profile(
            {
                "id": "inline-key",
                "name": "Inline Key",
                "base_url": "https://models.example.test/v1",
                "model": "auto",
                "secret_name": "OPENAI_PROFILE_INLINE_KEY",
                "api_key": "must-not-enter-config",
            }
        )
