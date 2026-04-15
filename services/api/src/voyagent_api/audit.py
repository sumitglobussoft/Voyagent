"""API-side audit sink + auth-failure recording helpers + read-surface router.

The agent runtime owns a rich :class:`AuditSink` protocol — we reuse
the canonical :class:`AuditEvent` shape here so auth-failure rows land
in the same table as tool invocations. When the runtime module is not
importable (e.g. bare-API deploys) we fall back to an in-memory list
keyed on the process so ``/auth/verify`` rejections still surface in
tests and local dev.

Rate limiting
-------------
A broken client with a stale token will pound ``/chat/*`` hundreds of
times a minute. :func:`record_auth_failure` caps writes at 5 per
minute per ``(remote_addr, path)`` so the audit table doesn't drown.
The limiter uses Redis when available, in-process LRU otherwise.

Read surface
------------
:data:`router` exposes ``GET /audit`` — a filterable, paginated,
tenant-isolated view of the ``audit_events`` table for the web UI.
Tenant isolation is enforced by the SQL ``WHERE`` clause (the tenant
id comes from the caller's verified JWT, never from a query param).
Every authenticated user in a tenant may read that tenant's audit
log today — there is no admin-only gate yet.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import OrderedDict
from datetime import date, datetime, time as dtime, timezone
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage.audit import AuditEventRow, AuditStatusEnum
from schemas.storage.session import ActorKindEnum
from schemas.storage.user import User

from .auth_inhouse.deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Sink shim                                                                   #
# --------------------------------------------------------------------------- #


class _ApiAuditSinkShim(Protocol):
    async def write(self, event: Any) -> None: ...


class _InMemoryApiAuditSink:
    """Trivial in-memory sink for dev + tests."""

    def __init__(self) -> None:
        self._events: list[Any] = []

    async def write(self, event: Any) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[Any]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


_api_sink: _ApiAuditSinkShim | None = None


def get_api_audit_sink() -> _ApiAuditSinkShim:
    """Return the process-wide API audit sink.

    Prefers the runtime's configured sink when both services are
    co-located; falls back to the in-memory shim.
    """
    global _api_sink
    if _api_sink is not None:
        return _api_sink
    try:
        # Build a runtime bundle only if one has already been built by
        # the chat layer. We avoid forcing the agent runtime to boot
        # solely to record auth failures.
        from voyagent_api import chat as _chat  # noqa: WPS433

        bundle = _chat._bundle  # type: ignore[attr-defined]
        if bundle is not None and getattr(bundle, "audit_sink", None) is not None:
            _api_sink = bundle.audit_sink
            return _api_sink
    except Exception:  # noqa: BLE001
        pass
    _api_sink = _InMemoryApiAuditSink()
    return _api_sink


def set_api_audit_sink_for_test(sink: _ApiAuditSinkShim | None) -> None:
    global _api_sink
    _api_sink = sink


# --------------------------------------------------------------------------- #
# Rate limiter                                                                #
# --------------------------------------------------------------------------- #


_INMEM_LIMITER: OrderedDict[str, tuple[int, int]] = OrderedDict()
_INMEM_LIMIT_CAP = 2048  # evict oldest entries past this soft cap
_RATE_LIMIT = 5
_RATE_WINDOW_SECONDS = 60


def _allow_inmem(key: str) -> bool:
    """In-memory token-bucket sibling to the Redis limiter."""
    now = int(time.time())
    bucket = _INMEM_LIMITER.get(key)
    if bucket is None or bucket[1] + _RATE_WINDOW_SECONDS <= now:
        _INMEM_LIMITER[key] = (1, now)
        _INMEM_LIMITER.move_to_end(key)
        while len(_INMEM_LIMITER) > _INMEM_LIMIT_CAP:
            _INMEM_LIMITER.popitem(last=False)
        return True
    count, first_ts = bucket
    if count >= _RATE_LIMIT:
        return False
    _INMEM_LIMITER[key] = (count + 1, first_ts)
    _INMEM_LIMITER.move_to_end(key)
    return True


async def _allow_redis(key: str) -> bool | None:
    """Return ``True``/``False`` on Redis path, or ``None`` on failure."""
    url = os.environ.get("VOYAGENT_REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    try:
        client = redis_async.from_url(url, decode_responses=True)
        rkey = f"voyagent:auth_fail:{key}"
        count = await client.incr(rkey)
        if int(count) == 1:
            await client.expire(rkey, _RATE_WINDOW_SECONDS)
        return int(count) <= _RATE_LIMIT
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth-failure rate-limit Redis path failed: %s", exc)
        return None


async def _allow(remote_addr: str, path: str) -> bool:
    key = f"{remote_addr}|{path}"
    verdict = await _allow_redis(key)
    if verdict is not None:
        return verdict
    return _allow_inmem(key)


# --------------------------------------------------------------------------- #
# Record                                                                      #
# --------------------------------------------------------------------------- #


_SYSTEM_TENANT_ID = "00000000-0000-7000-8000-000000000000"
"""Synthetic "system" tenant id used when the real one is unknown.

Matches the UUIDv7 pattern the canonical ``EntityId`` regex accepts.
When the storage layer enforces a real FK on ``tenant_id`` this id
will need a seed row — v0 uses the in-memory audit sink path which
carries no FK.
"""


async def record_auth_failure(
    *,
    error_code: str,
    method: str,
    path: str,
    remote_addr: str,
    tenant_id: str | None = None,
) -> None:
    """Append an auth-failure :class:`AuditEvent` — best-effort.

    Rate-limited to 5 events / minute / ``(remote_addr, path)`` so a
    broken client does not flood the audit log.
    """
    if not await _allow(remote_addr, path):
        return

    try:
        from schemas.canonical import ActorKind, AuditEvent, AuditStatus
    except Exception as exc:  # noqa: BLE001
        logger.debug("canonical audit types unavailable: %s", exc)
        return

    now = datetime.now(timezone.utc)
    try:
        event = AuditEvent(
            id=_uuid7_like(),
            tenant_id=tenant_id or _SYSTEM_TENANT_ID,
            actor_id=_SYSTEM_TENANT_ID,
            actor_kind=ActorKind.SYSTEM,
            tool="auth.verify",
            inputs={"method": method, "path": path, "remote_addr": remote_addr},
            started_at=now,
            completed_at=now,
            status=AuditStatus.REJECTED,
            error=error_code,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth-failure AuditEvent build failed: %s", exc)
        return

    sink = get_api_audit_sink()
    try:
        await sink.write(event)
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth-failure sink.write failed: %s", exc)


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


# --------------------------------------------------------------------------- #
# Read surface — GET /audit                                                   #
# --------------------------------------------------------------------------- #


router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    """Wire shape of one audit row.

    ``kind`` maps to the storage column ``tool`` — the UI terminology
    in the spec calls a row's event type a "kind" (e.g. ``auth.verify``,
    ``issue_ticket``) while storage names that column ``tool`` because
    rows started life as records of tool invocations. We keep the
    storage name unchanged and alias on the wire.

    ``payload`` bundles the raw JSON columns (``inputs``, ``outputs``,
    ``entity_refs``, ``error``, ``driver``) so the UI can pretty-print
    everything the row carries without a dedicated schema per tool.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    actor_kind: str
    actor_id: str | None = None
    actor_email: str | None = None
    kind: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime


class AuditListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


def _tenant_uuid_for_read(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.tenant_id)
    except ValueError as exc:  # pragma: no cover — JWT must carry a UUID.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


def _parse_kinds(raw: list[str] | None) -> list[str] | None:
    """Accept ``?kind=a&kind=b`` or ``?kind=a,b``; empty means no filter."""
    if not raw:
        return None
    out: list[str] = []
    for item in raw:
        if not item:
            continue
        for piece in item.split(","):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out or None


def _row_summary(row: AuditEventRow) -> str:
    """One-line human summary of an audit row.

    We prefer the ``error`` column when the row failed, otherwise fall
    back to a ``tool / driver`` signature. Real customer-facing copy
    would want per-tool formatters; v0 keeps it mechanical so the UI
    always has *something* to show.
    """
    status_value = (
        row.status.value
        if isinstance(row.status, AuditStatusEnum)
        else str(row.status)
    )
    if row.error:
        return f"{row.tool}: {row.error}"
    if row.driver:
        return f"{row.tool} via {row.driver} ({status_value})"
    return f"{row.tool} ({status_value})"


def _wire_status(row: AuditEventRow) -> str:
    """Collapse the five-state audit enum to the ``ok|error`` wire shape."""
    raw = row.status.value if isinstance(row.status, AuditStatusEnum) else str(row.status)
    if raw in ("failed", "rejected"):
        return "error"
    # ``started``, ``succeeded``, ``cancelled`` surface as "ok" — the UI
    # only distinguishes the failure path.
    return "ok"


def _actor_kind_wire(row: AuditEventRow) -> str:
    """Map the storage enum to the web-friendly ``user|agent|system`` set."""
    raw = (
        row.actor_kind.value
        if isinstance(row.actor_kind, ActorKindEnum)
        else str(row.actor_kind)
    )
    # Storage uses ``human``; the wire (and UI) call it ``user``.
    if raw == "human":
        return "user"
    return raw


def _row_to_response(
    row: AuditEventRow,
    *,
    actor_email: str | None,
) -> AuditEventResponse:
    payload: dict[str, Any] = {
        "inputs": row.inputs or {},
        "outputs": row.outputs or {},
        "entity_refs": row.entity_refs or {},
    }
    if row.driver:
        payload["driver"] = row.driver
    if row.error:
        payload["error"] = row.error
    if row.approval_required:
        payload["approval_required"] = True
    if row.approved_by is not None:
        payload["approved_by"] = str(row.approved_by)
    if row.approved_at is not None:
        payload["approved_at"] = row.approved_at.isoformat()
    if row.completed_at is not None:
        payload["completed_at"] = row.completed_at.isoformat()

    return AuditEventResponse(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        actor_kind=_actor_kind_wire(row),
        actor_id=str(row.actor_id) if row.actor_id is not None else None,
        actor_email=actor_email,
        kind=row.tool,
        summary=_row_summary(row),
        payload=payload,
        status=_wire_status(row),
        created_at=row.started_at,
    )


@router.get("", response_model=AuditListResponse)
async def list_audit_events(
    actor_id: str | None = Query(None),
    kind: list[str] | None = Query(None),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> AuditListResponse:
    """List audit events for the caller's tenant, most-recent-first.

    Tenant isolation is enforced on every query by filtering on the
    principal's ``tenant_id`` — callers never pass a tenant id.
    """
    tenant_uuid = _tenant_uuid_for_read(principal)

    base = select(AuditEventRow).where(AuditEventRow.tenant_id == tenant_uuid)
    count_base = (
        select(func.count())
        .select_from(AuditEventRow)
        .where(AuditEventRow.tenant_id == tenant_uuid)
    )

    if actor_id is not None:
        try:
            actor_uuid = uuid.UUID(actor_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_actor_id",
            ) from exc
        base = base.where(AuditEventRow.actor_id == actor_uuid)
        count_base = count_base.where(AuditEventRow.actor_id == actor_uuid)

    kinds = _parse_kinds(kind)
    if kinds:
        base = base.where(AuditEventRow.tool.in_(kinds))
        count_base = count_base.where(AuditEventRow.tool.in_(kinds))

    # Bracket on started_at (the row's logical "created_at"). ``from``
    # is inclusive at 00:00 UTC, ``to`` is inclusive through 23:59:59.
    if date_from is not None:
        start_dt = datetime.combine(date_from, dtime.min, tzinfo=timezone.utc)
        base = base.where(AuditEventRow.started_at >= start_dt)
        count_base = count_base.where(AuditEventRow.started_at >= start_dt)
    if date_to is not None:
        end_dt = datetime.combine(date_to, dtime.max, tzinfo=timezone.utc)
        base = base.where(AuditEventRow.started_at <= end_dt)
        count_base = count_base.where(AuditEventRow.started_at <= end_dt)

    total = int((await db.execute(count_base)).scalar_one() or 0)

    rows = (
        (
            await db.execute(
                base.order_by(AuditEventRow.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    # Second, batched query for ``actor_email`` — we deliberately avoid
    # a relationship join so this router stays independent of any
    # cross-table ORM wiring. Rows with ``actor_id is None`` (system
    # events) naturally carry ``actor_email = None``.
    actor_ids = {row.actor_id for row in rows if row.actor_id is not None}
    email_by_id: dict[uuid.UUID, str] = {}
    if actor_ids:
        user_rows = (
            (
                await db.execute(
                    select(User.id, User.email).where(User.id.in_(actor_ids))
                )
            )
            .all()
        )
        email_by_id = {uid: email for uid, email in user_rows}

    items = [
        _row_to_response(
            row,
            actor_email=(
                email_by_id.get(row.actor_id) if row.actor_id is not None else None
            ),
        )
        for row in rows
    ]

    return AuditListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


__all__ = [
    "get_api_audit_sink",
    "record_auth_failure",
    "router",
    "set_api_audit_sink_for_test",
]
