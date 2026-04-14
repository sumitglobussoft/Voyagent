"""Enquiries HTTP surface — agency-side CRUD for customer travel enquiries.

An enquiry is the earliest pipeline artifact: an agent logs a prospect's
intent (route, dates, pax, budget, notes) and can later promote the row
to a chat session owned by the agentic runtime.

Tenant isolation is enforced on every query via the caller's JWT
principal. The wire format never carries a ``tenant_id``; it is always
sourced from :class:`AuthenticatedPrincipal`.

Soft-delete via ``status=cancelled`` is the contract — there is no
``DELETE`` endpoint. ``cancelled`` and ``booked`` are terminal: you
cannot transition back to ``new`` or ``quoted`` (policy: resolved
states stay resolved until a dedicated reopen path lands).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage.enquiry import EnquiryRow, EnquiryStatusEnum
from schemas.storage.session import ActorKindEnum, SessionRow

from .auth_inhouse.deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])


# --------------------------------------------------------------------------- #
# Response models                                                             #
# --------------------------------------------------------------------------- #


StatusFilter = Literal["new", "quoted", "booked", "cancelled", "all"]
ValidStatus = Literal["new", "quoted", "booked", "cancelled"]


_TERMINAL_STATUSES = frozenset(
    {EnquiryStatusEnum.BOOKED, EnquiryStatusEnum.CANCELLED}
)
_OPEN_STATUSES = frozenset(
    {EnquiryStatusEnum.NEW, EnquiryStatusEnum.QUOTED}
)


class EnquiryResponse(BaseModel):
    """Wire shape of one enquiry row."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    created_by_user_id: str
    customer_name: str
    customer_email: str | None = None
    customer_phone: str | None = None
    origin: str | None = None
    destination: str | None = None
    depart_date: date | None = None
    return_date: date | None = None
    pax_count: int
    budget_amount: Decimal | None = None
    budget_currency: str | None = None
    status: str
    notes: str | None = None
    session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class EnquiryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EnquiryResponse]
    total: int
    limit: int
    offset: int


# Body models ---------------------------------------------------------------- #


_CURRENCY_FIELD_DOC = (
    "ISO-4217 alpha code — three uppercase letters. The API does not "
    "validate the code against a registry; it only enforces shape."
)


class EnquiryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=64)
    origin: str | None = Field(default=None, max_length=128)
    destination: str | None = Field(default=None, max_length=128)
    depart_date: date | None = None
    return_date: date | None = None
    pax_count: int = 1
    budget_amount: Decimal | None = None
    budget_currency: str | None = Field(
        default=None, description=_CURRENCY_FIELD_DOC
    )
    status: ValidStatus = "new"
    notes: str | None = Field(default=None, max_length=10_000)
    session_id: str | None = None


class EnquiryPatchRequest(BaseModel):
    """PATCH body. Omitted fields leave the column alone; explicit nulls clear it.

    Pydantic v2's ``model_fields_set`` distinguishes "field provided with
    value ``None``" (clear the column) from "field not provided at all"
    (leave the column alone), which is exactly the semantic we want.
    """

    model_config = ConfigDict(extra="forbid")

    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=64)
    origin: str | None = Field(default=None, max_length=128)
    destination: str | None = Field(default=None, max_length=128)
    depart_date: date | None = None
    return_date: date | None = None
    pax_count: int | None = None
    budget_amount: Decimal | None = None
    budget_currency: str | None = None
    status: ValidStatus | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    session_id: str | None = None


class PromoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enquiry: EnquiryResponse
    session_id: str


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


def _user_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.user_id)
    except ValueError as exc:  # pragma: no cover — JWT must carry a UUID.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


def _parse_enquiry_id(raw: str) -> uuid.UUID:
    """Parse the path param. 404 on bad UUID so we don't leak existence."""
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail="enquiry_not_found"
        ) from exc


def _validate_currency(code: str | None) -> None:
    """Shape check on ISO-4217 codes — three uppercase ASCII letters."""
    if code is None:
        return
    if len(code) != 3 or not code.isascii() or not code.isupper() or not code.isalpha():
        raise HTTPException(status_code=400, detail="invalid_currency")


def _validate_date_range(
    depart: date | None, return_: date | None
) -> None:
    if depart is not None and return_ is not None and return_ < depart:
        raise HTTPException(status_code=400, detail="invalid_date_range")


def _validate_pax(pax: int | None) -> None:
    if pax is not None and pax < 1:
        raise HTTPException(status_code=400, detail="invalid_pax_count")


def _validate_status_transition(
    existing: EnquiryStatusEnum, new: EnquiryStatusEnum
) -> None:
    """Block re-opening a terminal enquiry.

    Terminal = ``cancelled`` or ``booked``. Transitioning from either
    back to ``new`` or ``quoted`` is refused. Terminal -> terminal
    (e.g., ``booked`` -> ``cancelled``) is allowed as a corrective
    action.
    """
    if existing in _TERMINAL_STATUSES and new in _OPEN_STATUSES:
        raise HTTPException(
            status_code=400, detail="invalid_status_transition"
        )


def _row_to_response(row: EnquiryRow) -> EnquiryResponse:
    status_value = (
        row.status.value
        if isinstance(row.status, EnquiryStatusEnum)
        else str(row.status)
    )
    return EnquiryResponse(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        created_by_user_id=str(row.created_by_user_id),
        customer_name=row.customer_name,
        customer_email=row.customer_email,
        customer_phone=row.customer_phone,
        origin=row.origin,
        destination=row.destination,
        depart_date=row.depart_date,
        return_date=row.return_date,
        pax_count=row.pax_count,
        budget_amount=row.budget_amount,
        budget_currency=row.budget_currency,
        status=status_value,
        notes=row.notes,
        session_id=str(row.session_id) if row.session_id is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_session_id_or_none(raw: str | None) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="invalid_session_id"
        ) from exc


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #


@router.post(
    "",
    response_model=EnquiryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_enquiry(
    body: EnquiryCreateRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> EnquiryResponse:
    """Log a new customer enquiry against the caller's tenant."""
    tenant_uuid = _tenant_uuid(principal)
    user_uuid = _user_uuid(principal)

    _validate_currency(body.budget_currency)
    _validate_date_range(body.depart_date, body.return_date)
    _validate_pax(body.pax_count)

    session_uuid = _parse_session_id_or_none(body.session_id)

    row = EnquiryRow(
        tenant_id=tenant_uuid,
        created_by_user_id=user_uuid,
        customer_name=body.customer_name,
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        origin=body.origin,
        destination=body.destination,
        depart_date=body.depart_date,
        return_date=body.return_date,
        pax_count=body.pax_count,
        budget_amount=body.budget_amount,
        budget_currency=body.budget_currency,
        status=EnquiryStatusEnum(body.status),
        notes=body.notes,
        session_id=session_uuid,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


@router.get("", response_model=EnquiryListResponse)
async def list_enquiries(
    enquiry_status: StatusFilter = Query("all", alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=255),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> EnquiryListResponse:
    """List enquiries for the caller's tenant, most-recent-first."""
    tenant_uuid = _tenant_uuid(principal)

    base = select(EnquiryRow).where(EnquiryRow.tenant_id == tenant_uuid)
    count_base = (
        select(func.count())
        .select_from(EnquiryRow)
        .where(EnquiryRow.tenant_id == tenant_uuid)
    )

    if enquiry_status != "all":
        enum_value = EnquiryStatusEnum(enquiry_status)
        base = base.where(EnquiryRow.status == enum_value)
        count_base = count_base.where(EnquiryRow.status == enum_value)

    if q:
        pattern = f"%{q}%"
        # Case-insensitive substring match across the searchable text
        # columns. SQLAlchemy's ``ilike`` maps to Postgres ILIKE and
        # falls back to LIKE on SQLite (which already matches case-
        # insensitively by default for ASCII).
        search_clause = or_(
            EnquiryRow.customer_name.ilike(pattern),
            EnquiryRow.customer_email.ilike(pattern),
            EnquiryRow.customer_phone.ilike(pattern),
            EnquiryRow.origin.ilike(pattern),
            EnquiryRow.destination.ilike(pattern),
        )
        base = base.where(search_clause)
        count_base = count_base.where(search_clause)

    total = int((await db.execute(count_base)).scalar_one() or 0)
    rows = (
        (
            await db.execute(
                base.order_by(EnquiryRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return EnquiryListResponse(
        items=[_row_to_response(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _load_owned_enquiry(
    db: AsyncSession,
    *,
    enquiry_uuid: uuid.UUID,
    tenant_uuid: uuid.UUID,
) -> EnquiryRow:
    row = (
        await db.execute(
            select(EnquiryRow).where(
                EnquiryRow.id == enquiry_uuid,
                EnquiryRow.tenant_id == tenant_uuid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="enquiry_not_found")
    return row


@router.get("/{enquiry_id}", response_model=EnquiryResponse)
async def get_enquiry(
    enquiry_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> EnquiryResponse:
    """Fetch a single enquiry. 404 on cross-tenant."""
    tenant_uuid = _tenant_uuid(principal)
    enquiry_uuid = _parse_enquiry_id(enquiry_id)
    row = await _load_owned_enquiry(
        db, enquiry_uuid=enquiry_uuid, tenant_uuid=tenant_uuid
    )
    return _row_to_response(row)


@router.patch("/{enquiry_id}", response_model=EnquiryResponse)
async def patch_enquiry(
    enquiry_id: str,
    body: EnquiryPatchRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> EnquiryResponse:
    """Partial update. Omitted fields are left alone; explicit nulls clear them.

    Blocks re-opening a terminal enquiry (``cancelled`` / ``booked`` ->
    ``new`` / ``quoted``).
    """
    tenant_uuid = _tenant_uuid(principal)
    enquiry_uuid = _parse_enquiry_id(enquiry_id)
    row = await _load_owned_enquiry(
        db, enquiry_uuid=enquiry_uuid, tenant_uuid=tenant_uuid
    )

    # Determine final (post-patch) values for cross-field validation.
    patch = body.model_dump(exclude_unset=True)

    final_depart = (
        patch["depart_date"] if "depart_date" in patch else row.depart_date
    )
    final_return = (
        patch["return_date"] if "return_date" in patch else row.return_date
    )
    final_currency = (
        patch["budget_currency"]
        if "budget_currency" in patch
        else row.budget_currency
    )
    final_pax = patch["pax_count"] if "pax_count" in patch else row.pax_count

    _validate_currency(final_currency)
    _validate_date_range(final_depart, final_return)
    _validate_pax(final_pax)

    if "status" in patch and patch["status"] is not None:
        new_status = EnquiryStatusEnum(patch["status"])
        _validate_status_transition(row.status, new_status)
        row.status = new_status
    elif "status" in patch and patch["status"] is None:
        # Explicit null on a NOT NULL column — reject at the schema layer.
        raise HTTPException(
            status_code=422,
            detail="status_cannot_be_null",
        )

    # Simple column updates
    simple_fields = (
        "customer_name",
        "customer_email",
        "customer_phone",
        "origin",
        "destination",
        "depart_date",
        "return_date",
        "pax_count",
        "budget_amount",
        "budget_currency",
        "notes",
    )
    for field_name in simple_fields:
        if field_name not in patch:
            continue
        value = patch[field_name]
        # customer_name and pax_count are NOT NULL — reject explicit null.
        if value is None and field_name in ("customer_name", "pax_count"):
            raise HTTPException(
                status_code=422,
                detail=f"{field_name}_cannot_be_null",
            )
        setattr(row, field_name, value)

    if "session_id" in patch:
        value = patch["session_id"]
        if value is None:
            row.session_id = None
        else:
            try:
                row.session_id = uuid.UUID(str(value))
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=422, detail="invalid_session_id"
                ) from exc

    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


@router.post("/{enquiry_id}/promote-to-session", response_model=PromoteResponse)
async def promote_to_session(
    enquiry_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> PromoteResponse:
    """Attach a chat session to the enquiry. Idempotent.

    If the enquiry already has a ``session_id``, the existing id is
    returned without touching it — so retries / duplicate clicks never
    mint extra sessions.
    """
    tenant_uuid = _tenant_uuid(principal)
    user_uuid = _user_uuid(principal)
    enquiry_uuid = _parse_enquiry_id(enquiry_id)

    row = await _load_owned_enquiry(
        db, enquiry_uuid=enquiry_uuid, tenant_uuid=tenant_uuid
    )

    if row.session_id is not None:
        return PromoteResponse(
            enquiry=_row_to_response(row),
            session_id=str(row.session_id),
        )

    # Mint a session row directly. We do not go through the agent
    # runtime's session_store here on purpose — doing so would couple
    # enquiry promotion to the runtime's readiness. The chat surface
    # reads from the same ``sessions`` table and will pick up the row
    # on the next ``GET /chat/sessions/{id}``.
    new_session = SessionRow(
        tenant_id=tenant_uuid,
        actor_id=user_uuid,
        actor_kind=ActorKindEnum.HUMAN,
    )
    db.add(new_session)
    await db.flush()
    row.session_id = new_session.id
    await db.commit()
    await db.refresh(row)

    return PromoteResponse(
        enquiry=_row_to_response(row),
        session_id=str(new_session.id),
    )


# Decimal silences a re-export lint on unused but public symbols.
_ = InvalidOperation


__all__ = ["router"]
