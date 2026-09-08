"""``GET /api/acp-backends`` -- per-backend selectability and machine readiness.

One row per backend id in ``acp_backends.ACP_BACKENDS_KNOWN``, sorted by
``policy_id``, including ids this build cannot serve: the dashboard's backend
switch lists all of them and must be able to say which is which, so an
unservable backend needs a row rather than silent absence.

Two facts per row, from two owners that must not be conflated:

* ``selectable`` -- build capability AND deployment policy, read from
  ``handlers.core._selectable_acp_backends()``. That helper is already the
  single derivation feeding the PATCH allowlist and ``/api/config/schema``, and
  it already applies the ``agent_backend`` governance scope. Re-deriving it here
  from ``acp_backends.selectable_backend_values()`` would restore exactly the
  drift that a literal list in three places once caused: the wire would accept
  a value this endpoint calls unselectable, or the reverse.
* ``installed`` -- whether the harness is on THIS machine, from
  :mod:`codex_crew.agent_sdk`, which asks through the spawn's own resolvers.
  Reached through the SDK rather than the ACP layer directly: this handler is
  application code, and ``scripts/check_agent_sdk_boundary.py`` is what keeps
  that true.

Owner-only, and the snapshot is offloaded: Codex discovery runs a bounded
version probe and resolving the governance ceiling loads config, so neither may
run on the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List

from aiohttp import web

from codex_crew.agent_sdk import CodexBootstrapError, bootstrap_codex
from codex_crew.dashboard.handlers.kiro_prerequisite import _is_dashboard_owner
from codex_crew.sel import sel

logger = logging.getLogger(__name__)

#: Machine-readable error code, per the dashboard error-code contract
#: (``test/test_error_code_contract.py``): the client branches on this, and the
#: English prose beside it is advisory. Spelled to match the other owner-gated
#: dashboard handlers rather than inventing a per-endpoint code.
_CODE_OWNER_REQUIRED = "dashboard_owner_required"
_OWNER_REQUIRED_MESSAGE = "dashboard owner required"

_AUDIT_OPERATION = "acp_backend_status_access"
_AUDIT_INSTALL_OPERATION = "codex_cli_install"
_codex_install_lock = threading.Lock()


def _bootstrap_with_lock() -> Any:
    """Run the installer while the worker, not the request, owns the lock."""

    try:
        return bootstrap_codex()
    finally:
        # A disconnected/cancelled HTTP request does not stop ``to_thread``.
        # Releasing here prevents another click from racing the still-running
        # installer after the request coroutine has already gone away.
        _codex_install_lock.release()


async def _deny_non_owner(
    request: web.Request, *, operation: str = _AUDIT_OPERATION
) -> web.Response | None:
    """Refuse a non-owner, mirroring the prerequisite handlers' 403 shape.

    Which components are installed on the host is host-configuration state and
    belongs to the same audience as the first-run setup surface it complements,
    so it reuses that module's owner predicate rather than a second one.
    """
    if _is_dashboard_owner(request):
        return None

    caller = str(request.get("user") or "")
    audit_caller = str(request.get("app") or caller or "unknown")

    def _audit() -> None:
        sel().log_api_access(
            caller=audit_caller,
            operation=operation,
            outcome="denied",
            source="dashboard",
            resources=request.path,
            error=_OWNER_REQUIRED_MESSAGE,
        )

    try:
        await asyncio.to_thread(_audit)
    except Exception:
        # An unwritable audit log must not convert a denial into a 500 -- the
        # refusal is the security-relevant half and still has to land.
        logger.debug("Could not audit denied ACP backend status access", exc_info=True)
    return web.json_response(
        {"error": _OWNER_REQUIRED_MESSAGE, "code": _CODE_OWNER_REQUIRED},
        status=403,
    )


def _snapshot() -> List[Dict[str, Any]]:
    """Build the rows. BLOCKING -- run under ``asyncio.to_thread``.

    ``_selectable_acp_backends`` is imported here rather than at module scope:
    ``handlers.core`` is a large sibling in the same package, and a
    module-scope import from a module the package ``__init__`` also imports is
    how a cycle gets introduced later.
    """
    from codex_crew.agent_sdk import INSTALLED, MISSING, probe_backends
    from codex_crew.dashboard.handlers.core import _selectable_acp_backends

    selectable = set(_selectable_acp_backends())
    rows: List[Dict[str, Any]] = []
    for state in probe_backends():
        rows.append(
            {
                "id": state.backend,
                "policy_id": state.policy_id,
                "selectable": state.backend in selectable,
                "installed": state.installed,
                # Enforced here, not just by the probes: the contract makes this
                # non-empty ONLY for a MISSING verdict, so an UNKNOWN row can
                # never name a component the check never confirmed was absent.
                "missing_components": (
                    list(state.missing_components) if state.installed == MISSING else []
                ),
                "install_command": state.install_command,
                # Clamped to a MISSING-free verdict for the same reason as
                # ``missing_components`` above: "installed but the running gateway
                # cannot use it yet" is only meaningful once the components are
                # actually there. A MISSING or UNKNOWN row carries False.
                "restart_required": (
                    bool(state.restart_required) if state.installed == INSTALLED else False
                ),
                "codex_cli_source": state.codex_cli_source,
                "codex_cli_version": state.codex_cli_version,
                "one_click_install": bool(state.one_click_install),
            }
        )
    return rows


async def api_acp_backend_status(request: web.Request) -> web.Response:
    """GET /api/acp-backends -- selectability + install state for every backend."""
    denial = await _deny_non_owner(request)
    if denial is not None:
        return denial
    backends = await asyncio.to_thread(_snapshot)
    return web.json_response({"backends": backends})


async def api_codex_install(request: web.Request) -> web.Response:
    """POST /api/acp-backends/codex/install -- install and attach Codex."""

    denial = await _deny_non_owner(request, operation=_AUDIT_INSTALL_OPERATION)
    if denial is not None:
        return denial
    if not _codex_install_lock.acquire(blocking=False):
        return web.json_response(
            {"error": "Codex installation is already running", "code": "codex_install_in_progress"},
            status=409,
        )

    try:
        result = await asyncio.to_thread(_bootstrap_with_lock)
    except CodexBootstrapError as exc:
        logger.warning("Codex one-click bootstrap failed: %s", exc.code)
        return web.json_response(
            {"error": str(exc), "code": exc.code},
            status=503,
        )
    except Exception:
        logger.exception("Codex one-click bootstrap failed unexpectedly")
        return web.json_response(
            {
                "error": "Codex installation failed. Check the gateway log and try again.",
                "code": "codex_install_failed",
            },
            status=500,
        )

    try:
        await asyncio.to_thread(
            sel().log_api_access,
            caller=str(request.get("user") or "dashboard"),
            operation=_AUDIT_INSTALL_OPERATION,
            outcome="ok",
            source="dashboard",
            resources="codex",
        )
    except Exception:
        logger.debug("Could not audit successful Codex installation", exc_info=True)

    return web.json_response(
        {
            "ok": result.ok,
            "codex_cli": {
                "version": result.codex_cli.version,
                "source": result.codex_cli.source,
            },
            "adapter_ready": result.adapter_ready,
            "backends": await asyncio.to_thread(_snapshot),
        }
    )
