"""Chat surface — HTTP + Server-Sent Events for a single agent turn.

Thin wire layer between TypeScript clients (web, desktop, mobile) and the
Python agent runtime living in :mod:`voyagent_agent_runtime`.

Design notes
------------
* The runtime is imported **lazily** inside :func:`_runtime`. If the import
  fails — typically because the parallel runtime work hasn't landed yet in
  the current checkout — every ``/chat/*`` route responds with HTTP 503 and
  a machine-readable ``{"detail": "agent_runtime_unavailable"}`` body
  instead of taking the entire API process down.
* The SSE frame is deliberately uniform: one ``event: agent_event`` per
  :class:`AgentEvent` emitted by :meth:`Orchestrator.run_turn`, with
  ``AgentEvent.model_dump(mode="json")`` as the ``data`` field. An
  ``event: heartbeat`` frame is emitted every 15 s of silence so load
  balancers and EventSource listeners stay warm.
* Human-in-the-loop: when the runtime emits an ``approval_request`` it
  stops producing events. The client calls
  ``POST /chat/sessions/{id}/messages`` again with an empty ``message``
  and a populated ``approvals`` dict to resume.
* **Tenant isolation.** Every ``/chat/*`` endpoint takes a
  :class:`TenantContext` via :func:`get_tenant`. Session lookups compare
  ``session.tenant_id`` against ``tenant_ctx.tenant_id`` and return
  ``404`` on mismatch — we deliberately avoid ``403`` so callers cannot
  probe which session ids belong to other tenants.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from types import ModuleType
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .tenancy import TenantContext, get_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# --------------------------------------------------------------------------- #
# Runtime import — lazy, cached, failure-tolerant.                            #
# --------------------------------------------------------------------------- #


class _RuntimeUnavailable(RuntimeError):
    """Raised when :mod:`voyagent_agent_runtime` can't be imported."""


@lru_cache(maxsize=1)
def _runtime() -> ModuleType:
    """Import and cache the agent runtime module.

    Cached via :func:`functools.lru_cache` so a successful import happens
    exactly once. Failures re-raise — ``lru_cache`` doesn't cache
    exceptions — so operators can fix the environment without restarting
    uvicorn.
    """
    try:
        import voyagent_agent_runtime  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent runtime import failed: %s", exc)
        raise _RuntimeUnavailable(str(exc)) from exc
    logger.info("agent runtime imported: model=%s", _describe_runtime(voyagent_agent_runtime))
    return voyagent_agent_runtime


def _describe_runtime(runtime: ModuleType) -> str:
    """Best-effort human description of the loaded runtime."""
    try:
        settings_cls = runtime.Settings  # type: ignore[attr-defined]
        return str(settings_cls().model)
    except Exception:  # noqa: BLE001
        return "unknown"


def _runtime_or_503() -> ModuleType:
    """Return the runtime module or raise 503 if unavailable."""
    try:
        return _runtime()
    except _RuntimeUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent_runtime_unavailable",
        )


def runtime_available() -> bool:
    """Return ``True`` iff :mod:`voyagent_agent_runtime` imports cleanly.

    Used by :mod:`voyagent_api.main` at startup for a single log line so
    operators know whether ``/chat/*`` routes will serve or 503.
    """
    try:
        _runtime()
    except _RuntimeUnavailable:
        return False
    return True


# --------------------------------------------------------------------------- #
# Runtime bundle — one per process, built from env.                           #
# --------------------------------------------------------------------------- #


_bundle: Any | None = None
_bundle_lock = asyncio.Lock()


async def _get_bundle() -> Any:
    """Return the process-wide :class:`DefaultRuntime` bundle."""
    global _bundle
    if _bundle is not None:
        return _bundle
    async with _bundle_lock:
        if _bundle is None:
            runtime = _runtime_or_503()
            try:
                _bundle = runtime.build_default_runtime()
            except Exception as exc:  # noqa: BLE001
                logger.exception("build_default_runtime failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"agent_runtime_bootstrap_failed: {exc}",
                )
        return _bundle


# --------------------------------------------------------------------------- #
# Request / response models.                                                  #
# --------------------------------------------------------------------------- #


class SessionCreateRequest(BaseModel):
    """Body for ``POST /chat/sessions``.

    The tenant and actor are derived from the authenticated JWT, so the
    body is intentionally empty today. We keep the model around so future
    per-session options (seed system prompt, locale override, ...) can be
    added without a breaking wire change.
    """

    model_config = {"extra": "forbid"}


class SessionCreateResponse(BaseModel):
    session_id: str


class PendingApproval(BaseModel):
    approval_id: str
    tool_name: str | None = None
    summary: str | None = None


class SessionSummaryResponse(BaseModel):
    session_id: str
    tenant_id: str
    actor_id: str
    message_count: int
    pending_approvals: list[PendingApproval]


class SendMessageRequest(BaseModel):
    message: str = ""
    approvals: dict[str, bool] | None = None


# --------------------------------------------------------------------------- #
# Endpoints.                                                                  #
# --------------------------------------------------------------------------- #


@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: SessionCreateRequest | None = None,
    tenant_ctx: TenantContext = Depends(get_tenant),
) -> SessionCreateResponse:
    """Create a brand-new chat session owned by the authenticated tenant."""
    runtime = _runtime_or_503()
    bundle = await _get_bundle()

    new_session_id = runtime.new_session_id
    SessionCls = runtime.Session

    session = SessionCls(
        id=new_session_id(),
        tenant_id=tenant_ctx.tenant_id,
        actor_id=tenant_ctx.user_id,
    )
    await bundle.session_store.put(session)
    logger.info(
        "chat.session.created session_id=%s tenant=%s actor=%s",
        session.id,
        tenant_ctx.tenant_id,
        tenant_ctx.user_id,
    )
    # Silence unused-variable warning on ``body`` — it exists for future options.
    _ = body
    return SessionCreateResponse(session_id=session.id)


@router.get("/sessions/{session_id}", response_model=SessionSummaryResponse)
async def get_session(
    session_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant),
) -> SessionSummaryResponse:
    """Return session metadata without message content (history can get big).

    Returns ``404`` both when the session doesn't exist and when it
    exists but belongs to a different tenant — we don't want to confirm
    session existence across tenants.
    """
    bundle = await _get_bundle()
    session = await bundle.session_store.get(session_id)
    if session is None or session.tenant_id != tenant_ctx.tenant_id:
        raise HTTPException(status_code=404, detail="session_not_found")

    pending = [
        PendingApproval(
            approval_id=ap.id,
            tool_name=ap.tool_name,
            summary=ap.summary,
        )
        for ap in session.pending_approvals.values()
        if ap.granted is None
    ]

    return SessionSummaryResponse(
        session_id=session.id,
        tenant_id=session.tenant_id,
        actor_id=session.actor_id,
        message_count=len(session.message_history),
        pending_approvals=pending,
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    request: Request,
    tenant_ctx: TenantContext = Depends(get_tenant),
) -> EventSourceResponse:
    """Stream an agent turn as SSE.

    One ``event: agent_event`` frame per :class:`AgentEvent`; ``event:
    heartbeat`` every 15 s of silence; a synthetic ``error``-kind frame on
    any unexpected exception before the stream closes.
    """
    runtime = _runtime_or_503()
    bundle = await _get_bundle()

    session = await bundle.session_store.get(session_id)
    if session is None or session.tenant_id != tenant_ctx.tenant_id:
        raise HTTPException(status_code=404, detail="session_not_found")

    AgentEventCls = runtime.AgentEvent
    AgentEventKind = runtime.AgentEventKind

    async def event_source() -> AsyncIterator[dict[str, str]]:
        final_kind = AgentEventKind.FINAL.value
        try:
            async for event in bundle.orchestrator.run_turn(
                session,
                body.message,
                approvals=body.approvals,
            ):
                if await request.is_disconnected():
                    logger.info("chat.sse.client_disconnect session_id=%s", session_id)
                    break
                payload = event.model_dump(mode="json")
                yield {
                    "event": "agent_event",
                    "data": json.dumps(payload, separators=(",", ":")),
                }
                if payload.get("kind") == final_kind:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat.sse.turn_failed session_id=%s", session_id)
            error_event = AgentEventCls(
                kind=AgentEventKind.ERROR,
                session_id=session_id,
                turn_id="error",
                timestamp=datetime.now(timezone.utc),
                error_message=str(exc),
            )
            yield {
                "event": "agent_event",
                "data": json.dumps(
                    error_event.model_dump(mode="json"), separators=(",", ":")
                ),
            }

    async def with_heartbeats() -> AsyncIterator[dict[str, str]]:
        """Interleave ``event: heartbeat`` frames during silence > 15 s."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()

        async def pump() -> None:
            try:
                async for ev in event_source():
                    await queue.put(ev)
            finally:
                await queue.put(None)

        task = asyncio.create_task(pump())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": ""}
                    continue
                if item is None:
                    break
                yield item
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    return EventSourceResponse(with_heartbeats())
