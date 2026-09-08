"""Which backend has a mirror, and — as a first-class entry — which has none.

The point of a registry rather than a lookup that returns ``None`` on a miss is
that **absence has to be a statement**. A backend with no entry here fails the
parity test; a backend that genuinely needs no projection says so, with its
reason, in :data:`NO_MIRROR`. That is the difference between "declared not to
need one" and "nobody got round to it", which is the distinction whose absence
let the same missing-tools defect ship twice.
"""

from __future__ import annotations

from codex_crew.acp_backends import ACP_BACKEND_CODEX, ACP_BACKEND_OPENAI_COMPATIBLE
from codex_crew.providers.mirrors.base import AgentConfigMirror
from codex_crew.providers.mirrors.open_acp import OpenAICompatibleMirror

#: Backends whose spec projection lives in this folder.
MIRRORS: dict[str, type[AgentConfigMirror]] = {
    ACP_BACKEND_OPENAI_COMPATIBLE: OpenAICompatibleMirror,
}

#: Backends that deliberately have no mirror, and why. Read as a claim to be
#: checked, not as a backlog: each of these is a decision.
NO_MIRROR: dict[str, str] = {
    ACP_BACKEND_CODEX: (
        "Codex uses its native tool and permission configuration rather than an "
        "agent-spec mirror. Codex Crew verifies that configuration before the "
        "first prompt."
    ),
}


def mirror_for(backend: str) -> AgentConfigMirror | None:
    """The mirror for *backend*, or ``None`` when it declares it needs none.

    Raises for a backend that is in neither map: an unregistered backend is the
    failure this module exists to catch, so it is loud rather than silently
    mirror-less.
    """
    cls = MIRRORS.get(backend)
    if cls is not None:
        return cls()
    if backend in NO_MIRROR:
        return None
    raise KeyError(
        f"backend {backend!r} has no agent-config mirror and no NO_MIRROR entry — "
        "add one of the two; see providers/mirrors/README.md"
    )
