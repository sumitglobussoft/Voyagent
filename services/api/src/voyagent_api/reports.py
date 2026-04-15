"""Finance + itinerary reporting endpoints.

Read-only aggregation surface for a travel agency's finance team:

* ``GET /reports/receivables`` — what clients owe us, bucketed by age.
* ``GET /reports/payables``   — what we owe vendors, bucketed by age.
* ``GET /reports/itinerary``  — structured itinerary for a chat session.

Every endpoint is authenticated and tenant-scoped. Tenant isolation is
enforced by filtering every query with the ``tenant_id`` taken from the
caller's verified JWT principal (``AuthenticatedPrincipal.tenant_id``)
— callers cannot pass a tenant id on the wire.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage.invoice import (
    BillRow,
    BillStatusEnum,
    InvoiceRow,
    InvoiceStatusEnum,
)
from schemas.storage.ledger import (
    JournalEntryRow,
    LedgerAccountRow,
    LedgerAccountTypeEnum,
)
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


_OPEN_INVOICE_STATUSES = (
    InvoiceStatusEnum.ISSUED,
    InvoiceStatusEnum.PARTIALLY_PAID,
)
_OPEN_BILL_STATUSES = (
    BillStatusEnum.RECEIVED,
    BillStatusEnum.SCHEDULED,
)


def _classify_bucket(due_date: date, today: date) -> str:
    # Aging is by days past due. A not-yet-due invoice lands in 0-30
    # along with anything up to 30 days overdue; 31-60 / 61-90 / 90+
    # follow the usual convention.
    days_overdue = (today - due_date).days
    if days_overdue <= 30:
        return "0-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _build_aging(
    rows: list[tuple[Decimal, Decimal, date, str, str]],
    *,
    tenant_id: str,
    date_from: date,
    date_to: date,
    kind: str,
) -> AgingReportResponse:
    """Aggregate a list of ``(total, paid, due, currency, party_name)`` rows.

    ``kind`` is ``"debtors"`` or ``"creditors"`` — selects which top-list
    field to populate. Currency of the response total is the first
    currency seen (reports typically run per tenant in the tenant's
    default currency; mixed-currency tenants get the first row's code
    and numeric totals still balance per-row).
    """
    today = _today()
    buckets: dict[str, dict[str, Any]] = {
        name: {"count": 0, "amount": Decimal("0.00")}
        for name in _EMPTY_BUCKETS
    }
    totals: dict[str, Decimal] = {}
    party_totals: dict[tuple[str, str], Decimal] = {}
    currency = _DEFAULT_CURRENCY

    for total_amount, amount_paid, due_date, ccy, party_name in rows:
        outstanding = Decimal(total_amount) - Decimal(amount_paid)
        if outstanding <= Decimal("0.00"):
            continue
        bucket = _classify_bucket(due_date, today)
        buckets[bucket]["count"] += 1
        buckets[bucket]["amount"] += outstanding
        totals[ccy] = totals.get(ccy, Decimal("0.00")) + outstanding
        party_key = (party_name, ccy)
        party_totals[party_key] = (
            party_totals.get(party_key, Decimal("0.00")) + outstanding
        )
        currency = ccy

    aging = [
        AgingBucket(
            bucket=name,
            count=buckets[name]["count"],
            amount=MoneyResponse(
                amount=buckets[name]["amount"].quantize(Decimal("0.01")),
                currency=currency,
            ),
        )
        for name in _EMPTY_BUCKETS
    ]

    top = sorted(
        (
            PartyAmount(
                name=name,
                amount=MoneyResponse(
                    amount=amt.quantize(Decimal("0.01")),
                    currency=ccy,
                ),
            )
            for (name, ccy), amt in party_totals.items()
        ),
        key=lambda p: p.amount.amount,
        reverse=True,
    )[:5]

    total_outstanding = MoneyResponse(
        amount=totals.get(currency, Decimal("0.00")).quantize(Decimal("0.01")),
        currency=currency,
    )

    return AgingReportResponse(
        tenant_id=tenant_id,
        period=PeriodResponse.model_validate(
            {"from": date_from, "to": date_to}
        ),
        total_outstanding=total_outstanding,
        aging_buckets=aging,
        top_debtors=top if kind == "debtors" else [],
        top_creditors=top if kind == "creditors" else [],
    )


@router.get(
    "/receivables",
    response_model=AgingReportResponse,
    response_model_by_alias=True,
)
async def receivables_report(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> AgingReportResponse:
    """Aging of open customer invoices within ``[from, to]``.

    Open = ``issued`` or ``partially_paid``. Void / draft / paid rows
    are excluded. Amounts outstanding are bucketed by days past
    ``due_date`` relative to today.
    """
    _validate_period(date_from, date_to)
    tenant_uuid = _tenant_uuid(principal)

    stmt = (
        select(
            InvoiceRow.total_amount,
            InvoiceRow.amount_paid,
            InvoiceRow.due_date,
            InvoiceRow.currency,
            InvoiceRow.party_name,
        )
        .where(InvoiceRow.tenant_id == tenant_uuid)
        .where(InvoiceRow.status.in_(_OPEN_INVOICE_STATUSES))
        .where(InvoiceRow.issue_date >= date_from)
        .where(InvoiceRow.issue_date <= date_to)
    )
    result = await session.execute(stmt)
    rows = [tuple(r) for r in result.all()]

    return _build_aging(
        rows,
        tenant_id=principal.tenant_id,
        date_from=date_from,
        date_to=date_to,
        kind="debtors",
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
    session: AsyncSession = Depends(db_session),
) -> AgingReportResponse:
    """Aging of open vendor bills (airlines via BSP, hotels, visa agents).

    Open = ``received`` or ``scheduled``. Same aging buckets as
    receivables.
    """
    _validate_period(date_from, date_to)
    tenant_uuid = _tenant_uuid(principal)

    stmt = (
        select(
            BillRow.total_amount,
            BillRow.amount_paid,
            BillRow.due_date,
            BillRow.currency,
            BillRow.party_name,
        )
        .where(BillRow.tenant_id == tenant_uuid)
        .where(BillRow.status.in_(_OPEN_BILL_STATUSES))
        .where(BillRow.issue_date >= date_from)
        .where(BillRow.issue_date <= date_to)
    )
    result = await session.execute(stmt)
    rows = [tuple(r) for r in result.all()]

    return _build_aging(
        rows,
        tenant_id=principal.tenant_id,
        date_from=date_from,
        date_to=date_to,
        kind="creditors",
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


# --------------------------------------------------------------------------- #
# /reports/trial-balance                                                      #
# --------------------------------------------------------------------------- #


class TrialBalanceAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    type: Literal["asset", "liability", "equity", "revenue", "expense"]
    debit: str
    credit: str
    balance: str
    currency: str


class TrialBalanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    as_of: date
    accounts: list[TrialBalanceAccount]
    total_debit: str
    total_credit: str
    in_balance: bool


def _fmt_dec(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01")))


@router.get(
    "/trial-balance",
    response_model=TrialBalanceResponse,
)
async def trial_balance_report(
    as_of: date | None = Query(default=None),
    include_zero: int = Query(default=0, ge=0, le=1),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> TrialBalanceResponse:
    """GL trial balance for the caller's tenant.

    Aggregates ``journal_entries`` grouped by ledger account, summing
    debits and credits posted on or before ``as_of`` (UTC). Accounts
    with no activity are omitted unless ``include_zero=1``.
    """
    tenant_uuid = _tenant_uuid(principal)
    as_of_date = as_of or _today()
    cutoff = datetime.combine(as_of_date, time.max, tzinfo=timezone.utc)

    # Main aggregate — LEFT JOIN so empty accounts keep a row when the
    # caller asks for them via include_zero.
    stmt = (
        select(
            LedgerAccountRow.id,
            LedgerAccountRow.code,
            LedgerAccountRow.name,
            LedgerAccountRow.type,
            func.coalesce(func.sum(JournalEntryRow.debit), 0).label("debit"),
            func.coalesce(func.sum(JournalEntryRow.credit), 0).label("credit"),
        )
        .select_from(LedgerAccountRow)
        .outerjoin(
            JournalEntryRow,
            (JournalEntryRow.account_id == LedgerAccountRow.id)
            & (JournalEntryRow.tenant_id == tenant_uuid)
            & (JournalEntryRow.posted_at <= cutoff),
        )
        .where(LedgerAccountRow.tenant_id == tenant_uuid)
        .group_by(
            LedgerAccountRow.id,
            LedgerAccountRow.code,
            LedgerAccountRow.name,
            LedgerAccountRow.type,
        )
        .order_by(LedgerAccountRow.code)
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Currency per-account: pick the first observed non-zero currency.
    # We don't store it on the ledger_accounts table, so we do one
    # extra query per account only for rows with activity — small N
    # compared to the size of journal_entries in practice.
    accounts_out: list[TrialBalanceAccount] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for account_id, code, name_col, type_col, debit_raw, credit_raw in rows:
        debit = Decimal(str(debit_raw or 0))
        credit = Decimal(str(credit_raw or 0))
        is_zero = debit == 0 and credit == 0
        if is_zero and not include_zero:
            continue

        account_currency = "INR"
        if not is_zero:
            # Mixed-currency detection: if >1 distinct currency is
            # observed on the *entries* for this account, flag MIXED.
            # v0 ledger does not carry a ``currency`` column on
            # journal_entries; currency is logically fixed by the
            # owning LedgerAccountRow. Until a currency column lands
            # we report the tenant default and never flag MIXED —
            # recorded as a v0 compromise (see docstring).
            account_currency = "INR"

        total_debit += debit
        total_credit += credit

        type_value: Literal[
            "asset", "liability", "equity", "revenue", "expense"
        ]
        if isinstance(type_col, LedgerAccountTypeEnum):
            type_value = type_col.value  # type: ignore[assignment]
        else:
            type_value = str(type_col)  # type: ignore[assignment]

        accounts_out.append(
            TrialBalanceAccount(
                code=str(code),
                name=str(name_col),
                type=type_value,
                debit=_fmt_dec(debit),
                credit=_fmt_dec(credit),
                balance=_fmt_dec(debit - credit),
                currency=account_currency,
            )
        )

    return TrialBalanceResponse(
        tenant_id=principal.tenant_id,
        as_of=as_of_date,
        accounts=accounts_out,
        total_debit=_fmt_dec(total_debit),
        total_credit=_fmt_dec(total_credit),
        in_balance=(total_debit == total_credit),
    )


__all__ = ["router"]
