"""Wire-level proof for the bundled Chat Completions ACP adapter."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from aiohttp import web

from codex_crew.acp_adapters.openai_compatible_server import (
    OpenAICompatibleAcpServer,
    _safe_error,
    build_mcp_child_env,
    build_chat_completions_url,
    extract_prompt_text,
    sanitize_tool_name,
)

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_refuses_to_start_without_an_access_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODEXCREW_OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="access key is not configured"):
        OpenAICompatibleAcpServer()


def test_adapter_helpers_normalize_urls_prompts_and_tool_names() -> None:
    assert (
        build_chat_completions_url("https://example.test/v1/")
        == "https://example.test/v1/chat/completions"
    )
    assert (
        build_chat_completions_url("https://example.test/v1/chat/completions")
        == "https://example.test/v1/chat/completions"
    )
    assert (
        extract_prompt_text([{"type": "text", "text": "hello"}, {"type": "image", "url": "x"}])
        == "hello"
    )
    assert sanitize_tool_name("mcp.server/tool") == "mcp_server_tool"


def test_provider_error_redacts_credentials() -> None:
    message = _safe_error(
        RuntimeError("request failed with sk-proj-abcdefghijklmnopqrstuvwxyz123456")
    )

    assert "sk-proj-" not in message


def test_mcp_child_env_scrubs_inherited_provider_and_gateway_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEXCREW_OPENAI_API_KEY", "provider-secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "gateway-secret")
    monkeypatch.setenv("SAFE_PARENT_VALUE", "keep-me")

    env = build_mcp_child_env(
        {"env": [{"name": "MCP_SERVER_TOKEN", "value": "explicit-mcp-secret"}]}
    )

    assert "CODEXCREW_OPENAI_API_KEY" not in env
    assert "SLACK_BOT_TOKEN" not in env
    assert env["SAFE_PARENT_VALUE"] == "keep-me"
    assert env["MCP_SERVER_TOKEN"] == "explicit-mcp-secret"


@pytest.mark.asyncio
async def test_real_stdio_adapter_calls_chat_completions_and_streams_acp_update() -> None:
    seen: dict[str, object] = {}

    async def completion(request: web.Request) -> web.Response:
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = await request.json()
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)
        await response.write(
            b'data: {"model":"gpt-5.6-sol","choices":[{"delta":{"content":"adapter works"}}]}\n\n'
        )
        await response.write(
            b'data: {"model":"gpt-5.6-sol","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13,"prompt_tokens_details":{"cached_tokens":4}}}\n\n'
        )
        await response.write(b"data: [DONE]\n\n")
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", completion)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "CODEXCREW_OPENAI_BASE_URL": f"http://127.0.0.1:{port}/v1",
            "CODEXCREW_OPENAI_MODEL": "auto",
            "CODEXCREW_OPENAI_API_KEY": "test-local-key",
        }
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "codex_crew.acp_adapters.openai_compatible_server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    async def request(request_id: int, method: str, params: dict) -> list[dict]:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(
            (
                json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
                + "\n"
            ).encode()
        )
        await process.stdin.drain()
        messages: list[dict] = []
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert line, "adapter exited before replying"
            message = json.loads(line)
            messages.append(message)
            if message.get("id") == request_id:
                return messages

    try:
        initialized = await request(1, "initialize", {"protocolVersion": 1})
        assert initialized[-1]["result"]["protocolVersion"] == 1
        created = await request(2, "session/new", {"cwd": os.getcwd(), "mcpServers": []})
        session_id = created[-1]["result"]["sessionId"]
        prompted = await request(
            3,
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "say hi"}]},
        )
        updates = [message for message in prompted if message.get("method") == "session/update"]
        text_update = next(
            message["params"]["update"]
            for message in updates
            if message["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
        )
        usage_update = next(
            message["params"]["update"]
            for message in updates
            if message["params"]["update"]["sessionUpdate"] == "usage_update"
        )
        assert text_update["content"]["text"] == "adapter works"
        assert usage_update == {
            "sessionUpdate": "usage_update",
            "used": 13,
            "size": 272000,
        }
        assert prompted[-1]["result"]["stopReason"] == "end_turn"
        assert prompted[-1]["result"]["usage"] == {
            "totalTokens": 13,
            "inputTokens": 6,
            "cachedReadTokens": 4,
            "outputTokens": 3,
            "cachedWriteTokens": 0,
        }
        assert seen["authorization"] == "Bearer test-local-key"
        assert seen["body"] == {
            "model": "auto",
            "messages": [{"role": "user", "content": "say hi"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    finally:
        if process.stdin is not None:
            process.stdin.close()
        await asyncio.wait_for(process.wait(), timeout=10)
        await runner.cleanup()
