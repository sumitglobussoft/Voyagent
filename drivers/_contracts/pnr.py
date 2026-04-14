"""PNRDriver — reservation lifecycle against a GDS or airline-direct system."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.canonical import PNR, EntityId, Ticket

from .base import Driver


@runtime_checkable
class PNRDriver(Driver, Protocol):
    """Create, read, modify, cancel PNRs; issue and void tickets.

    All methods that change vendor-side state are flagged in their docstring.
    Issuance and void emit `AuditEvent`s at the tool runtime — the driver
    itself only performs the vendor call.
    """

    async def create(
        self,
        fare_ids: list[EntityId],
        passenger_ids: list[EntityId],
    ) -> PNR:
        """Create a new PNR holding the given fares for the given passengers.

        Side effects: YES — creates vendor-side reservation.
        Idempotent: NO — retries may produce duplicate PNRs. Runtime must
        dedupe via client-side request keys or by reading back by locator.

        Raises:
            AuthenticationError, AuthorizationError, ValidationFailedError,
            ConflictError (e.g. fare expired), RateLimitError, TransientError,
            PermanentError, UpstreamTimeoutError.
        """
        ...

    async def read(self, locator: str) -> PNR:
        """Fetch a PNR by its vendor record locator.

        Side effects: none. Idempotent: yes.

        Raises:
            NotFoundError if the locator is unknown to the vendor; plus the
            standard auth / transport errors.
        """
        ...

    async def cancel(self, pnr_id: EntityId) -> PNR:
        """Cancel all segments on a PNR.

        Side effects: YES — cancels vendor-side reservation.
        Idempotent: yes (cancelling a cancelled PNR is a no-op; returns
        current state).

        Raises:
            NotFoundError, ConflictError (e.g. ticketed beyond cancel window),
            AuthorizationError, plus the standard transport errors.
        """
        ...

    async def queue_read(self, queue_number: int) -> list[PNR]:
        """Read the PNRs on a GDS queue.

        Side effects: none (does not remove items from the queue; pop/move
        is a separate operation a future capability may expose).
        Idempotent: yes.

        Raises:
            AuthenticationError, AuthorizationError, NotFoundError if the
            queue does not exist, TransientError, UpstreamTimeoutError.
        """
        ...

    async def issue_ticket(self, pnr_id: EntityId) -> list[Ticket]:
        """Issue e-tickets for every ticketable fare on the PNR.

        Side effects: YES — creates tickets and charges BSP / agency account.
        Irreversible without an explicit void (see `void_ticket`). Approval
        gating is enforced by the tool runtime before the driver is called.
        Idempotent: NO — caller must check PNR state before retrying on
        UpstreamTimeoutError.

        Raises:
            ConflictError (PNR not ticketable), ValidationFailedError,
            AuthorizationError, PermanentError, plus standard transport errors.
        """
        ...

    async def void_ticket(self, ticket_id: EntityId) -> Ticket:
        """Void an issued ticket while still within the void window.

        Side effects: YES — reverses a ticket at BSP before settlement.
        Idempotent: yes (voiding a voided ticket returns current state).

        Raises:
            ConflictError if outside the void window (use refund flow
            instead), NotFoundError, AuthorizationError, plus standard errors.
        """
        ...


__all__ = ["PNRDriver"]
