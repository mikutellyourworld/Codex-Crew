"""Strict-internal OpenAI-compatible consultation endpoint.

The API key and its destination stay together on the gateway side in one
atomically encrypted vault record. The MCP shim sends only a prompt and receives
only redacted text, so neither the model nor a pooled MCP subprocess can inspect
credentials.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

from codex_crew.config.paths import data_home
from codex_crew.dashboard.handlers._shared import read_bounded_json, read_capped_response
from codex_crew.dashboard.handlers.link_meta import _PinnedResolver
from codex_crew.link_unfurl import UnfurlRejected, VettedUrl, vet_unfurl_url
from codex_crew.platform import redact_via_context
from codex_crew.secrets import SecretVault

logger = logging.getLogger(__name__)

CONFIG_SECRET = "OPENAI_COMPAT_CONFIG"
_CONFIG_VERSION = 1

MAX_PROMPT_CHARS = 32_000
# mcp_core._post uses json.dumps()'s ASCII-safe default. One non-BMP character
# therefore occupies twelve bytes as a surrogate pair ("\\ud83d\\ude00"). Keep
# the route cap above the largest schema-valid payload plus fixed JSON framing so
# a prompt accepted by the MCP boundary cannot be rejected by its internal hop.
_MAX_REQUEST_BYTES = MAX_PROMPT_CHARS * 12 + 1_024
_MAX_ENDPOINT_CHARS = 2_048
_MAX_MODEL_CHARS = 256
_MAX_API_KEY_CHARS = 8_192
_MAX_RESPONSE_BYTES = 256 * 1024
_MAX_OUTPUT_TOKENS = 2_048
_UPSTREAM_TIMEOUT_SECONDS = 25
# This includes encrypted config read, blocking DNS vetting, request and response.
# It must remain below mcp_consult._GATEWAY_TIMEOUT_SECONDS (35s), so a cancelled
# tool call cannot finish DNS later and initiate paid egress after its caller left.
_TOTAL_TIMEOUT_SECONDS = 30
_REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class _Connection:
    endpoint: VettedUrl
    model: str
    api_key: str


class _ConfigurationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _UpstreamError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _RedactionError(Exception):
    def __init__(self, phase: str) -> None:
        self.phase = phase
        super().__init__(phase)


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


async def _load_connection() -> _Connection:
    """Read and validate one atomic encrypted connection record."""

    def _read():
        return SecretVault(data_home()).get(CONFIG_SECRET)

    try:
        config_secret = await asyncio.to_thread(_read)
    except Exception as exc:
        logger.warning(
            "model consult: encrypted settings could not be read (%s)",
            type(exc).__name__,
        )
        raise _ConfigurationError("consult_not_configured") from None
    if config_secret is None:
        raise _ConfigurationError("consult_not_configured")

    try:
        record = json.loads(config_secret.reveal())
    except (TypeError, ValueError, json.JSONDecodeError):
        raise _ConfigurationError("consult_not_configured") from None
    if not isinstance(record, dict) or record.get("version") != _CONFIG_VERSION:
        raise _ConfigurationError("consult_not_configured")

    endpoint = record.get("endpoint")
    model = record.get("model")
    api_key = record.get("api_key")
    if not isinstance(endpoint, str) or not isinstance(model, str) or not isinstance(api_key, str):
        raise _ConfigurationError("consult_not_configured")
    endpoint = endpoint.strip()
    model = model.strip()
    api_key = api_key.strip()
    if (
        not model
        or len(model) > _MAX_MODEL_CHARS
        or _has_control_characters(model)
        or len(api_key) < 8
        or len(api_key) > _MAX_API_KEY_CHARS
        or _has_control_characters(api_key)
    ):
        raise _ConfigurationError("consult_not_configured")

    try:
        parts = urlsplit(endpoint)
        explicit_port = parts.port
    except ValueError:
        raise _ConfigurationError("consult_endpoint_blocked") from None
    if (
        not endpoint
        or len(endpoint) > _MAX_ENDPOINT_CHARS
        or parts.scheme.lower() != "https"
        or explicit_port not in (None, 443)
        or parts.query
        or parts.fragment
        or not parts.path.rstrip("/").endswith("/chat/completions")
    ):
        raise _ConfigurationError("consult_endpoint_blocked")

    try:
        vetted = await asyncio.to_thread(vet_unfurl_url, endpoint)
    except UnfurlRejected:
        raise _ConfigurationError("consult_endpoint_blocked") from None
    if vetted.scheme != "https" or vetted.port != 443:
        raise _ConfigurationError("consult_endpoint_blocked")
    return _Connection(vetted, model, api_key)


async def _post_completion(connection: _Connection, prompt: str) -> str:
    """POST one bounded, DNS-pinned chat-completions request."""
    connector = aiohttp.TCPConnector(
        resolver=_PinnedResolver(
            connection.endpoint.wire_host,
            connection.endpoint.ip,
            connection.endpoint.port,
        ),
        limit=1,
        family=socket.AF_UNSPEC,
    )
    headers = {
        "Authorization": f"Bearer {connection.api_key}",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "CodexCrew/model-consult",
    }
    request_body = {
        "model": connection.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": _MAX_OUTPUT_TOKENS,
    }

    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=_UPSTREAM_TIMEOUT_SECONDS),
            headers=headers,
            auto_decompress=False,
        ) as session:
            async with session.post(
                connection.endpoint.url,
                json=request_body,
                allow_redirects=False,
            ) as response:
                body = await read_capped_response(response, _MAX_RESPONSE_BYTES)
                status = response.status
    except asyncio.TimeoutError:
        raise _UpstreamError("consult_timeout") from None
    except (aiohttp.ClientError, OSError) as exc:
        logger.warning("model consult: upstream request failed (%s)", type(exc).__name__)
        raise _UpstreamError("consult_upstream_unavailable") from None

    if len(body) > _MAX_RESPONSE_BYTES:
        raise _UpstreamError("consult_response_too_large")
    if status != 200:
        raise _UpstreamError("consult_upstream_http")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _UpstreamError("consult_invalid_response") from None
    if not isinstance(payload, dict):
        raise _UpstreamError("consult_invalid_response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise _UpstreamError("consult_invalid_response")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise _UpstreamError("consult_invalid_response")
    answer = message.get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise _UpstreamError("consult_invalid_response")
    return answer


async def _consult(prompt: str) -> str:
    """Run the complete bounded consultation and return redacted text."""
    connection = await _load_connection()
    try:
        outbound_prompt = redact_via_context(prompt.replace(connection.api_key, _REDACTED))
    except Exception as exc:
        logger.warning("model consult: prompt redaction failed (%s)", type(exc).__name__)
        raise _RedactionError("prompt") from None

    answer = await _post_completion(connection, outbound_prompt)
    try:
        return redact_via_context(answer.replace(connection.api_key, _REDACTED))
    except Exception as exc:
        logger.warning("model consult: answer redaction failed (%s)", type(exc).__name__)
        raise _RedactionError("answer") from None


async def api_model_consult(request: web.Request) -> web.Response:
    """POST /api/model-consult — return one redacted external-model answer."""
    if request.get("internal_auth") is not True:
        return web.json_response(
            {"error": "internal secret required", "code": "internal_secret_required"},
            status=403,
        )

    body, body_error = await read_bounded_json(request, max_bytes=_MAX_REQUEST_BYTES)
    if body_error is not None:
        return body_error
    assert body is not None
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        return web.json_response(
            {
                "error": "prompt must be non-empty text within the size limit",
                "code": "consult_invalid_prompt",
            },
            status=400,
        )

    try:
        answer = await asyncio.wait_for(_consult(prompt), timeout=_TOTAL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return web.json_response(
            {"error": "the external model timed out", "code": "consult_timeout"},
            status=504,
        )
    except _ConfigurationError as exc:
        if exc.code == "consult_endpoint_blocked":
            return web.json_response(
                {
                    "error": "the configured endpoint is not an allowed public HTTPS chat-completions URL",
                    "code": "consult_endpoint_blocked",
                },
                status=503,
            )
        return web.json_response(
            {
                "error": "OpenAI-compatible consultation is not configured",
                "code": "consult_not_configured",
            },
            status=503,
        )
    except _RedactionError as exc:
        if exc.phase == "prompt":
            return web.json_response(
                {
                    "error": "prompt could not be safely prepared",
                    "code": "consult_redaction_failed",
                },
                status=500,
            )
        return web.json_response(
            {
                "error": "the external response could not be safely returned",
                "code": "consult_redaction_failed",
            },
            status=502,
        )
    except _UpstreamError as exc:
        if exc.code == "consult_timeout":
            return web.json_response(
                {"error": "the external model timed out", "code": "consult_timeout"},
                status=504,
            )
        messages = {
            "consult_upstream_unavailable": "the external model is unavailable",
            "consult_upstream_http": "the external model rejected the request",
            "consult_response_too_large": "the external model response exceeded the size limit",
            "consult_invalid_response": "the external model returned an invalid response",
        }
        return web.json_response(
            {
                "error": messages.get(exc.code, "external model consultation failed"),
                "code": exc.code,
            },
            status=502,
        )
    return web.json_response({"answer": answer})
