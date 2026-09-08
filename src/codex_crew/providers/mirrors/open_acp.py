"""Wire-only mirrors for public ACP backends that receive session MCP arrays."""

from __future__ import annotations

from collections.abc import Collection
from typing import Mapping

from codex_crew.acp.session_mcp import session_mcp_servers
from codex_crew.acp_backends import ACP_BACKEND_OPENAI_COMPATIBLE
from codex_crew.providers.mirrors.base import AgentConfigMirror, Concern, Disposition, Ruling


class _WireMcpMirror(AgentConfigMirror):
    def rulings(self) -> Mapping[Concern, Ruling]:
        delivered = Disposition.DELIVERED
        translated = Disposition.TRANSLATED
        withheld = Disposition.WITHHELD
        no_channel = Disposition.NO_CHANNEL
        return {
            Concern.MCP_SERVERS: Ruling(
                delivered,
                "the translated mcpServers array is supplied on session/new and session/load",
            ),
            Concern.TOOL_ALLOWLIST: Ruling(
                translated,
                "the agent tools list filters which MCP servers enter the session array",
            ),
            Concern.DENIED_TOOLS: Ruling(
                no_channel,
                "the ACP session array has no per-tool deny field",
                channel="a future backend-specific permission configuration channel",
            ),
            Concern.AUTO_APPROVE: Ruling(
                withheld,
                "automatic approval is withheld so tool decisions remain with the host",
            ),
            Concern.MODEL: Ruling(
                delivered,
                "the selected model is delivered through the backend session configuration",
            ),
            Concern.MODEL_ALLOWLIST: Ruling(
                withheld,
                "the backend owns its advertised model list",
            ),
            Concern.PERMISSION_MODE: Ruling(
                no_channel,
                "no verified portable ACP permission-mode channel is available",
                channel="a backend-advertised session config option",
            ),
            Concern.PROMPT: Ruling(
                withheld,
                "the prompt is injected as normal session context rather than mirrored",
            ),
            Concern.RESOURCES: Ruling(
                withheld,
                "resources are injected as session context rather than mirrored",
            ),
            Concern.HOOKS: Ruling(
                no_channel,
                "agent-spec hooks have no portable ACP representation",
                channel="a backend-native hooks configuration surface",
            ),
        }

    def session_params(
        self,
        agent: str | None,
        *,
        stub_server_names: Collection[str] = (),
        work_dir: object = None,
        **_kwargs: object,
    ) -> dict[str, object]:
        return {
            "mcpServers": session_mcp_servers(
                agent,
                stub_server_names=stub_server_names,
                work_dir=work_dir,
            )
        }


class OpenAICompatibleMirror(_WireMcpMirror):
    backend = ACP_BACKEND_OPENAI_COMPATIBLE
