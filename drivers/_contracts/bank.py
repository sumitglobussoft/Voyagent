"""BankDriver — bank account integrations.

`BankTransaction` is a driver-layer type — a normalized view of a single
statement line. Canonical `Payment` records are created upstream, by the
reconciliation flow that matches bank transactions to agency payments.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

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


class BankTransaction(BaseModel):
    """One bank statement line, normalized across banks.

    Driver-layer type. The reconciliation pipeline turns matched lines into
    canonical `Payment` / `Receipt` records — this type itself is never
    persisted directly as canonical data.
    """

    model_config = _driver_type_config()

    date: date
    description: str
    amount: Money = Field(description="Always positive; direction is carried separately.")
    reference: str = Field(description="Bank-assigned reference, UTR, cheque number, or narration key.")
    direction: PaymentDirection


@runtime_checkable
class BankDriver(Driver, Protocol):
    """Read bank statements and initiate outbound transfers."""

    async def fetch_statement(
        self,
        account_id: EntityId,
        period: Period,
    ) -> list[BankTransaction]:
        """Fetch statement lines for the account over the period.

        Side effects: none. Idempotent: yes for closed periods; lines within
        today's date may shift until end-of-day settlement.

        Raises:
            NotFoundError (account unknown), AuthenticationError,
            AuthorizationError, RateLimitError, TransientError,
            UpstreamTimeoutError.
        """
        ...

    async def initiate_transfer(
        self,
        amount: Money,
        beneficiary: EntityId,
        metadata: dict[str, Any],
    ) -> Payment:
        """Initiate an outbound transfer to a saved beneficiary.

        Side effects: YES — moves money via NEFT / RTGS / IMPS / SEPA /
        ACH / Fedwire depending on the bank. Approval gating is enforced
        by the tool runtime before the driver is called.
        Idempotent: NO at the wire level. Runtime passes a client-side
        request key in `metadata`; the key name is declared in the manifest.

        Raises:
            CapabilityNotSupportedError (rail unavailable),
            ValidationFailedError (beneficiary not registered or limits
            exceeded), AuthorizationError, RateLimitError, TransientError,
            PermanentError, UpstreamTimeoutError.
        """
        ...


__all__ = ["BankDriver", "BankTransaction"]
