"""PaymentDriver — collecting from clients and disbursing to suppliers.

One driver per payment rail. Razorpay, Stripe, Wise, PayU, HDFC NEFT, and
"manual cheque" are all peers here. Method-level capabilities (UPI on
Razorpay, SEPA on Wise) live in the manifest's `capabilities` map.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from schemas.canonical import EntityId, Money, Payment, PaymentMethod

from .base import Driver


@runtime_checkable
class PaymentDriver(Driver, Protocol):
    """Collect, disburse, refund, and read status of payments."""

    async def collect(
        self,
        amount: Money,
        method: PaymentMethod,
        counterparty_id: EntityId,
        metadata: dict[str, Any],
    ) -> Payment:
        """Initiate collection from the counterparty.

        Side effects: YES — typically creates a payment request or a
        one-time payment link. Actual settlement is asynchronous and is
        reported by webhook + `read_status`.
        Idempotent: NO at the wire level; runtime passes a client-side
        request key in `metadata` under a driver-specific key (the manifest
        declares the key name). Drivers that do not support idempotency keys
        must document the workaround in their README.

        Raises:
            CapabilityNotSupportedError (method not supported by rail),
            ValidationFailedError, AuthorizationError, RateLimitError,
            TransientError, PermanentError, UpstreamTimeoutError.
        """
        ...

    async def disburse(
        self,
        amount: Money,
        method: PaymentMethod,
        counterparty_id: EntityId,
        metadata: dict[str, Any],
    ) -> Payment:
        """Push funds out to the counterparty.

        Side effects: YES — moves money. Approval gating is enforced by the
        tool runtime before the driver is called.
        Idempotent: NO at the wire level (same idempotency-key pattern as
        `collect`). Retries without reconciliation can double-pay.

        Raises:
            CapabilityNotSupportedError, ValidationFailedError,
            AuthorizationError, RateLimitError, TransientError,
            PermanentError, UpstreamTimeoutError.
        """
        ...

    async def read_status(self, payment_id: EntityId) -> Payment:
        """Read current status of a payment.

        Side effects: none. Idempotent: yes. Drivers SHOULD map vendor
        statuses to canonical `PaymentStatus` consistently with their
        webhook handler.

        Raises:
            NotFoundError, AuthenticationError, TransientError.
        """
        ...

    async def refund(
        self,
        payment_id: EntityId,
        amount: Money | None = None,
    ) -> Payment:
        """Refund a settled payment, fully or partially.

        Side effects: YES — moves money. `amount=None` means full refund of
        the remaining unrefunded balance.
        Idempotent: driver-dependent; most rails allow multiple partial
        refunds, so retries may double-refund. Runtime MUST supply a
        request key in the same way as `collect`/`disburse`.

        Raises:
            ConflictError (payment not refundable, window closed),
            ValidationFailedError (amount exceeds remaining),
            CapabilityNotSupportedError, plus standard transport errors.
        """
        ...


__all__ = ["PaymentDriver"]
