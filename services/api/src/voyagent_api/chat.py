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

from .db import get_sessionmaker
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
    title: str | None = None


class SessionListItem(BaseModel):
    id: str
    title: str | None = None
    created_at: str | None = None
    message_count: int = 0


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]


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
        title=getattr(session, "title", None),
    )


def _derive_title(message: str) -> str | None:
    """Return a title derived from the first user message.

    Rule: strip, then take the first 60 chars. Empty/whitespace-only
    messages yield ``None``.
    """
    if not message:
        return None
    cleaned = message.strip()
    if not cleaned:
        return None
    if len(cleaned) <= 60:
        return cleaned
    return cleaned[:60]


async def _persist_session_title(session_id: str, title: str) -> None:
    """Best-effort UPDATE of ``sessions.title`` in Postgres.

    Silently swallows failures — the in-memory session_store already
    carries the title, and a missing row (e.g. tests with a stub
    runtime that doesn't write through to SQL) shouldn't block the
    turn from streaming.
    """
    try:
        from sqlalchemy import text  # local import keeps test startup cheap

        maker = get_sessionmaker()
    except Exception:  # noqa: BLE001
        return
    try:
        async with maker() as db:
            await db.execute(
                text(
                    "UPDATE sessions SET title = :title "
                    "WHERE id = :sid AND title IS NULL"
                ),
                {"title": title, "sid": session_id},
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "chat.title.persist_failed session_id=%s err=%s",
            session_id,
            exc,
        )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    tenant_ctx: TenantContext = Depends(get_tenant),
) -> SessionListResponse:
    """List chat sessions for the current tenant, newest first.

    Reads from the ``sessions`` SQL table rather than the in-memory
    session_store so the sidebar stays populated across restarts.
    Returns ``{id, title, created_at, message_count}`` for each row.
    """
    try:
        from sqlalchemy import text

        maker = get_sessionmaker()
    except Exception:  # noqa: BLE001
        return SessionListResponse(sessions=[])

    items: list[SessionListItem] = []
    try:
        async with maker() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT s.id, s.title, s.created_at, "
                        "COALESCE((SELECT COUNT(*) FROM messages m "
                        "WHERE m.session_id = s.id), 0) AS msg_count "
                        "FROM sessions s "
                        "WHERE s.tenant_id = :tid "
                        "ORDER BY s.created_at DESC "
                        "LIMIT 200"
                    ),
                    {"tid": tenant_ctx.tenant_id},
                )
            ).all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("chat.sessions.list_failed err=%s", exc)
        return SessionListResponse(sessions=[])

    for row in rows:
        created_at = row[2]
        items.append(
            SessionListItem(
                id=str(row[0]),
                title=row[1],
                created_at=(
                    created_at.isoformat()
                    if hasattr(created_at, "isoformat")
                    else (str(created_at) if created_at is not None else None)
                ),
                message_count=int(row[3] or 0),
            )
        )
    return SessionListResponse(sessions=items)


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

    Each ``agent_event`` carries a monotonically-increasing ``id:``
    field scoped to the session. On reconnect, clients send the last
    seen id in the ``Last-Event-ID`` HTTP header; the endpoint replays
    any buffered events with a higher id without re-running the
    orchestrator. Heartbeats carry no ``id:``.

    The replay buffer is in-memory per session and capped at
    ``SSE_REPLAY_BUFFER_CAP`` (200 by default).
    """
    runtime = _runtime_or_503()
    bundle = await _get_bundle()

    session = await bundle.session_store.get(session_id)
    if session is None or session.tenant_id != tenant_ctx.tenant_id:
        raise HTTPException(status_code=404, detail="session_not_found")

    AgentEventCls = runtime.AgentEvent
    AgentEventKind = runtime.AgentEventKind
    buffer_cap: int = getattr(runtime, "SSE_REPLAY_BUFFER_CAP", 200)

    # --- Session-title auto-generation (first user message only) --------- #
    # The check runs *before* the orchestrator appends the new user turn
    # to ``message_history``, so ``len(...) == 0`` correctly identifies the
    # first message. Non-empty ``approvals`` resume flows don't count.
    existing_title = getattr(session, "title", None)
    if (
        existing_title in (None, "")
        and body.message
        and body.message.strip()
        and len(getattr(session, "message_history", []) or []) == 0
    ):
        derived = _derive_title(body.message)
        if derived:
            try:
                session.title = derived  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            await _persist_session_title(session_id, derived)

    # Parse Last-Event-ID. Per the SSE spec, browsers auto-send it when
    # the EventSource reconnects; our SDK forwards an explicit header on
    # its own retry path.
    raw_last_id = request.headers.get("last-event-id")
    last_event_id: int | None = None
    if raw_last_id is not None and raw_last_id != "":
        try:
            last_event_id = int(raw_last_id)
        except ValueError:
            last_event_id = None  # treated as mismatch below.

    # Defensive: older Session instances (pre-reconnect work) may lack
    # the buffer + counter attributes. Synthesize defaults rather than
    # crashing on an in-flight rollout.
    if getattr(session, "sse_event_buffer", None) is None:
        try:
            session.sse_event_buffer = []  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    if getattr(session, "sse_last_event_id", None) is None:
        try:
            session.sse_last_event_id = 0  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def _append_to_buffer(eid: int, data_json: str) -> None:
        buf = session.sse_event_buffer
        buf.append((eid, data_json))
        overflow = len(buf) - buffer_cap
        if overflow > 0:
            del buf[:overflow]

    def _next_event_id() -> int:
        session.sse_last_event_id = int(session.sse_last_event_id) + 1
        return session.sse_last_event_id

    replay_requested = raw_last_id is not None and raw_last_id != ""
    replay_valid = (
        last_event_id is not None
        and last_event_id <= int(session.sse_last_event_id)
    )

    async def event_source() -> AsyncIterator[dict[str, str]]:
        final_kind = AgentEventKind.FINAL.value

        # --- Replay path -------------------------------------------- #
        if replay_requested:
            if replay_valid:
                replayed = [
                    (eid, data)
                    for eid, data in list(session.sse_event_buffer)
                    if last_event_id is not None and eid > last_event_id
                ]
                for eid, data in replayed:
                    yield {
                        "id": str(eid),
                        "event": "agent_event",
                        "data": data,
                    }
                # If the last replayed frame was the terminal ``final``,
                # close without re-running the turn.
                if replayed:
                    try:
                        tail_payload = json.loads(replayed[-1][1])
                        if (
                            isinstance(tail_payload, dict)
                            and tail_payload.get("kind") == final_kind
                        ):
                            return
                    except Exception:  # noqa: BLE001
                        pass
                # No tail terminator replayed and no new work intended:
                # return a clean empty stream.
                if not body.message and not body.approvals:
                    return
            else:
                # Mismatched Last-Event-ID: we can't prove what the
                # client has. Emit a single error frame with a
                # ``replay_failed`` code and keep going live.
                err = AgentEventCls(
                    kind=AgentEventKind.ERROR,
                    session_id=session_id,
                    turn_id="replay",
                    timestamp=datetime.now(timezone.utc),
                    error_message="replay_failed: Last-Event-ID outside server buffer",
                )
                err_json = json.dumps(
                    err.model_dump(mode="json"), separators=(",", ":")
                )
                eid = _next_event_id()
                _append_to_buffer(eid, err_json)
                yield {"id": str(eid), "event": "agent_event", "data": err_json}

        # --- Live path ---------------------------------------------- #
        try:
            async for event in bundle.orchestrator.run_turn(
                session,
                body.message,
                approvals=body.approvals,
                actor_role=tenant_ctx.role,
            ):
                if await request.is_disconnected():
                    logger.info("chat.sse.client_disconnect session_id=%s", session_id)
                    break
                payload = event.model_dump(mode="json")
                data = json.dumps(payload, separators=(",", ":"))
                eid = _next_event_id()
                _append_to_buffer(eid, data)
                yield {"id": str(eid), "event": "agent_event", "data": data}
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
            data = json.dumps(
                error_event.model_dump(mode="json"), separators=(",", ":")
            )
            eid = _next_event_id()
            _append_to_buffer(eid, data)
            yield {"id": str(eid), "event": "agent_event", "data": data}

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
