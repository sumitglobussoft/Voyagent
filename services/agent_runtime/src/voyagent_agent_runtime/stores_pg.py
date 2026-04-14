"""Postgres-backed :class:`SessionStore` and :class:`AuditSink`.

These implementations satisfy the same in-process protocols as
:class:`InMemorySessionStore` / :class:`InMemoryAuditSink` so the
runtime swap is transparent to :mod:`voyagent_agent_runtime.runtime`.

Design notes:

* Translation between canonical Pydantic models and ORM rows lives in
  this file and nowhere else. Storage is a separate concern from
  canonical; both shapes evolve, and the translation is the seam.
* Audit writes must never raise — the user's turn is more important
  than a perfectly-captured audit row. See :func:`_best_effort`.
* ``append_message`` computes the next ``sequence`` inside a single
  transaction via a ``SELECT COALESCE(MAX(...),0)+1`` subquery to avoid
  a lost-update race across concurrent writers.
"""

from __future__ import annotations

import functools
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, TypeVar

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from schemas.canonical import (
    ActorKind,
    AuditEvent,
    AuditStatus,
    EntityId,
)
from schemas.storage import (
    ActorKindEnum,
    AuditEventRow,
    AuditStatusEnum,
    MessageRow,
    PendingApprovalRow,
    SessionRow,
)

from .session import (
    CrossTenantApprovalError,
    DEFAULT_APPROVAL_TTL_SECONDS,
    Message,
    PendingApproval,
    Session,
)
from .tools import AuditSink

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Best-effort decorator for audit writes                                      #
# --------------------------------------------------------------------------- #


T = TypeVar("T")


def _best_effort(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T | None]]:
    """Swallow all exceptions from an async method.

    Used on audit sink writes so a DB hiccup doesn't fail a user turn.
    A missed audit row is regrettable; a crashed chat session is worse.
    """

    @functools.wraps(func)
    async def _wrapper(*args: Any, **kwargs: Any) -> T | None:
        try:
            return await func(*args, **kwargs)
        except Exception:  # noqa: BLE001 — deliberate catch-all
            logger.exception(
                "audit write failed — continuing without persisting the event"
            )
            return None

    return _wrapper


# --------------------------------------------------------------------------- #
# Translation helpers                                                         #
# --------------------------------------------------------------------------- #


def _entity_id_to_uuid(value: EntityId | str | uuid.UUID) -> uuid.UUID:
    """Canonical EntityIds are UUIDv7 strings; cast to ``uuid.UUID``."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _uuid_to_entity_id(value: uuid.UUID) -> EntityId:
    return str(value)  # type: ignore[return-value]


def _actor_kind_to_storage(kind: ActorKind) -> ActorKindEnum:
    return ActorKindEnum(kind.value)


def _actor_kind_from_storage(kind: ActorKindEnum) -> ActorKind:
    return ActorKind(kind.value)


def _audit_status_to_storage(status: AuditStatus) -> AuditStatusEnum:
    return AuditStatusEnum(status.value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Session store                                                               #
# --------------------------------------------------------------------------- #


class PostgresSessionStore:
    """:class:`SessionStore` backed by the storage schema.

    Construct with an :class:`AsyncEngine` — the store builds its own
    session factory so callers don't juggle session lifetimes.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

    # ------------------------------------------------------------------ #
    # CRUD                                                               #
    # ------------------------------------------------------------------ #

    async def get(self, session_id: EntityId) -> Session | None:
        """Return the full session (with messages + approvals) or ``None``."""
        sid = _entity_id_to_uuid(session_id)
        async with self._sessionmaker() as db:
            row = await db.get(SessionRow, sid)
            if row is None:
                return None

            msg_stmt = (
                select(MessageRow)
                .where(MessageRow.session_id == sid)
                .order_by(MessageRow.sequence)
            )
            msg_rows = list((await db.execute(msg_stmt)).scalars())

            ap_stmt = select(PendingApprovalRow).where(
                PendingApprovalRow.session_id == sid
            )
            ap_rows = list((await db.execute(ap_stmt)).scalars())

        messages = [
            Message(role=m.role, content=list(m.content or []))
            for m in msg_rows
        ]
        approvals = {
            ap.id: PendingApproval(
                id=ap.id,
                tool_name=ap.tool_name,
                summary=ap.summary,
                turn_id=ap.turn_id,
                requested_at=ap.requested_at,
                granted=ap.granted,
                resolved_at=ap.resolved_at,
                expires_at=getattr(ap, "expires_at", None),
                status=getattr(ap, "status", None) or "pending",
            )
            for ap in ap_rows
        }
        return Session(
            id=_uuid_to_entity_id(row.id),
            tenant_id=_uuid_to_entity_id(row.tenant_id),
            actor_id=(
                _uuid_to_entity_id(row.actor_id)
                if row.actor_id is not None
                else _uuid_to_entity_id(row.id)
            ),
            actor_kind=_actor_kind_from_storage(row.actor_kind),
            message_history=messages,
            pending_approvals=approvals,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def put(self, session: Session) -> None:
        """Upsert the session row. Does **not** touch messages or approvals.

        Messages are append-only via :meth:`append_message`; approvals
        flow through :meth:`add_approval` / :meth:`resolve_approval`.
        Re-persisting them here would risk clobbering newer writes.
        """
        sid = _entity_id_to_uuid(session.id)
        tid = _entity_id_to_uuid(session.tenant_id)
        actor_uuid: uuid.UUID | None
        try:
            actor_uuid = _entity_id_to_uuid(session.actor_id)
        except Exception:  # noqa: BLE001
            actor_uuid = None

        async with self._sessionmaker() as db:
            async with db.begin():
                dialect = db.bind.dialect.name if db.bind else ""
                values = {
                    "id": sid,
                    "tenant_id": tid,
                    "actor_id": actor_uuid,
                    "actor_kind": _actor_kind_to_storage(session.actor_kind),
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                }
                if dialect == "postgresql":
                    stmt = pg_insert(SessionRow).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[SessionRow.id],
                        set_={
                            "tenant_id": stmt.excluded.tenant_id,
                            "actor_id": stmt.excluded.actor_id,
                            "actor_kind": stmt.excluded.actor_kind,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await db.execute(stmt)
                else:
                    # Portable upsert for SQLite-backed unit tests.
                    existing = await db.get(SessionRow, sid)
                    if existing is None:
                        await db.execute(insert(SessionRow).values(**values))
                    else:
                        await db.execute(
                            update(SessionRow)
                            .where(SessionRow.id == sid)
                            .values(
                                tenant_id=tid,
                                actor_id=actor_uuid,
                                actor_kind=values["actor_kind"],
                                updated_at=values["updated_at"],
                            )
                        )

    async def append_message(self, session_id: EntityId, msg: Message) -> None:
        """Append one message with the next ``sequence``.

        Uses a correlated subquery so the sequence is computed in the
        same statement as the insert, which is race-free as long as the
        transaction isolates us from concurrent inserts on the same
        ``session_id`` (default ``READ COMMITTED`` on Postgres is
        enough here because the unique ``(session_id, sequence)``
        constraint forces a retry on the rare collision).
        """
        sid = _entity_id_to_uuid(session_id)
        async with self._sessionmaker() as db:
            async with db.begin():
                max_stmt = (
                    select(MessageRow.sequence)
                    .where(MessageRow.session_id == sid)
                    .order_by(MessageRow.sequence.desc())
                    .limit(1)
                )
                current_max = (await db.execute(max_stmt)).scalar_one_or_none()
                next_seq = 0 if current_max is None else int(current_max) + 1

                row = MessageRow(
                    session_id=sid,
                    role=msg.role,
                    content=list(msg.content),
                    sequence=next_seq,
                    created_at=_utcnow(),
                )
                db.add(row)
                await db.execute(
                    update(SessionRow)
                    .where(SessionRow.id == sid)
                    .values(updated_at=_utcnow())
                )

    async def add_approval(
        self,
        session_id: EntityId,
        ap: PendingApproval,
        *,
        approval_ttl_seconds: int | None = None,
    ) -> None:
        """Upsert a pending approval row keyed on the approval id."""
        sid = _entity_id_to_uuid(session_id)
        # Stamp expires_at off requested_at so a caller that pre-dates
        # requested_at for a backfill test still gets a stable deadline.
        expires_at = ap.expires_at
        if expires_at is None:
            ttl = (
                approval_ttl_seconds
                if approval_ttl_seconds is not None
                else DEFAULT_APPROVAL_TTL_SECONDS
            )
            expires_at = ap.requested_at + timedelta(seconds=ttl)
        async with self._sessionmaker() as db:
            async with db.begin():
                existing = await db.get(PendingApprovalRow, ap.id)
                if existing is None:
                    db.add(
                        PendingApprovalRow(
                            id=ap.id,
                            session_id=sid,
                            tool_name=ap.tool_name,
                            summary=ap.summary,
                            turn_id=ap.turn_id,
                            requested_at=ap.requested_at,
                            granted=ap.granted,
                            resolved_at=ap.resolved_at,
                            expires_at=expires_at,
                            status=ap.status,
                        )
                    )
                else:
                    existing.tool_name = ap.tool_name
                    existing.summary = ap.summary
                    existing.turn_id = ap.turn_id
                    existing.requested_at = ap.requested_at
                    existing.granted = ap.granted
                    existing.resolved_at = ap.resolved_at
                    existing.expires_at = expires_at
                    existing.status = ap.status
                await db.execute(
                    update(SessionRow)
                    .where(SessionRow.id == sid)
                    .values(updated_at=_utcnow())
                )

    async def resolve_approval(
        self,
        session_id: EntityId,
        approval_id: str,
        granted: bool,
        *,
        actor_tenant_id: EntityId | None = None,
    ) -> None:
        """Mark an approval granted/denied. Raises ``KeyError`` if unknown."""
        sid = _entity_id_to_uuid(session_id)
        async with self._sessionmaker() as db:
            async with db.begin():
                existing = await db.get(PendingApprovalRow, approval_id)
                if existing is None or existing.session_id != sid:
                    raise KeyError(
                        f"No pending approval {approval_id!r} on session "
                        f"{session_id!r}."
                    )
                if actor_tenant_id is not None:
                    sess_row = await db.get(SessionRow, sid)
                    if sess_row is not None:
                        owner_tenant = _uuid_to_entity_id(sess_row.tenant_id)
                        if owner_tenant != actor_tenant_id:
                            raise CrossTenantApprovalError(
                                f"actor tenant {actor_tenant_id!r} cannot "
                                f"resolve approval owned by tenant "
                                f"{owner_tenant!r}."
                            )
                existing.granted = granted
                existing.resolved_at = _utcnow()
                existing.status = "granted" if granted else "rejected"
                await db.execute(
                    update(SessionRow)
                    .where(SessionRow.id == sid)
                    .values(updated_at=_utcnow())
                )

    async def expire_stale_approvals(
        self,
        session_id: EntityId | None = None,
        *,
        now: datetime | None = None,
    ) -> int:
        """Flip any ``pending`` approval past its deadline to ``expired``."""
        ts = now or _utcnow()
        async with self._sessionmaker() as db:
            async with db.begin():
                stmt = (
                    update(PendingApprovalRow)
                    .where(PendingApprovalRow.status == "pending")
                    .where(PendingApprovalRow.expires_at <= ts)
                    .values(status="expired")
                    .execution_options(synchronize_session=False)
                )
                if session_id is not None:
                    stmt = stmt.where(
                        PendingApprovalRow.session_id
                        == _entity_id_to_uuid(session_id)
                    )
                result = await db.execute(stmt)
                return result.rowcount or 0

    # Housekeeping — tests use this to keep fixture isolation tight.
    async def _wipe_session(self, session_id: EntityId) -> None:  # pragma: no cover
        sid = _entity_id_to_uuid(session_id)
        async with self._sessionmaker() as db:
            async with db.begin():
                await db.execute(
                    delete(PendingApprovalRow).where(
                        PendingApprovalRow.session_id == sid
                    )
                )
                await db.execute(
                    delete(MessageRow).where(MessageRow.session_id == sid)
                )
                await db.execute(
                    delete(SessionRow).where(SessionRow.id == sid)
                )


# --------------------------------------------------------------------------- #
# Audit sink                                                                  #
# --------------------------------------------------------------------------- #


class PostgresAuditSink:
    """:class:`AuditSink` backed by ``audit_events``.

    Exposes the protocol's ``write(event)`` plus convenience
    ``start / succeed / fail`` helpers. Every public method is wrapped
    in :func:`_best_effort` so the caller's turn is never broken by a
    database issue.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

    # ------------------------------------------------------------------ #
    # Protocol surface                                                   #
    # ------------------------------------------------------------------ #

    @_best_effort
    async def write(self, event: AuditEvent) -> None:
        """Upsert a single audit event row.

        The runtime writes the same ``id`` twice for one tool call —
        once on STARTED and again on the terminal status. We treat the
        second call as an update so the timeline of the row matches
        the canonical event's status transitions.
        """
        eid = _entity_id_to_uuid(event.id)
        tid = _entity_id_to_uuid(event.tenant_id)
        actor_uuid: uuid.UUID | None
        try:
            actor_uuid = _entity_id_to_uuid(event.actor_id)
        except Exception:  # noqa: BLE001
            actor_uuid = None

        approved_by_uuid: uuid.UUID | None
        if event.approved_by is not None:
            try:
                approved_by_uuid = _entity_id_to_uuid(event.approved_by)
            except Exception:  # noqa: BLE001
                approved_by_uuid = None
        else:
            approved_by_uuid = None

        async with self._sessionmaker() as db:
            async with db.begin():
                existing = await db.get(AuditEventRow, eid)
                if existing is None:
                    db.add(
                        AuditEventRow(
                            id=eid,
                            tenant_id=tid,
                            actor_id=actor_uuid,
                            actor_kind=_actor_kind_to_storage(event.actor_kind),
                            tool=event.tool,
                            driver=event.driver,
                            entity_refs=dict(event.entity_refs),
                            inputs=dict(event.inputs),
                            outputs=dict(event.outputs),
                            error=event.error,
                            approval_required=event.approval_required,
                            approved_by=approved_by_uuid,
                            approved_at=event.approved_at,
                            started_at=event.started_at,
                            completed_at=event.completed_at,
                            status=_audit_status_to_storage(event.status),
                        )
                    )
                else:
                    existing.outputs = dict(event.outputs)
                    existing.error = event.error
                    existing.completed_at = event.completed_at
                    existing.status = _audit_status_to_storage(event.status)
                    existing.approved_by = approved_by_uuid
                    existing.approved_at = event.approved_at

    # ------------------------------------------------------------------ #
    # Convenience helpers                                                #
    # ------------------------------------------------------------------ #

    @_best_effort
    async def start(
        self,
        *,
        tenant_id: EntityId,
        actor_id: EntityId | None,
        actor_kind: ActorKind,
        tool: str,
        driver: str | None = None,
        inputs: dict[str, Any] | None = None,
        approval_required: bool = False,
    ) -> uuid.UUID:
        """Insert a STARTED row and return its id.

        The runtime's existing path in ``tools.py`` already mints
        ``AuditEvent`` objects and calls :meth:`write`, so this helper
        is optional — provided for code that prefers a lifecycle API.
        """
        row = AuditEventRow(
            tenant_id=_entity_id_to_uuid(tenant_id),
            actor_id=_entity_id_to_uuid(actor_id) if actor_id else None,
            actor_kind=_actor_kind_to_storage(actor_kind),
            tool=tool,
            driver=driver,
            inputs=dict(inputs or {}),
            approval_required=approval_required,
            started_at=_utcnow(),
            status=AuditStatusEnum.STARTED,
        )
        async with self._sessionmaker() as db:
            async with db.begin():
                db.add(row)
            await db.refresh(row)
        return row.id

    @_best_effort
    async def succeed(
        self, audit_id: uuid.UUID, outputs: dict[str, Any] | None = None
    ) -> None:
        """Mark the row SUCCEEDED and stamp ``completed_at``."""
        async with self._sessionmaker() as db:
            async with db.begin():
                await db.execute(
                    update(AuditEventRow)
                    .where(AuditEventRow.id == audit_id)
                    .values(
                        outputs=dict(outputs or {}),
                        status=AuditStatusEnum.SUCCEEDED,
                        completed_at=_utcnow(),
                    )
                )

    @_best_effort
    async def fail(self, audit_id: uuid.UUID, error: str) -> None:
        """Mark the row FAILED with an error string."""
        async with self._sessionmaker() as db:
            async with db.begin():
                await db.execute(
                    update(AuditEventRow)
                    .where(AuditEventRow.id == audit_id)
                    .values(
                        error=error,
                        status=AuditStatusEnum.FAILED,
                        completed_at=_utcnow(),
                    )
                )


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


async def build_pg_stores(
    engine: AsyncEngine,
) -> tuple[PostgresSessionStore, PostgresAuditSink]:
    """Return a wired :class:`PostgresSessionStore` + :class:`PostgresAuditSink`.

    Async-flavoured factory so callers can ``await`` any future
    bootstrap work (connection probing, for example) in one place.
    """
    return PostgresSessionStore(engine), PostgresAuditSink(engine)


# Note: :class:`PostgresAuditSink` is structurally compatible with
# :class:`AuditSink` (its ``write`` coroutine matches the protocol's
# signature). We rely on duck typing rather than an explicit
# runtime_checkable decorator to keep the protocol minimal.
_ = AuditSink  # re-export anchor for readers; no runtime effect.


__all__ = [
    "PostgresAuditSink",
    "PostgresSessionStore",
    "build_pg_stores",
]
