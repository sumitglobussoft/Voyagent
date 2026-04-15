"""Approvals HTTP surface — list + resolve pending agent tool approvals.

The storage side already exists (``pending_approvals`` + ``approval_status``
enum + ``expires_at``). The agent runtime writes approvals via its own
session store; this module is the *human* side of the loop — the web UI
calls these routes to see what's waiting on a human decision and to
grant / reject each item.

Tenant isolation is enforced by joining through :class:`SessionRow` and
filtering on ``session.tenant_id == principal.tenant_id``. Callers can
never pass a tenant id on the wire.

Cross-tenant probes return 404 (not 403) deliberately — a 403 would
confirm that the approval id exists in some tenant, leaking existence.
This matches the convention already used by ``/reports/itinerary``.

Expiry is handled lazily: ``GET /api/approvals`` runs a sweep that flips
any ``pending`` rows past their ``expires_at`` to ``expired`` before
returning results, so the UI never shows a stale ``pending`` row.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage.audit import AuditEventRow, AuditStatusEnum
from schemas.storage.session import (
    ActorKindEnum,
    ApprovalStatusEnum,
    PendingApprovalRow,
    SessionRow,
)

from .auth_inhouse.deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


# --------------------------------------------------------------------------- #
# Response models                                                             #
# --------------------------------------------------------------------------- #


StatusFilter = Literal["pending", "granted", "rejected", "expired", "all"]

_RESOLVED_STATUSES = frozenset(
    {
        ApprovalStatusEnum.GRANTED,
        ApprovalStatusEnum.REJECTED,
        ApprovalStatusEnum.EXPIRED,
    }
)


class ApprovalItem(BaseModel):
    """Shape of one approval row on the wire.

    ``payload`` mirrors the tool-call args for the UI. The current
    ``pending_approvals`` schema does not carry the raw payload column
    yet, so this field is always ``{}`` — kept in the response so the
    wire shape is stable once a later migration adds a payload column.
    ``resolved_by_user_id`` is similarly always ``null`` today (there
    is no column to persist it) — populated once the column lands.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    tool_name: str
    summary: str
    requested_at: datetime
    expires_at: datetime | None
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    resolved_at: datetime | None = None
    resolved_by_user_id: str | None = None


class ApprovalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ApprovalItem]
    total: int
    limit: int
    offset: int


class ResolveApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    granted: bool
    reason: str | None = Field(default=None, max_length=1024)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _tenant_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.tenant_id)
    except ValueError as exc:  # pragma: no cover — JWT must carry a UUID.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_item(row: PendingApprovalRow) -> ApprovalItem:
    status_value = (
        row.status.value
        if isinstance(row.status, ApprovalStatusEnum)
        else str(row.status)
    )
    return ApprovalItem(
        id=row.id,
        session_id=str(row.session_id),
        tool_name=row.tool_name,
        summary=row.summary,
        requested_at=row.requested_at,
        expires_at=row.expires_at,
        status=status_value,
        payload={},
        resolved_at=row.resolved_at,
        resolved_by_user_id=None,
    )


async def _sweep_expired(
    session: AsyncSession, *, tenant_uuid: uuid.UUID
) -> None:
    """Flip any tenant-owned ``pending`` rows past their deadline to ``expired``.

    Lazy sweep on list requests so there is no background job and the
    UI is guaranteed to see the correct status. Scoped to the caller's
    tenant for tight blast radius.
    """
    now = _utcnow()
    tenant_sessions = select(SessionRow.id).where(
        SessionRow.tenant_id == tenant_uuid
    )
    stmt = (
        update(PendingApprovalRow)
        .where(PendingApprovalRow.status == ApprovalStatusEnum.PENDING)
        .where(PendingApprovalRow.expires_at.is_not(None))
        .where(PendingApprovalRow.expires_at <= now)
        .where(PendingApprovalRow.session_id.in_(tenant_sessions))
        .values(status=ApprovalStatusEnum.EXPIRED)
        .execution_options(synchronize_session=False)
    )
    await session.execute(stmt)
    await session.commit()


def _parse_session_id(session_id: str | None) -> uuid.UUID | None:
    if session_id is None:
        return None
    try:
        return uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_session_id",
        ) from exc


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    approval_status: StatusFilter = Query("pending", alias="status"),
    session_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> ApprovalListResponse:
    """List approvals for the caller's tenant.

    Runs a lazy expiry sweep before the query so stale rows are not
    returned as ``pending``.
    """
    tenant_uuid = _tenant_uuid(principal)
    sid = _parse_session_id(session_id)

    await _sweep_expired(db, tenant_uuid=tenant_uuid)

    base = (
        select(PendingApprovalRow)
        .join(SessionRow, SessionRow.id == PendingApprovalRow.session_id)
        .where(SessionRow.tenant_id == tenant_uuid)
    )
    count_base = (
        select(func.count())
        .select_from(PendingApprovalRow)
        .join(SessionRow, SessionRow.id == PendingApprovalRow.session_id)
        .where(SessionRow.tenant_id == tenant_uuid)
    )

    if approval_status != "all":
        enum_value = ApprovalStatusEnum(approval_status)
        base = base.where(PendingApprovalRow.status == enum_value)
        count_base = count_base.where(PendingApprovalRow.status == enum_value)

    if sid is not None:
        base = base.where(PendingApprovalRow.session_id == sid)
        count_base = count_base.where(PendingApprovalRow.session_id == sid)

    total = int((await db.execute(count_base)).scalar_one() or 0)

    rows = (
        (
            await db.execute(
                base.order_by(PendingApprovalRow.requested_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return ApprovalListResponse(
        items=[_row_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{approval_id}", response_model=ApprovalItem)
async def get_approval(
    approval_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> ApprovalItem:
    """Return a single approval. 404 for cross-tenant or unknown ids."""
    tenant_uuid = _tenant_uuid(principal)

    stmt = (
        select(PendingApprovalRow)
        .join(SessionRow, SessionRow.id == PendingApprovalRow.session_id)
        .where(PendingApprovalRow.id == approval_id)
        .where(SessionRow.tenant_id == tenant_uuid)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="approval_not_found")
    return _row_to_item(row)


@router.post("/{approval_id}/resolve", response_model=ApprovalItem)
async def resolve_approval_endpoint(
    approval_id: str,
    body: ResolveApprovalRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> ApprovalItem:
    """Grant or reject a pending approval.

    Errors:

    * 404 ``approval_not_found`` — unknown id OR cross-tenant.
      Deliberately 404 (not 403) to avoid leaking existence across
      tenant boundaries.
    * 409 ``approval_already_resolved`` — the row's status is no longer
      ``pending`` (already granted / rejected / expired).
    """
    tenant_uuid = _tenant_uuid(principal)

    # Fetch the row and its owning session in one join so we never read
    # a row we shouldn't. ``session_row`` gives us the tenant check.
    stmt = (
        select(PendingApprovalRow, SessionRow)
        .join(SessionRow, SessionRow.id == PendingApprovalRow.session_id)
        .where(PendingApprovalRow.id == approval_id)
    )
    result = (await db.execute(stmt)).first()
    if result is None:
        raise HTTPException(status_code=404, detail="approval_not_found")

    row: PendingApprovalRow = result[0]
    session_row: SessionRow = result[1]

    if session_row.tenant_id != tenant_uuid:
        # Cross-tenant — return 404 so callers cannot probe existence.
        # The spec calls out forbidden_cross_tenant as a distinct 403
        # path for the session-store API (which knows the approval id
        # is valid). At the HTTP surface we refuse to confirm the id
        # exists at all, per the same rationale as /reports/itinerary.
        raise HTTPException(status_code=404, detail="approval_not_found")

    # Guard against double-resolution. ``expired`` is a terminal state
    # too — the lazy sweep may have flipped the row between the UI
    # reading it and the user clicking ``grant``.
    if row.status in _RESOLVED_STATUSES:
        raise HTTPException(
            status_code=409, detail="approval_already_resolved"
        )

    now = _utcnow()
    # Cheap belt-and-braces: if the row is past its deadline, treat the
    # resolution as too-late and transition to ``expired`` rather than
    # silently accepting a stale grant. SQLite roundtrips datetimes
    # without tz, so normalize both sides to UTC before comparing.
    deadline = row.expires_at
    if deadline is not None:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline <= now:
            row.status = ApprovalStatusEnum.EXPIRED
            await db.commit()
            raise HTTPException(
                status_code=409, detail="approval_already_resolved"
            )

    row.granted = body.granted
    row.resolved_at = now
    row.status = (
        ApprovalStatusEnum.GRANTED
        if body.granted
        else ApprovalStatusEnum.REJECTED
    )

    # ``reason`` is accepted on the wire but cannot be persisted to the
    # current ``pending_approvals`` schema. Log it so an operator can
    # correlate after the fact; a future migration will add a column.
    if body.reason:
        logger.info(
            "approval_resolve approval_id=%s granted=%s reason=%s "
            "resolver_user_id=%s tenant=%s",
            approval_id,
            body.granted,
            body.reason,
            principal.user_id,
            principal.tenant_id,
        )

    await db.commit()
    await db.refresh(row)

    # Write a corresponding audit_events row so the UI's audit log shows
    # ``approval.granted`` / ``approval.rejected`` entries. Best-effort —
    # a schema/DB hiccup here must not roll back the approval state
    # transition (losing an approval state is far worse than losing one
    # audit row). Mirrors the try/except style of ``record_auth_failure``.
    try:
        await _write_approval_audit(
            db,
            tenant_uuid=tenant_uuid,
            principal=principal,
            approval_id=approval_id,
            session_id=str(row.session_id),
            tool_name=row.tool_name,
            granted=body.granted,
            reason=body.reason,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "approval audit write failed approval_id=%s granted=%s: %s",
            approval_id,
            body.granted,
            exc,
        )

    return _row_to_item(row)


async def _write_approval_audit(
    db: AsyncSession,
    *,
    tenant_uuid: uuid.UUID,
    principal: AuthenticatedPrincipal,
    approval_id: str,
    session_id: str,
    tool_name: str,
    granted: bool,
    reason: str | None,
    now: datetime,
) -> None:
    """Insert one ``audit_events`` row describing this approval decision.

    Raises on DB errors so the caller's ``try/except`` can log-and-continue.
    """
    try:
        actor_uuid: uuid.UUID | None = uuid.UUID(principal.user_id)
    except ValueError:
        actor_uuid = None

    verb = "granted" if granted else "rejected"
    event_row = AuditEventRow(
        tenant_id=tenant_uuid,
        actor_id=actor_uuid,
        actor_kind=ActorKindEnum.HUMAN,
        tool=f"approval.{verb}",
        inputs={
            "approval_id": approval_id,
            "session_id": session_id,
            "tool_name": tool_name,
            "reason": reason,
        },
        outputs={},
        entity_refs={},
        started_at=now,
        completed_at=now,
        status=AuditStatusEnum.SUCCEEDED,
    )
    db.add(event_row)
    await db.commit()


__all__ = ["router"]
