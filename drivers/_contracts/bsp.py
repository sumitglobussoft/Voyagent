"""BSPDriver — IATA Billing & Settlement Plan integrations.

BSP operates per-country. `country` on every call drives which driver
handles the request (BSP-India vs BSP-UK vs BSP-UAE differ in file formats,
submission cycles, and ADM/ACM workflows).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.canonical import (
    BSPReport,
    CountryCode,
    EntityId,
    LocalizedText,
    Payment,
    Period,
)

from .base import Driver


@runtime_checkable
class BSPDriver(Driver, Protocol):
    """Fetch BSP statements, raise memos, settle remittance."""

    async def fetch_statement(
        self,
        country: CountryCode,
        period: Period,
    ) -> BSPReport:
        """Download and parse the BSP settlement statement for a country
        + period.

        Side effects: none (read-only). Idempotent: yes. Statement files
        are immutable once published by BSP, so caching by (country, period)
        is safe.

        Raises:
            NotFoundError (statement not yet published for this period),
            AuthenticationError, TransientError, PermanentError,
            UpstreamTimeoutError.
        """
        ...

    async def raise_adm(self, reference: str, reason: LocalizedText) -> str:
        """Raise an Agency Debit Memo dispute or lodgement.

        Side effects: YES — posts to the BSPlink / ADM workflow.
        Idempotent: NO — repeated calls may create duplicate memos. Runtime
        dedupes via `reference` + driver-local request keys.

        Returns the BSP-assigned ADM reference number.

        Raises:
            ValidationFailedError, AuthorizationError, ConflictError,
            TransientError, PermanentError.
        """
        ...

    async def raise_acm(self, reference: str, reason: LocalizedText) -> str:
        """Raise an Agency Credit Memo.

        Side effects: YES. Idempotency: same pattern as `raise_adm`.

        Returns the BSP-assigned ACM reference number.

        Raises:
            ValidationFailedError, AuthorizationError, ConflictError,
            TransientError, PermanentError.
        """
        ...

    async def make_settlement_payment(self, report_id: EntityId) -> Payment:
        """Trigger the net remittance payment for a settlement report.

        Side effects: YES — moves money from the agency's BSP account to
        IATA. Approval gating is enforced by the tool runtime first.
        Idempotent: NO at the wire level; runtime must confirm prior
        settlement by `read_status` on the returned Payment before retrying.

        Raises:
            ConflictError (already settled, or report not settleable yet),
            AuthorizationError, PermanentError, UpstreamTimeoutError.
        """
        ...


__all__ = ["BSPDriver"]
