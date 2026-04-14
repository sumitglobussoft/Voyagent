"""CardDriver — corporate / agency credit card integrations.

Mirrors `BankDriver` on the card side. Supports statement fetch for
reconciliation, dispute-driven refunds, and utilization tracking so the
orchestrator can warn before a card is over-limit.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from schemas.canonical import (
    EntityId,
    Money,
    Payment,
    PaymentDirection,
    Period,
)

from .base import Driver


def _driver_type_config() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CardTransaction(BaseModel):
    """One card statement line, normalized across issuers.

    Driver-layer type; see `BankTransaction` for the same rationale.
    """

    model_config = _driver_type_config()

    date: date
    merchant: str
    amount: Money = Field(description="Always positive; direction is carried separately.")
    reference: str = Field(description="Issuer-assigned authorization or posting reference.")
    direction: PaymentDirection = Field(
        description="OUTBOUND for a charge, INBOUND for a refund or credit.",
    )
    merchant_category: str | None = Field(
        default=None,
        description="MCC or issuer-local category label when present.",
    )


class CardUtilization(BaseModel):
    """A card's current-cycle utilization snapshot.

    Driver-layer type. Used by the orchestrator to gate further use of the
    card before the limit is breached.
    """

    model_config = _driver_type_config()

    limit: Money
    outstanding: Money = Field(description="Posted balance already charged against the limit.")
    available: Money = Field(description="limit - outstanding - pending_authorizations.")
    statement_due_date: date | None = None


@runtime_checkable
class CardDriver(Driver, Protocol):
    """Read card statements, initiate refunds, track utilization."""

    async def fetch_statement(
        self,
        card_id: EntityId,
        period: Period,
    ) -> list[CardTransaction]:
        """Fetch card transactions for the period.

        Side effects: none. Idempotent: yes for closed cycles; pending
        authorizations may change until posted.

        Raises:
            NotFoundError, AuthenticationError, TransientError,
            UpstreamTimeoutError.
        """
        ...

    async def initiate_refund(
        self,
        transaction_ref: str,
        amount: Money | None = None,
    ) -> Payment:
        """Initiate a refund / chargeback on a posted transaction.

        Side effects: YES — moves money. `amount=None` means full reversal.
        Idempotent: NO at the wire level; runtime passes a request key.

        Raises:
            ConflictError (not refundable, outside window),
            ValidationFailedError (amount exceeds original),
            AuthorizationError, TransientError, PermanentError,
            UpstreamTimeoutError.
        """
        ...

    async def track_utilization(self, card_id: EntityId) -> CardUtilization:
        """Return the current utilization snapshot.

        Side effects: none. Idempotent: yes (freshness is best-effort).

        Raises:
            NotFoundError, AuthenticationError, TransientError.
        """
        ...


__all__ = ["CardDriver", "CardTransaction", "CardUtilization"]
