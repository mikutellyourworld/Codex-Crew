"""ACP stdio server backed by an OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from codex_crew import model_registry
from codex_crew.sandbox import scrub_agent_subprocess_env
from codex_crew.security import redact_credentials, redact_exfiltration_urls

PROTOCOL_VERSION = 1
DEFAULT_OPENAI_MODEL = "auto"
_ADAPTER_NAME = "codexcrew-openai-compatible"
_MAX_TOOL_LOOPS = 50
_MAX_ERROR_CHARS = 1200
_ALLOW_OPTIONS = frozenset({"allow", "allow_once", "allow_always"})
_TOOL_NAME_RE = re.compile(r"[^A-Za-z0-9_-]")

logger = logging.getLogger(__name__)


def build_chat_completions_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    return clean if clean.endswith("/chat/completions") else f"{clean}/chat/completions"


def sanitize_tool_name(name: str) -> str:
    return _TOOL_NAME_RE.sub("_", name)[:64] or "tool"


def extract_prompt_text(prompt: object) -> str:
    if isinstance(prompt, str):
        return prompt
    if not isinstance(prompt, list):
        return ""
    return "".join(
        str(block.get("text", ""))
        for block in prompt
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _response(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _session_update(session_id: str, update: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": session_id, "update": update},
    }


def _safe_error(exc: BaseException, api_key: str = "") -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message, _credential_warnings = redact_credentials(message)
    message, _url_warnings = redact_exfiltration_urls(message)
    return message[:_MAX_ERROR_CHARS]


def _mcp_content_text(result: object) -> str:
    if not isinstance(result, dict):
        return json.dumps(result, default=str)
    content = result.get("content")
    if not isinstance(content, list):
        return json.dumps(result, default=str)
    return "\n".join(
        (
            str(block.get("text", ""))
            if isinstance(block, dict) and block.get("type") == "text"
            else json.dumps(block, default=str)
        )
        for block in content
    )


def build_mcp_child_env(entry: dict[str, Any]) -> dict[str, str]:
    """Build an MCP environment without inherited agent-provider credentials."""
    env = scrub_agent_subprocess_env(dict(os.environ))
    env = {key: value for key, value in env.items() if not key.startswith("CODEXCREW_OPENAI_")}
    raw_env = entry.get("env") or []
    if isinstance(raw_env, dict):
        env.update({str(key): str(value) for key, value in raw_env.items()})
    elif isinstance(raw_env, list):
        for pair in raw_env:
            if isinstance(pair, dict) and pair.get("name"):
                env[str(pair["name"])] = str(pair.get("value", ""))
    return env


class _McpProcess:
    def __init__(self, name: str, entry: dict[str, Any]) -> None:
        self.name = name
        self.entry = entry
        self.process: asyncio.subprocess.Process | None = None
        self._pending: dict[object, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> list[dict[str, Any]]:
        command = self.entry.get("command")
        if not isinstance(command, str) or not command:
            raise RuntimeError("MCP entry has no command")
        args = [str(arg) for arg in self.entry.get("args") or []]
        env = build_mcp_child_env(self.entry)
        self.process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": _ADAPTER_NAME, "version": "1"},
            },
        )
        await self.notify("notifications/initialized", {})
        listed = await self.request("tools/list", {})
        tools = listed.get("tools")
        return tools if isinstance(tools, list) else []

    async def _write(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise RuntimeError(f"MCP server {self.name!r} is not running")
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        async with self._write_lock:
            process.stdin.write(data)
            await process.stdin.drain()

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            message = await asyncio.wait_for(future, timeout=30)
        finally:
            self._pending.pop(request_id, None)
        if isinstance(message.get("error"), dict):
            raise RuntimeError(str(message["error"].get("message") or "MCP request failed"))
        result = message.get("result")
        return result if isinstance(result, dict) else {}

    async def _read_loop(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            if "id" in message and "method" not in message:
                future = self._pending.get(message.get("id"))
                if future is not None and not future.done():
                    future.set_result(message)
            elif "id" in message and message.get("method"):
                await self._write(_error(message.get("id"), -32601, "client method not supported"))
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RuntimeError(f"MCP server {self.name!r} exited"))

    async def _drain_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        while await process.stderr.readline():
            pass

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        return _mcp_content_text(
            await self.request("tools/call", {"name": name, "arguments": arguments})
        )

    async def close(self) -> None:
        process = self.process
        if process is not None and process.returncode is None:
            process.terminate()
            with contextlib.suppress(asyncio.TimeoutError, ProcessLookupError):
                await asyncio.wait_for(process.wait(), timeout=3)
            if process.returncode is None:
                process.kill()
                await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        self.process = None


class McpToolBridge:
    def __init__(self) -> None:
        self._processes: list[_McpProcess] = []
        self._routes: dict[str, tuple[_McpProcess, str, str]] = {}
        self.openai_tools: list[dict[str, Any]] = []

    async def connect(self, entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            server_name = str(entry.get("name") or "mcp")
            process = _McpProcess(server_name, entry)
            try:
                tools = await process.start()
            except Exception as exc:
                logger.warning("MCP server %s unavailable: %s", server_name, _safe_error(exc))
                await process.close()
                continue
            self._processes.append(process)
            for tool in tools:
                if not isinstance(tool, dict) or not tool.get("name"):
                    continue
                original = str(tool["name"])
                public = sanitize_tool_name(original)
                if public in self._routes:
                    logger.warning("MCP tool name collision on %s; keeping first", public)
                    continue
                self._routes[public] = (process, original, server_name)
                schema = tool.get("inputSchema")
                self.openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": public,
                            "description": str(tool.get("description") or ""),
                            "parameters": (
                                schema
                                if isinstance(schema, dict)
                                else {"type": "object", "properties": {}}
                            ),
                        },
                    }
                )

    def identity(self, public_name: str) -> tuple[str, str]:
        route = self._routes.get(public_name)
        return (route[2], route[1]) if route else ("", "")

    async def call(self, public_name: str, arguments: dict[str, Any]) -> str:
        route = self._routes.get(public_name)
        if route is None:
            return f"error: unknown tool {public_name!r}"
        return await route[0].call(route[1], arguments)

    async def close(self) -> None:
        await asyncio.gather(
            *(process.close() for process in self._processes), return_exceptions=True
        )
        self._processes.clear()


@dataclass
class _Session:
    id: str
    cwd: str
    bridge: McpToolBridge
    model: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)


class _ToolCallAccumulator:
    def __init__(self) -> None:
        self._calls: dict[int, dict[str, Any]] = {}

    def add(self, raw: object) -> None:
        if not isinstance(raw, dict):
            return
        raw_index = raw.get("index")
        index = int(raw_index) if isinstance(raw_index, int) else 0
        call = self._calls.setdefault(
            index,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if raw.get("id"):
            call["id"] = str(raw["id"])
        function = raw.get("function")
        if isinstance(function, dict):
            if function.get("name"):
                call["function"]["name"] += str(function["name"])
            if function.get("arguments"):
                call["function"]["arguments"] += str(function["arguments"])

    def finish(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for index in sorted(self._calls):
            call = self._calls[index]
            if call["function"]["name"]:
                call["id"] = call["id"] or str(uuid.uuid4())
                result.append(call)
        return result


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value != value or value in (float("inf"), float("-inf")):
        return None
    return int(value)


@dataclass(frozen=True)
class _CompletionUsage:
    input_tokens: int
    output_tokens: int
    cached_read_tokens: int
    total_tokens: int
    model: str = ""
    context_window: int = 0

    def add(self, other: "_CompletionUsage") -> "_CompletionUsage":
        return _CompletionUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_read_tokens=self.cached_read_tokens + other.cached_read_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            model=other.model or self.model,
            context_window=other.context_window or self.context_window,
        )

    def prompt_result(self) -> dict[str, int]:
        return {
            "totalTokens": self.total_tokens,
            "inputTokens": self.input_tokens,
            "cachedReadTokens": self.cached_read_tokens,
            "outputTokens": self.output_tokens,
            "cachedWriteTokens": 0,
        }


def parse_completion_usage(
    payload: object,
    *,
    fallback_model: str = "",
) -> _CompletionUsage | None:
    """Normalize exact Chat Completions usage without inventing token counts."""
    if not isinstance(payload, dict):
        return None
    raw_usage = payload.get("usage")
    if not isinstance(raw_usage, dict):
        return None

    prompt_tokens = _nonnegative_int(raw_usage.get("prompt_tokens", raw_usage.get("input_tokens")))
    output_tokens = _nonnegative_int(
        raw_usage.get("completion_tokens", raw_usage.get("output_tokens"))
    )
    supplied_total = _nonnegative_int(raw_usage.get("total_tokens"))
    if prompt_tokens is None and output_tokens is None and supplied_total is None:
        return None

    details = raw_usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    cached_read = (
        _nonnegative_int(details.get("cached_tokens", raw_usage.get("cached_read_tokens"))) or 0
    )
    prompt_total = prompt_tokens or 0
    cached_read = min(cached_read, prompt_total)
    output = output_tokens or 0
    total = supplied_total if supplied_total is not None else prompt_total + output
    model = str(payload.get("model") or fallback_model)

    context_window = (
        _nonnegative_int(
            raw_usage.get(
                "context_window_tokens",
                raw_usage.get("context_window", payload.get("context_window")),
            )
        )
        or 0
    )
    if not context_window and model and model_registry.has_known_window(model):
        context_window = int(model_registry.model_window(model) or 0)

    return _CompletionUsage(
        input_tokens=max(prompt_total - cached_read, 0),
        output_tokens=output,
        cached_read_tokens=cached_read,
        total_tokens=total,
        model=model,
        context_window=context_window,
    )


class OpenAICompatibleAcpServer:
    def __init__(self) -> None:
        self._write_lock = asyncio.Lock()
        self._pending: dict[object, asyncio.Future[dict[str, Any]]] = {}
        self._sessions: dict[str, _Session] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._closing = False
        self._base_url = os.environ.get("CODEXCREW_OPENAI_BASE_URL", "").strip()
        self._default_model = (
            os.environ.get("CODEXCREW_OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
            or DEFAULT_OPENAI_MODEL
        )
        self._api_key = os.environ.get("CODEXCREW_OPENAI_API_KEY", "").strip()
        if not self._api_key:
            raise RuntimeError("OpenAI-compatible provider access key is not configured")
        self._http: aiohttp.ClientSession | None = None

    async def _send(self, message: dict[str, Any]) -> None:
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        async with self._write_lock:
            await asyncio.to_thread(_write_protocol, data)

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            return await future
        finally:
            self._pending.pop(request_id, None)

    async def serve(self) -> None:
        while not self._closing:
            line = await asyncio.to_thread(sys.stdin.buffer.readline)
            if not line:
                break
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("method"):
                task = asyncio.create_task(self._dispatch(message))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            elif "id" in message:
                future = self._pending.get(message.get("id"))
                if future is not None and not future.done():
                    future.set_result(message)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        try:
            if method == "initialize":
                await self._send(
                    _response(
                        request_id,
                        {
                            "protocolVersion": PROTOCOL_VERSION,
                            "agentInfo": {"name": _ADAPTER_NAME, "version": "1"},
                            "agentCapabilities": {
                                "loadSession": False,
                                "promptCapabilities": {"image": False},
                            },
                        },
                    )
                )
            elif method == "session/new":
                await self._send(_response(request_id, await self._new_session(params)))
            elif method == "session/prompt":
                await self._prompt(request_id, params)
            elif method in {"session/set_model", "session/set_config_option"}:
                session = self._sessions.get(str(params.get("sessionId") or ""))
                model = params.get("modelId") or (
                    params.get("value") if params.get("configId") == "model" else None
                )
                if session is not None and model:
                    session.model = str(model)
                await self._send(_response(request_id, {}))
            elif method == "session/set_mode":
                await self._send(_response(request_id, {}))
            elif method == "session/cancel":
                session = self._sessions.get(str(params.get("sessionId") or ""))
                if session is not None:
                    session.cancel.set()
            elif request_id is not None:
                await self._send(_error(request_id, -32601, f"method not found: {method}"))
        except Exception as exc:
            logger.exception("ACP method %s failed", method)
            if request_id is not None:
                await self._send(_error(request_id, -32603, _safe_error(exc, self._api_key)))

    async def _new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        bridge = McpToolBridge()
        raw_servers = params.get("mcpServers")
        servers = [entry for entry in raw_servers or [] if isinstance(entry, dict)]
        await bridge.connect(servers)
        self._sessions[session_id] = _Session(
            id=session_id,
            cwd=str(params.get("cwd") or ""),
            bridge=bridge,
            model=self._default_model,
        )
        return {
            "sessionId": session_id,
            "models": {
                "currentModelId": self._default_model,
                "availableModels": [{"modelId": self._default_model, "name": self._default_model}],
            },
        }

    async def _prompt(self, request_id: object, params: dict[str, Any]) -> None:
        session = self._sessions.get(str(params.get("sessionId") or ""))
        if session is None:
            await self._send(_error(request_id, -32602, "unknown sessionId"))
            return
        session.cancel.clear()
        session.messages.append(
            {"role": "user", "content": extract_prompt_text(params.get("prompt"))}
        )
        usage: _CompletionUsage | None = None
        context_usage: _CompletionUsage | None = None
        try:
            stop_reason, usage, context_usage = await self._run_turn(session)
        except Exception as exc:
            logger.exception("OpenAI-compatible prompt failed")
            await self._send(
                _session_update(
                    session.id,
                    {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {
                            "type": "text",
                            "text": f"OpenAI-compatible provider error: {_safe_error(exc, self._api_key)}",
                        },
                    },
                )
            )
            stop_reason = "refusal"

        if context_usage is not None and context_usage.context_window > 0:
            await self._send(
                _session_update(
                    session.id,
                    {
                        "sessionUpdate": "usage_update",
                        "used": context_usage.total_tokens,
                        "size": context_usage.context_window,
                    },
                )
            )
        result: dict[str, Any] = {"stopReason": stop_reason}
        if usage is not None:
            result["usage"] = usage.prompt_result()
        await self._send(_response(request_id, result))

    async def _run_turn(
        self, session: _Session
    ) -> tuple[str, _CompletionUsage | None, _CompletionUsage | None]:
        if not self._base_url:
            raise RuntimeError("provider base URL is not configured")
        endpoint = build_chat_completions_url(self._base_url)
        if self._http is None:
            timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=600)
            self._http = aiohttp.ClientSession(timeout=timeout)
        turn_usage: _CompletionUsage | None = None
        context_usage: _CompletionUsage | None = None
        for _ in range(_MAX_TOOL_LOOPS):
            if session.cancel.is_set():
                return "cancelled", turn_usage, context_usage
            content, calls, completion_usage = await self._completion(session, endpoint)
            if completion_usage is not None:
                context_usage = completion_usage
                turn_usage = (
                    completion_usage if turn_usage is None else turn_usage.add(completion_usage)
                )
            assistant: dict[str, Any] = {"role": "assistant", "content": content}
            if calls:
                assistant["tool_calls"] = calls
            session.messages.append(assistant)
            if not calls:
                return "end_turn", turn_usage, context_usage
            for index, call in enumerate(calls):
                if session.cancel.is_set():
                    self._balance_cancelled_calls(session, calls[index:])
                    return "cancelled", turn_usage, context_usage
                await self._execute_tool(session, call)
        raise RuntimeError("tool-call loop limit reached")

    async def _completion(
        self, session: _Session, endpoint: str
    ) -> tuple[str, list[dict[str, Any]], _CompletionUsage | None]:
        assert self._http is not None
        headers = {"Accept": "text/event-stream, application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body: dict[str, Any] = {
            "model": session.model,
            "messages": session.messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if session.bridge.openai_tools:
            body["tools"] = session.bridge.openai_tools
        async with self._http.post(endpoint, headers=headers, json=body) as response:
            if response.status >= 400:
                # Provider error bodies are untrusted and sometimes echo request
                # metadata. Keep user-visible failures actionable without relaying
                # arbitrary upstream content into chat or gateway logs.
                raise RuntimeError(f"provider returned HTTP {response.status}")
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                payload = await response.json(content_type=None)
                return await self._consume_json_completion(session, payload)
            text_parts: list[str] = []
            accumulator = _ToolCallAccumulator()
            completion_usage: _CompletionUsage | None = None
            served_model = session.model
            async for raw_line in response.content:
                if session.cancel.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("model"):
                    served_model = str(payload["model"])
                parsed_usage = parse_completion_usage(
                    payload,
                    fallback_model=served_model,
                )
                if parsed_usage is not None:
                    completion_usage = parsed_usage
                delta = _first_choice_part(payload, "delta")
                if not isinstance(delta, dict):
                    continue
                piece = delta.get("content")
                if isinstance(piece, str) and piece:
                    text_parts.append(piece)
                    await self._send_text(session.id, piece)
                for call in delta.get("tool_calls") or []:
                    accumulator.add(call)
            return "".join(text_parts), accumulator.finish(), completion_usage

    async def _consume_json_completion(
        self, session: _Session, payload: object
    ) -> tuple[str, list[dict[str, Any]], _CompletionUsage | None]:
        message = _first_choice_part(payload, "message")
        if not isinstance(message, dict):
            raise RuntimeError("provider response did not contain a completion message")
        content = message.get("content")
        text = content if isinstance(content, str) else ""
        if text:
            await self._send_text(session.id, text)
        calls = [call for call in message.get("tool_calls") or [] if isinstance(call, dict)]
        for call in calls:
            call["id"] = str(call.get("id") or uuid.uuid4())
        return text, calls, parse_completion_usage(payload, fallback_model=session.model)

    async def _send_text(self, session_id: str, text: str) -> None:
        await self._send(
            _session_update(
                session_id,
                {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            )
        )

    async def _execute_tool(self, session: _Session, call: dict[str, Any]) -> None:
        call_id = str(call.get("id") or uuid.uuid4())
        call["id"] = call_id
        function = call.get("function")
        function = function if isinstance(function, dict) else {}
        public_name = str(function.get("name") or "")
        try:
            arguments = json.loads(str(function.get("arguments") or "{}"))
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        server_name, original_name = session.bridge.identity(public_name)
        title = f"mcp__{server_name}__{original_name}" if server_name else public_name or "tool"
        update: dict[str, Any] = {
            "sessionUpdate": "tool_call",
            "toolCallId": call_id,
            "title": title,
            "kind": "other",
            "rawInput": arguments,
        }
        if server_name:
            update["_meta"] = {"kiro": {"mcpServerName": server_name, "toolName": original_name}}
        await self._send(_session_update(session.id, update))
        permitted = await self._request_permission(session, call_id, title, arguments)
        result = (
            await session.bridge.call(public_name, arguments)
            if permitted
            else "Tool call rejected by the user."
        )
        await self._send(
            _session_update(
                session.id,
                {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": call_id,
                    "status": "completed",
                    "content": [{"content": {"type": "text", "text": result}}],
                },
            )
        )
        session.messages.append({"role": "tool", "tool_call_id": call_id, "content": result})

    async def _request_permission(
        self, session: _Session, call_id: str, title: str, arguments: dict[str, Any]
    ) -> bool:
        reply = await self._request(
            "session/request_permission",
            {
                "sessionId": session.id,
                "toolCall": {
                    "toolCallId": call_id,
                    "title": title,
                    "kind": "other",
                    "input": arguments,
                },
                "options": [
                    {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
                    {
                        "optionId": "allow_always",
                        "name": "Always allow",
                        "kind": "allow_always",
                    },
                    {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
                ],
            },
        )
        outcome = reply.get("result")
        outcome = outcome.get("outcome") if isinstance(outcome, dict) else {}
        return bool(
            isinstance(outcome, dict)
            and outcome.get("outcome") == "selected"
            and outcome.get("optionId") in _ALLOW_OPTIONS
        )

    @staticmethod
    def _balance_cancelled_calls(session: _Session, calls: list[dict[str, Any]]) -> None:
        for call in calls:
            session.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or uuid.uuid4()),
                    "content": "Tool call cancelled.",
                }
            )

    async def close(self) -> None:
        self._closing = True
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        await asyncio.gather(
            *(session.bridge.close() for session in self._sessions.values()),
            return_exceptions=True,
        )
        if self._http is not None:
            await self._http.close()


def _first_choice_part(payload: object, key: str) -> object:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    return choices[0].get(key)


def _write_protocol(data: bytes) -> None:
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("CODEXCREW_OPENAI_LOG_LEVEL", "WARNING"), stream=sys.stderr
    )
    server = OpenAICompatibleAcpServer()
    try:
        await server.serve()
    finally:
        await server.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
