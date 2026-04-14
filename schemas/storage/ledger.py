"""Ledger storage — chart of accounts and double-entry journal.

:class:`LedgerAccountRow` is a lightweight chart of accounts. Accounts
are tenant-scoped; tenants share no account rows.

:class:`JournalEntryRow` is one posting line. Multiple lines sharing an
``entry_id`` form a balanced journal entry (sum of debits equals sum of
credits). The balance invariant is enforced at the write helper
(:func:`post_journal_entry`) — NOT via a database trigger. A trigger
would be a portability nightmare across Postgres/SQLite test DBs and
would hide the failure mode from tests that exercise the write path.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import (
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDType, tenant_id_fk, uuid7, uuid_pk


class LedgerAccountTypeEnum(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


LEDGER_ACCOUNT_TYPE_SATYPE = SAEnum(
    LedgerAccountTypeEnum,
    name="ledger_account_type",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


_AMOUNT_TYPE = Numeric(14, 2)


class LedgerAccountRow(Base, Timestamps):
    """A single line in the chart of accounts."""

    __tablename__ = "ledger_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[LedgerAccountTypeEnum] = mapped_column(
        LEDGER_ACCOUNT_TYPE_SATYPE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="1",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", name="ux_ledger_accounts_tenant_code"
        ),
        Index(
            "ix_ledger_accounts_tenant_active",
            "tenant_id",
            "is_active",
        ),
    )


class JournalEntryRow(Base):
    """One line of a double-entry journal posting.

    Multiple rows sharing ``entry_id`` form a single balanced entry.
    Primary key is ``(entry_id, line_no)`` so line ordering is stable
    and a line can be referenced deterministically.
    """

    __tablename__ = "journal_entries"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        primary_key=True,
    )
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)

    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    debit: Mapped[Decimal] = mapped_column(
        _AMOUNT_TYPE,
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )
    credit: Mapped[Decimal] = mapped_column(
        _AMOUNT_TYPE,
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index(
            "ix_journal_entries_tenant_posted",
            "tenant_id",
            "posted_at",
        ),
        Index("ix_journal_entries_entry", "entry_id"),
    )


# --------------------------------------------------------------------------- #
# Write helper — enforces debit = credit at application layer                 #
# --------------------------------------------------------------------------- #


class UnbalancedJournalEntryError(ValueError):
    """Raised when the sum of debits does not equal the sum of credits.

    Enforcement lives here (not in a DB trigger) so it is portable
    across Postgres and SQLite, and so tests can assert on it without
    depending on backend-specific error mapping.
    """


@dataclass(frozen=True)
class JournalLine:
    account_id: uuid.UUID
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")
    memo: str | None = None


def _q(value: Decimal | int | float | str) -> Decimal:
    # Normalise to a two-place Decimal without going via float.
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(Decimal("0.01"))


def build_journal_entry(
    *,
    tenant_id: uuid.UUID,
    lines: Sequence[JournalLine],
    posted_at: datetime | None = None,
    source: str | None = None,
    entry_id: uuid.UUID | None = None,
) -> list[JournalEntryRow]:
    """Build balanced :class:`JournalEntryRow` instances or raise.

    * Requires at least two lines (a single-line "entry" cannot be
      balanced unless it is zero, which is meaningless).
    * Each line must have non-negative ``debit`` and ``credit`` and
      exactly one of the two non-zero (the usual double-entry rule).
    * Sum of debits across all lines must equal sum of credits.

    Returns the built rows (caller adds them to a session and commits).
    """
    if len(lines) < 2:
        raise UnbalancedJournalEntryError(
            "journal entry requires at least two lines"
        )

    rows: list[JournalEntryRow] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    eid = entry_id or uuid7()
    when = posted_at or datetime.now(timezone.utc)

    for idx, line in enumerate(lines, start=1):
        debit = _q(line.debit)
        credit = _q(line.credit)
        if debit < 0 or credit < 0:
            raise UnbalancedJournalEntryError(
                "journal line debit/credit must be non-negative"
            )
        if (debit > 0) == (credit > 0):
            # Both zero, or both non-zero — both invalid.
            raise UnbalancedJournalEntryError(
                "journal line must have exactly one of debit / credit non-zero"
            )
        total_debit += debit
        total_credit += credit
        rows.append(
            JournalEntryRow(
                entry_id=eid,
                line_no=idx,
                tenant_id=tenant_id,
                account_id=line.account_id,
                debit=debit,
                credit=credit,
                memo=line.memo,
                posted_at=when,
                source=source,
            )
        )

    if total_debit != total_credit:
        raise UnbalancedJournalEntryError(
            f"journal entry unbalanced: debits={total_debit} "
            f"credits={total_credit}"
        )

    return rows


__all__ = [
    "LEDGER_ACCOUNT_TYPE_SATYPE",
    "JournalEntryRow",
    "JournalLine",
    "LedgerAccountRow",
    "LedgerAccountTypeEnum",
    "UnbalancedJournalEntryError",
    "build_journal_entry",
]
