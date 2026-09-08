"""Selected OpenAI-compatible profiles reach the bundled ACP adapter safely."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codex_crew.config.loader import CodexCrewConfig
from codex_crew.secrets import SecretVault


def _cfg() -> CodexCrewConfig:
    cfg = CodexCrewConfig()
    cfg.agent.acp_backend = "openai_compatible"
    cfg.agent.member_acp_backend = "openai_compatible"
    cfg.agent.model = "global-model"
    return cfg


def test_freechain_is_the_default_profile_and_reads_its_key_from_the_vault(tmp_path) -> None:
    SecretVault(tmp_path).set_sync("FREECHAIN_ACCESS_KEY", "local-key")
    cfg = _cfg()
    with patch("codex_crew.config.loader.config_dir", return_value=tmp_path):
        provider = cfg.create_provider_factory()(session_key="test:freechain")

    assert provider.client._acp_backend == "openai_compatible"
    assert provider.client._model == "auto"
    assert provider.client._extra_env == {
        "CODEXCREW_OPENAI_BASE_URL": "http://127.0.0.1:4853/v1",
        "CODEXCREW_OPENAI_MODEL": "auto",
        "CODEXCREW_OPENAI_PROFILE_ID": "freechain",
        "CODEXCREW_OPENAI_API_KEY": "local-key",
    }


def test_custom_profile_selection_keeps_multiple_profiles_and_caller_env(tmp_path) -> None:
    cfg = _cfg()
    cfg.agent.openai_compatible_profile = "second"
    cfg.agent.openai_compatible_profiles = [
        {
            "id": "first",
            "name": "First",
            "base_url": "https://first.example/v1",
            "model": "first-model",
            "secret_name": "OPENAI_PROFILE_FIRST",
        },
        {
            "id": "second",
            "name": "Second",
            "base_url": "https://second.example/v1",
            "model": "second-model",
            "secret_name": "OPENAI_PROFILE_SECOND",
        },
    ]
    SecretVault(tmp_path).set_sync("OPENAI_PROFILE_SECOND", "second-key")
    with patch("codex_crew.config.loader.config_dir", return_value=tmp_path):
        provider = cfg.create_provider_factory()(
            session_key="test:second", extra_env={"HTTPS_PROXY": "http://localhost:9"}
        )

    assert provider.client._model == "second-model"
    assert provider.client._extra_env["HTTPS_PROXY"] == "http://localhost:9"
    assert provider.client._extra_env["CODEXCREW_OPENAI_BASE_URL"] == "https://second.example/v1"
    assert provider.client._extra_env["CODEXCREW_OPENAI_API_KEY"] == "second-key"


def test_each_provider_creation_reads_the_current_vault_value(tmp_path) -> None:
    vault = SecretVault(tmp_path)
    vault.set_sync("FREECHAIN_ACCESS_KEY", "first-key")
    cfg = _cfg()
    with patch("codex_crew.config.loader.config_dir", return_value=tmp_path):
        factory = cfg.create_provider_factory()
        first = factory(session_key="test:first")
        vault.set_sync("FREECHAIN_ACCESS_KEY", "rotated-key")
        second = factory(session_key="test:second")

    assert first.client._extra_env["CODEXCREW_OPENAI_API_KEY"] == "first-key"
    assert second.client._extra_env["CODEXCREW_OPENAI_API_KEY"] == "rotated-key"


def test_api_keys_never_serialize_into_configuration() -> None:
    cfg = _cfg()
    cfg.agent.openai_compatible_profiles = [
        {
            "id": "custom",
            "name": "Custom",
            "base_url": "https://example.test/v1",
            "model": "model",
            "secret_name": "OPENAI_PROFILE_CUSTOM",
        }
    ]
    serialized = cfg.to_dict()
    assert "api_key" not in repr(serialized)
    assert (
        serialized["agent"]["openai_compatible_profiles"][0]["secret_name"]
        == "OPENAI_PROFILE_CUSTOM"
    )


def test_provider_creation_refuses_an_unconfigured_api_key(tmp_path) -> None:
    cfg = _cfg()

    with patch("codex_crew.config.loader.config_dir", return_value=tmp_path):
        with pytest.raises(ValueError, match="requires an API key"):
            cfg.create_provider_factory()(session_key="test:missing-key")
