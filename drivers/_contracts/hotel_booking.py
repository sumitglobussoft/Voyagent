"""HotelBookingDriver — confirming and managing hotel bookings."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.canonical import EntityId, HotelBooking, HotelStay

from .base import Driver


@runtime_checkable
class HotelBookingDriver(Driver, Protocol):
    """Book, cancel, and read hotel reservations with a supplier.

    Typically paired with a `HotelSearchDriver` from the same vendor, but a
    tenant may shop through one driver (e.g. a metasearch aggregator) and
    book through another (direct with the property).
    """

    async def book(self, offer_ref: str, stay: HotelStay) -> HotelBooking:
        """Confirm the previously-shopped offer into a supplier booking.

        Side effects: YES — creates vendor-side booking and typically
        encumbers payment on the tenant's agency account.
        Idempotent: NO on first call. Runtime must dedupe via a client-side
        request key; on UpstreamTimeoutError, read by offer_ref or supplier
        search before retrying.

        Raises:
            ConflictError (offer expired or inventory gone),
            ValidationFailedError, AuthorizationError, RateLimitError,
            TransientError, PermanentError, UpstreamTimeoutError.
        """
        ...

    async def cancel(self, booking_id: EntityId) -> HotelBooking:
        """Cancel the hotel booking.

        Side effects: YES — cancels at the supplier. Refund rules are
        supplier-specific and expressed through the original cancellation
        policy; this call only commits the cancellation.
        Idempotent: yes (cancelling a cancelled booking returns current state).

        Raises:
            ConflictError (outside cancellation window), NotFoundError,
            AuthorizationError, plus standard transport errors.
        """
        ...

    async def read(self, booking_id: EntityId) -> HotelBooking:
        """Fetch the current state of a hotel booking from the supplier.

        Side effects: none. Idempotent: yes.

        Raises:
            NotFoundError, AuthenticationError, TransientError,
            UpstreamTimeoutError.
        """
        ...


__all__ = ["HotelBookingDriver"]
