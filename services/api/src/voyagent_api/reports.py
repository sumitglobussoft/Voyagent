"""Finance + itinerary reporting endpoints.

Read-only aggregation surface for a travel agency's finance team:

* ``GET /reports/receivables`` — what clients owe us, bucketed by age.
* ``GET /reports/payables``   — what we owe vendors, bucketed by age.
* ``GET /reports/itinerary``  — structured itinerary for a chat session.

Every endpoint is authenticated and tenant-scoped. Tenant isolation is
enforced by filtering every query with the ``tenant_id`` taken from the
caller's verified JWT principal (``AuthenticatedPrincipal.tenant_id``)
— callers cannot pass a tenant id on the wire.

v0 note: the finance storage tables (invoices, bills, ledger entries)
do not exist yet. Rather than 500-ing, the finance endpoints return a
well-formed empty result so dashboards can wire up today and start
showing real numbers as soon as the invoice / BSP drivers land.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage.session import MessageRow, SessionRow

from .auth_inhouse.deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
)

router = APIRouter(prefix="/reports", tags=["reports"])


# --------------------------------------------------------------------------- #
# Response models                                                             #
# --------------------------------------------------------------------------- #

_DEFAULT_CURRENCY = "INR"


class MoneyResponse(BaseModel):
    """Minimal money shape for report responses.

    We deliberately do NOT reuse :class:`schemas.canonical.Money` here
    because it is a strict model with extra-field bans; locally scoping
    the response keeps the router independent of canonical churn.
    """

    model_config = ConfigDict(extra="forbid")

    amount: Decimal
    currency: str = _DEFAULT_CURRENCY


def _zero(currency: str = _DEFAULT_CURRENCY) -> MoneyResponse:
    return MoneyResponse(amount=Decimal("0.00"), currency=currency)


class PeriodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: date = Field(
        alias="from",
        serialization_alias="from",
    )
    to: date


class AgingBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    count: int
    amount: MoneyResponse


class PartyAmount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    amount: MoneyResponse


class AgingReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    period: PeriodResponse
    total_outstanding: MoneyResponse
    aging_buckets: list[AgingBucket]
    top_debtors: list[PartyAmount] = Field(default_factory=list)
    top_creditors: list[PartyAmount] = Field(default_factory=list)


class PassengerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    passport_number: str | None = None


class FlightItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pnr: str | None = None
    origin: str | None = None
    dest: str | None = None
    depart: str | None = None
    carrier: str | None = None


class HotelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    city: str | None = None
    check_in: str | None = None
    check_out: str | None = None


class VisaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: str | None = None
    status: str | None = None


class ItineraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    session_id: str
    passengers: list[PassengerItem] = Field(default_factory=list)
    flights: list[FlightItem] = Field(default_factory=list)
    hotels: list[HotelItem] = Field(default_factory=list)
    visas: list[VisaItem] = Field(default_factory=list)
    total_cost: MoneyResponse


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


_EMPTY_BUCKETS = ("0-30", "31-60", "61-90", "90+")


def _empty_buckets(currency: str = _DEFAULT_CURRENCY) -> list[AgingBucket]:
    return [
        AgingBucket(bucket=name, count=0, amount=_zero(currency))
        for name in _EMPTY_BUCKETS
    ]


def _validate_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must be on or before to",
        )


def _tenant_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.tenant_id)
    except ValueError as exc:  # pragma: no cover — JWT shouldn't carry garbage
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


# --------------------------------------------------------------------------- #
# /reports/receivables                                                        #
# --------------------------------------------------------------------------- #


@router.get(
    "/receivables",
    response_model=AgingReportResponse,
    response_model_by_alias=True,
)
async def receivables_report(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    _session: AsyncSession = Depends(db_session),
) -> AgingReportResponse:
    """Aging of unpaid customer invoices.

    Returns empty aggregates until the invoice storage driver lands —
    there are no ``invoices`` or ``invoice_lines`` tables yet, so
    aggregating them would be meaningless. The response shape is final
    so dashboards can bind to it today.
    """
    _validate_period(date_from, date_to)
    return AgingReportResponse(
        tenant_id=principal.tenant_id,
        period=PeriodResponse.model_validate(
            {"from": date_from, "to": date_to}
        ),
        total_outstanding=_zero(),
        aging_buckets=_empty_buckets(),
        top_debtors=[],
    )


# --------------------------------------------------------------------------- #
# /reports/payables                                                           #
# --------------------------------------------------------------------------- #


@router.get(
    "/payables",
    response_model=AgingReportResponse,
    response_model_by_alias=True,
)
async def payables_report(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    _session: AsyncSession = Depends(db_session),
) -> AgingReportResponse:
    """Aging of unpaid vendor bills (airlines via BSP, hotels, visa agents).

    Returns empty aggregates until the bill / BSP storage drivers land.
    """
    _validate_period(date_from, date_to)
    return AgingReportResponse(
        tenant_id=principal.tenant_id,
        period=PeriodResponse.model_validate(
            {"from": date_from, "to": date_to}
        ),
        total_outstanding=_zero(),
        aging_buckets=_empty_buckets(),
        top_creditors=[],
    )


# --------------------------------------------------------------------------- #
# /reports/itinerary                                                          #
# --------------------------------------------------------------------------- #


def _extract_itinerary_blocks(messages: list[MessageRow]) -> dict[str, list[Any]]:
    """Best-effort scan of message tool_result / tool_use blocks for itinerary bits.

    The agent may eventually persist structured itinerary data via a
    dedicated booking store; until then we scrape whatever structured
    content is already in ``messages.content``.
    """
    # TODO: wire once booking store lands
    passengers: list[PassengerItem] = []
    flights: list[FlightItem] = []
    hotels: list[HotelItem] = []
    visas: list[VisaItem] = []

    for msg in messages:
        content = msg.content
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            data = block.get("data") if isinstance(block.get("data"), dict) else None
            if data is None:
                continue
            kind = data.get("kind") or block.get("kind")
            try:
                if kind == "passenger":
                    passengers.append(PassengerItem.model_validate(data.get("value", {})))
                elif kind == "flight":
                    flights.append(FlightItem.model_validate(data.get("value", {})))
                elif kind == "hotel":
                    hotels.append(HotelItem.model_validate(data.get("value", {})))
                elif kind == "visa":
                    visas.append(VisaItem.model_validate(data.get("value", {})))
            except Exception:  # noqa: BLE001
                # Malformed structured payloads are ignored — this is a
                # read-only report, never a hard failure path.
                continue

    return {
        "passengers": passengers,
        "flights": flights,
        "hotels": hotels,
        "visas": visas,
    }


@router.get("/itinerary", response_model=ItineraryResponse)
async def itinerary_report(
    session_id: str = Query(..., min_length=1),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> ItineraryResponse:
    """Return the structured itinerary built so far for a single chat session.

    404 is returned when the session doesn't exist OR belongs to a
    different tenant — the two are deliberately indistinguishable to
    avoid leaking existence across tenant boundaries.
    """
    tenant_uuid = _tenant_uuid(principal)

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc

    row = (
        await session.execute(
            select(SessionRow).where(
                SessionRow.id == session_uuid,
                SessionRow.tenant_id == tenant_uuid,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    messages = (
        (
            await session.execute(
                select(MessageRow)
                .where(MessageRow.session_id == row.id)
                .order_by(MessageRow.sequence)
            )
        )
        .scalars()
        .all()
    )

    parts = _extract_itinerary_blocks(list(messages))

    return ItineraryResponse(
        tenant_id=principal.tenant_id,
        session_id=session_id,
        passengers=parts["passengers"],
        flights=parts["flights"],
        hotels=parts["hotels"],
        visas=parts["visas"],
        total_cost=_zero(),
    )


__all__ = ["router"]
