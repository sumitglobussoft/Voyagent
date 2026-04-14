"""MessagingDriver — outbound email, WhatsApp, and SMS."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.canonical import E164Phone, EmailStr, EntityId, LocalizedText

from .base import Driver


@runtime_checkable
class MessagingDriver(Driver, Protocol):
    """Send messages over one or more channels.

    A driver may implement a subset — a tenant that uses SendGrid for email
    and Twilio for WhatsApp will register two separate drivers, each
    declaring the channels they support via their manifest.
    """

    async def send_email(
        self,
        to: EmailStr,
        subject: str,
        body: LocalizedText,
        attachments: list[EntityId],
    ) -> str:
        """Send an email. Attachments are resolved by `DocumentDriver`/storage
        at send time.

        Side effects: YES — a message leaves the agency.
        Idempotent: NO. Runtime MUST supply an idempotency key via message
        metadata (channel-specific; declared in the manifest).

        Returns the provider-assigned message id.

        Raises:
            CapabilityNotSupportedError (channel not implemented by driver),
            ValidationFailedError (bad address), RateLimitError,
            TransientError, PermanentError, UpstreamTimeoutError.
        """
        ...

    async def send_whatsapp(
        self,
        to_e164: E164Phone,
        body: LocalizedText,
        attachments: list[EntityId],
    ) -> str:
        """Send a WhatsApp message.

        Side effects: YES.
        Idempotent: NO (same pattern as `send_email`). Template vs free-form
        message selection is driver-specific; drivers MUST document which
        WhatsApp Business constructs they use.

        Returns the provider-assigned message id.

        Raises:
            CapabilityNotSupportedError, ValidationFailedError,
            RateLimitError, TransientError, PermanentError,
            UpstreamTimeoutError.
        """
        ...

    async def send_sms(
        self,
        to_e164: E164Phone,
        body: LocalizedText,
    ) -> str:
        """Send an SMS.

        Side effects: YES. Idempotent: NO (same pattern as above).

        Returns the provider-assigned message id.

        Raises:
            CapabilityNotSupportedError, ValidationFailedError,
            RateLimitError, TransientError, PermanentError.
        """
        ...


__all__ = ["MessagingDriver"]
