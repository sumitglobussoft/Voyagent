"""VisaPortalDriver — visa application portals.

Most implementations are browser automation (VFS Global, BLS International,
embassy portals) rather than published APIs. Drivers run on the
`browser_runner` service; their manifest advertises `requires:
["browser_runner"]`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from schemas.canonical import (
    CountryCode,
    EntityId,
    Passenger,
    Period,
    VisaChecklistItem,
    VisaStatus,
)

from .base import Driver


@runtime_checkable
class VisaPortalDriver(Driver, Protocol):
    """Prepare checklists, fill forms, upload documents, book appointments,
    and read status on a visa portal.

    Implementation note: most portals have no API. Expect Playwright-driven
    browser automation here; failures will skew toward flaky transients and
    layout-change breakages. Use TransientError liberally and classify
    layout breakages as PermanentError until the driver ships a fix.
    """

    async def prepare_checklist(
        self,
        destination: CountryCode,
        category: str,
        passenger: Passenger,
    ) -> list[VisaChecklistItem]:
        """Produce the required-documents checklist for this destination +
        category + passenger combination.

        Side effects: none (reads portal pages or a local rule set).
        Idempotent: yes.

        Raises:
            ValidationFailedError if the category is unknown for the
            destination, TransientError, PermanentError.
        """
        ...

    async def fill_form(
        self,
        visa_file_id: EntityId,
        field_values: dict[str, Any],
    ) -> None:
        """Fill the portal's application form for a visa file.

        Side effects: YES — writes a draft on the portal. Most portals save
        a draft without submitting; submission is typically a separate call
        that will arrive in v1 once the exact finalization gesture per portal
        is nailed down.
        Idempotent: yes — re-submitting the same field values overwrites the
        draft. Driver must detect portal session expiry and re-login.

        Raises:
            ValidationFailedError (field failed portal-side validation),
            AuthenticationError (portal session expired), TransientError,
            PermanentError.
        """
        ...

    async def upload_document(
        self,
        visa_file_id: EntityId,
        document_id: EntityId,
    ) -> None:
        """Upload a supporting document from Voyagent storage to the portal.

        Side effects: YES — attaches the document to the portal draft.
        Idempotent: depends on portal. Drivers SHOULD detect a previously-
        uploaded document by checksum and skip re-upload; where the portal
        allows duplicates, the driver MUST replace rather than append.

        Raises:
            NotFoundError (document_id unknown to storage),
            ValidationFailedError (portal rejected format or size),
            TransientError, PermanentError.
        """
        ...

    async def book_appointment(
        self,
        visa_file_id: EntityId,
        preferred_window: Period,
    ) -> datetime:
        """Book a biometrics / interview appointment within `preferred_window`.

        Side effects: YES — holds an appointment slot. Slot allocation is
        a race; the returned datetime may fall outside the preferred window
        if nothing was available inside it (driver chooses the nearest slot
        after the window start and logs the deviation).
        Idempotent: NO — each call books a new slot. Check
        `VisaFile.appointment_at` before retrying on UpstreamTimeoutError.

        Raises:
            ConflictError (no slots in the window), AuthenticationError,
            TransientError, PermanentError, UpstreamTimeoutError.
        """
        ...

    async def read_status(self, application_ref: str) -> VisaStatus:
        """Read the current processing status from the portal.

        Side effects: none. Idempotent: yes.

        Raises:
            NotFoundError, AuthenticationError, TransientError.
        """
        ...


__all__ = ["VisaPortalDriver"]
