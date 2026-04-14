"""AccountingDriver — chart of accounts, journal posting, invoicing.

Backends range from full-API SaaS (Zoho Books, Xero, QuickBooks Online) to
offline/desktop systems that only accept XML imports (Tally Prime). The
manifest's `capabilities` map expresses that distinction so the orchestrator
can degrade gracefully (e.g. generate an importable XML when live posting
is unsupported).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from schemas.canonical import (
    EntityId,
    Invoice,
    JournalEntry,
    LedgerAccount,
    Money,
)

from .base import Driver


@runtime_checkable
class AccountingDriver(Driver, Protocol):
    """Read and write into a tenant's accounting system."""

    async def list_accounts(self) -> list[LedgerAccount]:
        """Return the tenant's chart of accounts.

        Side effects: none. Idempotent: yes. Cacheable for the driver's
        configured TTL — charts change rarely.

        Raises:
            AuthenticationError, AuthorizationError, TransientError,
            UpstreamTimeoutError.
        """
        ...

    async def post_journal(self, entry: JournalEntry) -> EntityId:
        """Post a double-entry journal voucher to the books.

        Side effects: YES — creates a posting. Reversing posted entries
        requires a counter-entry; drivers MUST NOT silently edit.
        Idempotent: NO at the wire level. Runtime supplies a client-side
        request key; on UpstreamTimeoutError, the runtime reconciles by
        reading the voucher list before retrying.

        Returns the backend-assigned voucher id (already in EntityId shape).

        Raises:
            ValidationFailedError (backend rejected the entry),
            ConflictError (period closed), AuthorizationError,
            CapabilityNotSupportedError (for backends that accept imports
            only — caller should use the import-file flow), TransientError,
            PermanentError, UpstreamTimeoutError.
        """
        ...

    async def create_invoice(self, invoice: Invoice) -> EntityId:
        """Create a customer invoice in the backend.

        Side effects: YES — creates an invoice and typically consumes a
        number from the tenant's numbering series. Runtime owns series
        allocation and passes the reserved number on the canonical Invoice.
        Idempotent: NO at the wire level (same dedupe pattern as
        `post_journal`).

        Raises:
            ValidationFailedError, ConflictError (duplicate invoice number),
            AuthorizationError, TransientError, PermanentError,
            UpstreamTimeoutError.
        """
        ...

    async def read_invoice(self, invoice_id: EntityId) -> Invoice:
        """Fetch an invoice as the backend currently sees it.

        Side effects: none. Idempotent: yes. Useful after a retry to confirm
        whether a previous create_invoice actually succeeded.

        Raises:
            NotFoundError, AuthenticationError, TransientError.
        """
        ...

    async def read_account_balance(
        self,
        account_id: EntityId,
        as_of: date,
    ) -> Money:
        """Return the balance on an account as of the given date.

        Side effects: none. Idempotent: yes. The `as_of` date is inclusive;
        the returned `Money` uses the account's configured currency, or the
        tenant's base currency for accounts marked multi-currency.

        Raises:
            NotFoundError, AuthorizationError, TransientError.
        """
        ...


__all__ = ["AccountingDriver"]
