"""StatutoryDriver — statutory tax filings.

GST-India, TDS, VAT-UK (HMRC), VAT-EU, VAT-UAE, SST-Malaysia, IRS filings
all plug into this one contract. The `regime` parameter selects the
filing family; drivers advertise which regimes they implement through
their manifest's `capabilities` map (e.g. `"filing.gst_india.gstr1": "full"`).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from schemas.canonical import Period, TaxRegime

from .base import Driver


@runtime_checkable
class StatutoryDriver(Driver, Protocol):
    """Compute, file, and track the status of statutory returns."""

    async def compute_return(
        self,
        regime: TaxRegime,
        period: Period,
    ) -> dict[str, Any]:
        """Compute the return payload for the given regime + period.

        Returns a driver-local dict — the exact schema differs per regime
        and is declared in the driver's manifest / README. Canonicalizing
        return payloads is deferred; the structures are too regime-specific
        to usefully normalize in v0.

        Side effects: none. Idempotent: yes (pure function of the books
        on the day of computation).

        Raises:
            CapabilityNotSupportedError (regime not implemented here),
            ValidationFailedError (books not ready for the period),
            TransientError.
        """
        ...

    async def file_return(
        self,
        regime: TaxRegime,
        period: Period,
        payload: dict[str, Any],
    ) -> str:
        """Submit a previously-computed return to the authority.

        Side effects: YES — submits to the government. Irreversible;
        corrections require a revised-return workflow (driver-specific).
        Approval gating is enforced by the tool runtime before this call.
        Idempotent: NO. Runtime passes a request key; on timeout, confirm
        with `read_filing_status` before retrying.

        Returns the authority-assigned filing reference.

        Raises:
            CapabilityNotSupportedError, ValidationFailedError,
            AuthorizationError, ConflictError (period already filed),
            TransientError, PermanentError, UpstreamTimeoutError.
        """
        ...

    async def read_filing_status(self, filing_ref: str) -> str:
        """Read the current status of a submitted filing.

        Returns a driver-local status string (e.g. `'accepted'`,
        `'pending_verification'`, `'rejected:<reason>'`). Canonical statuses
        are deferred until the regime landscape settles.

        Side effects: none. Idempotent: yes.

        Raises:
            NotFoundError, AuthenticationError, TransientError.
        """
        ...


__all__ = ["StatutoryDriver"]
