"""DocumentDriver — OCR, parsing, and verification.

Not a storage driver. Canonical `Document` records live in the storage
layer; `DocumentDriver` reads them by `document_id` and returns structured
extractions or verification verdicts.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from schemas.canonical import EntityId, Passport

from .base import Driver


@runtime_checkable
class DocumentDriver(Driver, Protocol):
    """Extract and verify content from uploaded documents."""

    async def ocr(self, document_id: EntityId) -> dict[str, Any]:
        """Run OCR and return raw extracted fields.

        The returned dict is driver-local and meant to be consumed by a
        follow-up canonical parse (like `parse_passport`). It deliberately
        does not try to be canonical — OCR output is lossy and per-provider.

        Side effects: none. Idempotent: yes (same input yields same output
        within a provider model version).

        Raises:
            NotFoundError (document unknown), ValidationFailedError
            (unreadable), TransientError, PermanentError.
        """
        ...

    async def parse_passport(self, document_id: EntityId) -> Passport:
        """Parse a passport scan into the canonical `Passport` model.

        Side effects: none. Idempotent: yes.

        Raises:
            NotFoundError, ValidationFailedError (MRZ unreadable or
            checksum failed), TransientError, PermanentError.
        """
        ...

    async def verify_signature(self, document_id: EntityId) -> bool:
        """Return True if the document bears a detectable signature.

        Coarse v0 contract: presence/absence only. Structured verification
        (signatory identity, signing cert validity) arrives when a
        qualified-eSign driver lands in v1.

        Side effects: none. Idempotent: yes.

        Raises:
            NotFoundError, ValidationFailedError, TransientError.
        """
        ...


__all__ = ["DocumentDriver"]
