"""Canonical <-> Tally conversion (pure functions, no I/O).

These are the heart of the driver: everything the rest of the codebase
needs to translate between Voyagent's canonical :mod:`schemas.canonical`
and Tally's XML shapes lives here.

**Sign convention.** Tally's ``ISDEEMEDPOSITIVE`` field is the opposite
of the more common accountant's "debits are positive" convention:

  - ``ISDEEMEDPOSITIVE=Yes`` means "this line behaves like a debit for
    the ledger's natural side". For asset/expense ledgers this *is* a
    debit; for income/liability/equity ledgers it is a credit by
    nominal sign but still marked ``Yes`` when it increases the book
    balance.
  - The monetary amount is typically signed: negative for the
    'Yes' side, positive for the 'No' side.

Voyagent's canonical :class:`JournalLine` carries either a ``debit`` or
a ``credit`` :class:`Money`. The driver maps them uniformly as:

  * ``debit``  -> ``ISDEEMEDPOSITIVE=Yes``, ``AMOUNT=-abs(value)``
  * ``credit`` -> ``ISDEEMEDPOSITIVE=No``,  ``AMOUNT=abs(value)``

This is the widely-documented Tally convention for journal vouchers and
is what most open-source Tally SDKs emit. It is NOT the only convention
that exists in the wild — some integrations flip it for sales vouchers.
See the driver :mod:`README` for the caveat; production deployments must
verify against their own chart of accounts before trusting automated
posting.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Final

from drivers._contracts.errors import PermanentError, ValidationFailedError
from schemas.canonical import (
    AccountType,
    EntityId,
    Invoice,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    LocalizedText,
    Money,
)

from .errors import DRIVER_NAME
from .xml_builder import (
    TallyLedgerEntry,
    build_post_journal_voucher,
    build_post_sales_voucher,
)
from .xml_parser import TallyLedger

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Parent-group -> canonical AccountType map                                   #
# --------------------------------------------------------------------------- #

# Keys are compared case-insensitively against the Tally ledger's PARENT
# text. Values are canonical AccountType. Unknown parents fall through to
# EXPENSE with a warning (see :func:`tally_ledger_to_account`).
_PARENT_TO_TYPE: Final[dict[str, AccountType]] = {
    # Assets
    "cash-in-hand": AccountType.ASSET,
    "bank accounts": AccountType.ASSET,
    "bank ocaccounts": AccountType.ASSET,  # Tally's overdraft variant
    "sundry debtors": AccountType.ASSET,
    "fixed assets": AccountType.ASSET,
    "investments": AccountType.ASSET,
    "loans & advances (asset)": AccountType.ASSET,
    "deposits (asset)": AccountType.ASSET,
    "stock-in-hand": AccountType.ASSET,
    "current assets": AccountType.ASSET,
    "misc. expenses (asset)": AccountType.ASSET,
    # Liabilities
    "sundry creditors": AccountType.LIABILITY,
    "duties & taxes": AccountType.LIABILITY,
    "loans (liability)": AccountType.LIABILITY,
    "secured loans": AccountType.LIABILITY,
    "unsecured loans": AccountType.LIABILITY,
    "provisions": AccountType.LIABILITY,
    "current liabilities": AccountType.LIABILITY,
    "bank od a/c": AccountType.LIABILITY,
    "suspense a/c": AccountType.LIABILITY,
    # Equity
    "capital account": AccountType.EQUITY,
    "reserves & surplus": AccountType.EQUITY,
    # Income
    "sales accounts": AccountType.INCOME,
    "direct incomes": AccountType.INCOME,
    "indirect incomes": AccountType.INCOME,
    # Expenses
    "purchase accounts": AccountType.EXPENSE,
    "direct expenses": AccountType.EXPENSE,
    "indirect expenses": AccountType.EXPENSE,
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _new_entity_id() -> EntityId:
    """Generate a UUIDv7-shaped id for driver-materialised records.

    Stdlib does not ship UUIDv7; we patch the version nibble on a uuid4.
    Only used when Tally does not give us a native id (e.g. a fresh
    LedgerAccount from a ledger master that has no EntityId upstream).
    """
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def _parse_opening_balance(raw: str | None) -> Decimal:
    """Parse Tally's opening-balance string.

    Tally may return values like ``"1800.00 Dr"`` or a bare number. Dr/Cr
    suffixes are informational — sign is driven by the ledger's natural
    side, which we don't need here because we only materialise the
    magnitude into :class:`LedgerAccount` (the canonical model does not
    carry opening balances directly).
    """
    if not raw:
        return Decimal("0")
    text = raw.strip().upper().replace("DR", "").replace("CR", "").strip()
    text = text.replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        logger.warning("tally: unparseable opening balance %r; treating as 0", raw)
        return Decimal("0")


def _infer_account_type(parent: str | None) -> AccountType:
    if not parent:
        logger.warning(
            "tally: ledger has no PARENT group; defaulting to EXPENSE. "
            "This is almost certainly wrong — verify the chart of accounts."
        )
        return AccountType.EXPENSE
    mapped = _PARENT_TO_TYPE.get(parent.strip().lower())
    if mapped is not None:
        return mapped
    logger.warning(
        "tally: unrecognised parent group %r; defaulting to EXPENSE. "
        "Add this group to mapping._PARENT_TO_TYPE if it is common in your chart.",
        parent,
    )
    return AccountType.EXPENSE


# --------------------------------------------------------------------------- #
# Public mappers                                                              #
# --------------------------------------------------------------------------- #


def tally_ledger_to_account(t: TallyLedger, tenant_id: EntityId) -> LedgerAccount:
    """Map a Tally ledger row to a canonical :class:`LedgerAccount`.

    The canonical ``code`` is populated from the Tally ledger name —
    Tally does not have a separate short code — and ``name.default``
    mirrors it. The currency is passed through if Tally reports one;
    otherwise ``None`` meaning 'account inherits the tenant base
    currency'.
    """
    account_type = _infer_account_type(t.parent)
    # Eagerly parse the opening balance so unparseable values surface as
    # warnings at mapping time rather than silently later.
    _parse_opening_balance(t.opening_balance_str)

    now = datetime.now(timezone.utc)
    currency = t.currency.strip().upper() if t.currency else None
    # Canonical currency is a 3-letter ISO-4217 code; Tally sometimes
    # returns symbols like '₹' or 'Rs.' — drop anything that doesn't fit.
    if currency is not None and not (len(currency) == 3 and currency.isalpha()):
        logger.debug("tally: dropping non-ISO currency symbol %r", currency)
        currency = None

    return LedgerAccount(
        id=_new_entity_id(),
        tenant_id=tenant_id,
        code=t.name,
        name=LocalizedText(default=t.name),
        type=account_type,
        currency=currency,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _resolve_ledger_name(
    resolver: Callable[[EntityId], str] | None,
    account_id: EntityId,
) -> str:
    """Resolve a canonical account id to a Tally ledger display name.

    The driver cannot post to Tally without knowing the ledger's display
    name, because Tally addresses ledgers by name, not by id. The resolver
    is injected by the runtime; raising here keeps the failure loud.
    """
    if resolver is None:
        raise PermanentError(
            DRIVER_NAME,
            "Tally mapping requires a ledger_name_resolver; none was configured on the driver.",
        )
    try:
        name = resolver(account_id)
    except KeyError as exc:
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Tally mapping: no ledger name known for account id {account_id!r}.",
        ) from exc
    if not isinstance(name, str) or not name.strip():
        raise ValidationFailedError(
            DRIVER_NAME,
            f"Tally mapping: resolver returned an empty name for account {account_id!r}.",
        )
    return name


def _journal_line_to_tally_entry(
    line: JournalLine,
    resolver: Callable[[EntityId], str] | None,
) -> TallyLedgerEntry:
    """Translate one canonical line into a Tally voucher row.

    See the module docstring for the sign convention. Debits carry
    ``ISDEEMEDPOSITIVE=Yes`` with a negative amount; credits carry
    ``ISDEEMEDPOSITIVE=No`` with a positive amount.
    """
    name = _resolve_ledger_name(resolver, line.account_id)
    if line.debit is not None:
        magnitude = line.debit.amount
        return TallyLedgerEntry(
            ledger_name=name,
            amount=-magnitude.copy_abs(),
            is_deemed_positive=True,
        )
    assert line.credit is not None  # JournalLine validator guarantees exactly one
    magnitude = line.credit.amount
    return TallyLedgerEntry(
        ledger_name=name,
        amount=magnitude.copy_abs(),
        is_deemed_positive=False,
    )


def journal_entry_to_tally_xml_body(
    entry: JournalEntry,
    company_name: str,
    ledger_name_resolver: Callable[[EntityId], str],
) -> bytes:
    """Serialize a canonical :class:`JournalEntry` as a Tally Import envelope.

    All lines are emitted under a single ``<VOUCHER VCHTYPE="Journal">``.
    The narration is taken from ``entry.narration.default`` — translations
    are not round-tripped because Tally has no per-language narration
    support. A sensible future extension would prepend a language tag.
    """
    entries = [_journal_line_to_tally_entry(line, ledger_name_resolver) for line in entry.lines]
    return build_post_journal_voucher(
        company_name,
        entry_date=entry.entry_date,
        narration=entry.narration.default,
        entries=entries,
    )


def invoice_to_tally_sales_voucher(
    invoice: Invoice,
    company_name: str,
    ledger_name_resolver: Callable[[EntityId], str],
) -> bytes:
    """Serialize a canonical :class:`Invoice` as a Tally Sales voucher.

    The mapping is deliberately simple: the client's debtor ledger is the
    'party' side (debit, ``ISDEEMEDPOSITIVE=Yes``, negative amount equal
    to ``grand_total``); each line's subtotal posts as a credit to the
    line's sales ledger (via the resolver), and each tax line posts as a
    credit to the configured duties-and-taxes ledger for that tax code.

    **Caveat.** This simple shape covers straightforward invoices but
    does not model Tally's inventory-driven Sales vouchers (``STOCKITEM``
    blocks). Tenants that run Tally in inventory mode will need a richer
    mapping keyed off their item masters — out of scope for v0.

    The caller is responsible for having registered appropriate
    resolver entries for:
      * ``invoice.client_id``                -> party ledger name
      * each ``line.references['sales_ledger_id']`` (optional)
      * each ``tax.references['tax_ledger_id']``    (optional)

    Where those references are missing, the mapping falls back to the
    (hardcoded) Tally defaults ``"Sales"`` and ``"Duties & Taxes"``
    respectively, which at least produces a postable voucher on most
    out-of-the-box charts.
    """
    party_ledger = _resolve_ledger_name(ledger_name_resolver, invoice.client_id)

    entries: list[TallyLedgerEntry] = []
    # Debtor side (party) — single line for the grand total.
    entries.append(
        TallyLedgerEntry(
            ledger_name=party_ledger,
            amount=-invoice.grand_total.amount.copy_abs(),
            is_deemed_positive=True,
        )
    )

    # Income side — one line per invoice line (subtotal) + one per tax line.
    for line in invoice.lines:
        sales_ref = line.references.get("sales_ledger_id") if line.references else None
        if sales_ref is not None:
            sales_ledger = _resolve_ledger_name(ledger_name_resolver, sales_ref)
        else:
            sales_ledger = "Sales"
        entries.append(
            TallyLedgerEntry(
                ledger_name=sales_ledger,
                amount=line.subtotal.amount.copy_abs(),
                is_deemed_positive=False,
            )
        )
        for tax in line.taxes:
            # Canonical TaxLine carries no EntityId reference by design;
            # fall back to Tally's conventional group ledger.
            entries.append(
                TallyLedgerEntry(
                    ledger_name="Duties & Taxes",
                    amount=tax.tax_amount.amount.copy_abs(),
                    is_deemed_positive=False,
                )
            )

    return build_post_sales_voucher(
        company_name,
        entry_date=invoice.issue_date,
        narration=(invoice.notes.default if invoice.notes else f"Invoice {invoice.invoice_number}"),
        entries=entries,
        voucher_number=invoice.invoice_number,
        reference=invoice.invoice_number,
    )


def money_with_currency(amount: Decimal, currency: str) -> Money:
    """Helper used by the driver when synthesising partial Money values."""
    return Money(amount=amount, currency=currency.upper())


__all__ = [
    "invoice_to_tally_sales_voucher",
    "journal_entry_to_tally_xml_body",
    "money_with_currency",
    "tally_ledger_to_account",
]
