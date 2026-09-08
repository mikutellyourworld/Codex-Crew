"""OpenAI-compatible consultation stays opt-in, stateless, and key-isolated."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from codex_crew import agent, mcp_cleanup, mcp_consult, mcp_discovery, onboarding_import
from codex_crew.dashboard.handlers import model_consult
from codex_crew.link_unfurl import VettedUrl
from codex_crew.secrets import SecretVault
from codex_crew.validation import ValidationError

SERVER = "codexcrew-consult"
SUBCOMMAND = "mcp-consult"


async def _store_config(
    tmp_path,
    *,
    endpoint: str = "https://api.example.com/v1/chat/completions",
    model: str = "owner-model",
    api_key: str = "private-api-key",
) -> None:
    vault = SecretVault(tmp_path)
    await vault.set(
        model_consult.CONFIG_SECRET,
        json.dumps(
            {
                "version": 1,
                "endpoint": endpoint,
                "model": model,
                "api_key": api_key,
            }
        ),
    )


def test_consult_server_is_an_unapproved_opt_in_set() -> None:
    spec = agent._MANAGED_MCP_SERVERS[SERVER]
    assert spec.get("opt_in") is True
    assert "autoApprove" not in spec
    assert SERVER in mcp_cleanup.OPT_IN_BIN_MCP_SERVERS
    assert mcp_discovery._MANAGED_SERVER_SUBCOMMANDS[SERVER] == SUBCOMMAND
    assert mcp_discovery._MANAGED_SERVER_TOOL_MODULES[SERVER] == "codex_crew.mcp_consult"
    assert SERVER in onboarding_import._managed_mcp_names()
    from codex_crew import cli

    cli_source = inspect.getsource(cli)
    assert f'sub.add_parser("{SUBCOMMAND}")' in cli_source
    assert f'args.command == "{SUBCOMMAND}"' in cli_source
    built = agent.build_agent_config()
    assert SERVER not in built.get("mcpServers", {})
    assert f"@{SERVER}" not in built.get("tools", [])


def test_tool_forwards_only_the_prompt_and_returns_untrusted_text(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, str], str]] = []
    monkeypatch.setattr(mcp_consult, "_resolve_session_key", lambda: "dashboard:slot")

    def _post(path: str, body: dict[str, str], **kwargs: Any) -> dict[str, str]:
        calls.append((path, body, kwargs["session_key"]))
        return {"answer": "second opinion"}

    monkeypatch.setattr(mcp_consult, "_post", _post)
    assert mcp_consult._call_tool_inner("consult_model", {"prompt": "check this"}) == (
        "External model response (untrusted):\n\nsecond opinion"
    )
    assert calls == [("/api/model-consult", {"prompt": "check this"}, "dashboard:slot")]


def test_tool_validation_rejects_blank_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        mcp_consult._validate_args("consult_model", {"prompt": "   "})
    with pytest.raises(ValidationError):
        mcp_consult._validate_args(
            "consult_model", {"prompt": "hello", "endpoint": "https://example.com"}
        )


def test_internal_request_cap_covers_maximum_unicode_prompt() -> None:
    wire = json.dumps({"prompt": "😀" * model_consult.MAX_PROMPT_CHARS}).encode()
    assert len(wire) <= model_consult._MAX_REQUEST_BYTES


@pytest.mark.asyncio
async def test_connection_record_requires_https_port_443(tmp_path, monkeypatch) -> None:
    await _store_config(
        tmp_path,
        endpoint="https://api.example.com:80/v1/chat/completions",
    )
    monkeypatch.setattr(model_consult, "data_home", lambda: tmp_path)
    monkeypatch.setattr(
        model_consult,
        "vet_unfurl_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("blocked before DNS")),
    )

    with pytest.raises(model_consult._ConfigurationError) as exc_info:
        await model_consult._load_connection()
    assert exc_info.value.code == "consult_endpoint_blocked"


@pytest.mark.asyncio
async def test_gateway_keeps_key_out_of_prompt_and_answer(tmp_path, monkeypatch) -> None:
    api_key = "private-api-key"
    await _store_config(tmp_path, api_key=api_key)

    monkeypatch.setattr(model_consult, "data_home", lambda: tmp_path)
    monkeypatch.setattr(
        model_consult,
        "vet_unfurl_url",
        lambda _url: VettedUrl(
            url="https://api.example.com/v1/chat/completions",
            scheme="https",
            host="api.example.com",
            wire_host="api.example.com",
            port=443,
            ip="203.0.113.10",
            domain="api.example.com",
        ),
    )
    monkeypatch.setattr(
        model_consult,
        "redact_via_context",
        lambda text: text.replace("sensitive prompt", "[REDACTED]"),
    )
    sent: dict[str, str] = {}

    async def _post_completion(connection, prompt: str) -> str:
        sent["prompt"] = prompt
        assert connection.api_key == api_key
        return f"reflected {api_key}"

    monkeypatch.setattr(model_consult, "_post_completion", _post_completion)

    @web.middleware
    async def _internal(request: web.Request, handler):
        request["internal_auth"] = True
        return await handler(request)

    app = web.Application(middlewares=[_internal])
    app.router.add_post("/api/model-consult", model_consult.api_model_consult)
    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/model-consult", json={"prompt": f"sensitive prompt {api_key}"}
        )
        assert response.status == 200
        payload = await response.json()

    assert sent["prompt"] == "[REDACTED] [REDACTED]"
    assert api_key not in payload["answer"]
    assert payload["answer"] == "reflected [REDACTED]"


@pytest.mark.asyncio
async def test_total_deadline_covers_connection_loading_and_prevents_late_egress(
    monkeypatch,
) -> None:
    egress_started = False

    async def _slow_connection():
        await asyncio.Future()

    async def _unexpected_egress(*_args):
        nonlocal egress_started
        egress_started = True
        return "unexpected"

    monkeypatch.setattr(model_consult, "_TOTAL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(model_consult, "_load_connection", _slow_connection)
    monkeypatch.setattr(model_consult, "_post_completion", _unexpected_egress)

    @web.middleware
    async def _internal(request: web.Request, handler):
        request["internal_auth"] = True
        return await handler(request)

    app = web.Application(middlewares=[_internal])
    app.router.add_post("/api/model-consult", model_consult.api_model_consult)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/model-consult", json={"prompt": "hello"})
        assert response.status == 504
        assert (await response.json())["code"] == "consult_timeout"

    assert egress_started is False


@pytest.mark.asyncio
async def test_gateway_reasserts_internal_auth() -> None:
    app = web.Application()
    app.router.add_post("/api/model-consult", model_consult.api_model_consult)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/model-consult", json={"prompt": "hello"})
        assert response.status == 403
        assert await response.json() == {
            "error": "internal secret required",
            "code": "internal_secret_required",
        }


class _FakeContent:
    async def iter_chunked(self, _size: int):
        yield json.dumps({"choices": [{"message": {"content": "answer"}}]}).encode()


class _FakeResponse:
    status = 200
    content = _FakeContent()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_upstream_request_is_bounded_and_has_no_tool_surface(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeSession:
        def __init__(self, **kwargs: Any) -> None:
            captured["session"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def post(self, url: str, **kwargs: Any):
            captured["url"] = url
            captured["post"] = kwargs
            return _FakeResponse()

    monkeypatch.setattr(model_consult.aiohttp, "TCPConnector", lambda **kwargs: kwargs)
    monkeypatch.setattr(model_consult.aiohttp, "ClientSession", _FakeSession)
    connection = model_consult._Connection(
        VettedUrl(
            url="https://api.example.com/v1/chat/completions",
            scheme="https",
            host="api.example.com",
            wire_host="api.example.com",
            port=443,
            ip="203.0.113.10",
            domain="api.example.com",
        ),
        "owner-model",
        "private-api-key",
    )

    assert await model_consult._post_completion(connection, "question") == "answer"
    assert captured["session"]["headers"]["Authorization"] == "Bearer private-api-key"
    assert captured["post"] == {
        "json": {
            "model": "owner-model",
            "messages": [{"role": "user", "content": "question"}],
            "stream": False,
            "max_tokens": model_consult._MAX_OUTPUT_TOKENS,
        },
        "allow_redirects": False,
    }
