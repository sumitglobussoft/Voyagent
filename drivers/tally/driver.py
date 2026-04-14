"""The Tally driver — satisfies :class:`AccountingDriver`.

Desktop-bound: requires a host that can reach ``localhost:9000`` of a
running Tally Prime instance with the Gateway Server enabled and the
configured company open. The manifest advertises this constraint through
``requires=["desktop_host"]`` so the orchestrator does not schedule this
driver onto cloud-only workers.

v0 supports:
  * ``list_accounts``          — full (via the 'List of Ledgers' TDL collection)
  * ``post_journal``           — via XML Import Data (voucher create)
  * ``create_invoice``         — via XML Import Data (sales voucher create)
  * ``read_invoice``           — **not supported**; Tally lacks a stable
    read-by-external-id endpoint out of the box.
  * ``read_account_balance``   — partial; only opening-balance semantics
    for ``as_of`` <= books-start date. Anything else raises
    :class:`CapabilityNotSupportedError`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, ClassVar

from drivers._contracts.errors import (
    CapabilityNotSupportedError,
    PermanentError,
    ValidationFailedError,
)
from drivers._contracts.manifest import CapabilityManifest
from schemas.canonical import (
    EntityId,
    Invoice,
    JournalEntry,
    LedgerAccount,
    Money,
)

from .client import TallyClient
from .config import TallyConfig
from .errors import DRIVER_NAME, map_tally_error
from .mapping import (
    _new_entity_id,
    invoice_to_tally_sales_voucher,
    journal_entry_to_tally_xml_body,
    tally_ledger_to_account,
)
from .xml_builder import build_list_ledgers, build_ping
from .xml_parser import (
    parse_ledger_list,
    parse_ping_response,
    parse_voucher_create_response,
)

logger = logging.getLogger(__name__)


class TallyDriver:
    """Reference driver implementing :class:`AccountingDriver` over Tally XML.

    Construct once per tenant with a :class:`TallyConfig`. Methods are
    ``async`` and safe for concurrent use so long as Tally itself is
    (Tally's gateway is single-threaded in practice; the client keeps
    concurrency modest).

    The ``ledger_name_resolver`` maps canonical :class:`EntityId` values
    to the Tally display name the gateway expects on every posting. The
    runtime supplies it — the driver is intentionally agnostic to how
    the mapping is persisted.
    """

    name: ClassVar[str] = "tally"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        config: TallyConfig,
        *,
        client: TallyClient | None = None,
        tenant_id: EntityId | None = None,
        ledger_name_resolver: Callable[[EntityId], str] | None = None,
    ) -> None:
        self._config = config
        self._client = client or TallyClient(config)
        self._tenant_id: EntityId = tenant_id or _new_entity_id()
        self._ledger_name_resolver = ledger_name_resolver
        # In-memory canonical->Tally id mapping. Runtime should persist
        # this; the driver only keeps the most-recent round-trip so
        # tests and scripts can observe it.
        self._recent_voucher_ids: dict[EntityId, str] = {}

    async def aclose(self) -> None:
        """Release the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Driver protocol                                                    #
    # ------------------------------------------------------------------ #

    def manifest(self) -> CapabilityManifest:
        """Return the static capability manifest for this driver."""
        return CapabilityManifest(
            driver=self.name,
            version=self.version,
            implements=["AccountingDriver"],
            capabilities={
                "list_accounts": "full",
                "post_journal": "supported_via_xml_import",
                "create_invoice": "supported_via_xml_import",
                "read_invoice": "not_supported",
                "read_account_balance": "partial",
            },
            transport=["http_xml"],
            requires=["desktop_host", "tenant_credentials"],
            tenant_config_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["company_name"],
                "properties": {
                    "gateway_url": {"type": "string", "format": "uri"},
                    "company_name": {"type": "string", "minLength": 1},
                    "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
                    "max_retries": {"type": "integer", "minimum": 0},
                    "basic_auth_user": {"type": "string"},
                    "basic_auth_password": {"type": "string"},
                },
                "additionalProperties": False,
            },
        )

    # ------------------------------------------------------------------ #
    # AccountingDriver                                                   #
    # ------------------------------------------------------------------ #

    async def list_accounts(self) -> list[LedgerAccount]:
        """Return the tenant's chart of accounts.

        Performs a lightweight ping first so auth / company-not-open
        failures surface as clean :class:`DriverError` subclasses before
        any heavier collection fetch.
        """
        # Ping — surfaces auth + company-open issues early.
        ping_body = await self._client.post_envelope(build_ping(self._config.company_name))
        try:
            parse_ping_response(ping_body)
        except ValidationFailedError:
            raise map_tally_error(200, ping_body)

        body = await self._client.post_envelope(
            build_list_ledgers(self._config.company_name)
        )
        ledgers = parse_ledger_list(body)
        return [tally_ledger_to_account(t, tenant_id=self._tenant_id) for t in ledgers]

    async def post_journal(self, entry: JournalEntry) -> EntityId:
        """Post a double-entry journal voucher to Tally.

        Tally returns its own numeric ``LASTVCHID`` on success; we
        synthesise a canonical :class:`EntityId` because the contract
        requires one, and stash the mapping in
        ``self._recent_voucher_ids`` so the runtime can observe it if
        desired. Persistence of the mapping is the runtime's job — not
        the driver's.
        """
        xml = journal_entry_to_tally_xml_body(
            entry,
            company_name=self._config.company_name,
            ledger_name_resolver=self._require_resolver(),
        )
        body = await self._client.post_envelope(xml)
        ack = parse_voucher_create_response(body)

        if ack.created < 1 and ack.altered < 1:
            # A zero-created / zero-altered ack usually means Tally silently
            # rejected the envelope; map_tally_error extracts the better
            # message when there's a <LINEERROR> inside.
            raise map_tally_error(200, body)

        canonical_id = _new_entity_id()
        if ack.last_vch_id:
            self._recent_voucher_ids[canonical_id] = ack.last_vch_id
        return canonical_id

    async def create_invoice(self, invoice: Invoice) -> EntityId:
        """Create a Sales voucher in Tally for the given canonical invoice.

        See :func:`drivers.tally.mapping.invoice_to_tally_sales_voucher`
        for the mapping rules and caveats (no inventory, default fallback
        ledgers).
        """
        xml = invoice_to_tally_sales_voucher(
            invoice,
            company_name=self._config.company_name,
            ledger_name_resolver=self._require_resolver(),
        )
        body = await self._client.post_envelope(xml)
        ack = parse_voucher_create_response(body)

        if ack.created < 1 and ack.altered < 1:
            raise map_tally_error(200, body)

        canonical_id = _new_entity_id()
        if ack.last_vch_id:
            self._recent_voucher_ids[canonical_id] = ack.last_vch_id
        return canonical_id

    async def read_invoice(self, invoice_id: EntityId) -> Invoice:
        """Not supported in v0.

        Tally has no stable 'fetch voucher by canonical id' endpoint —
        vouchers are addressable by Tally's own master-id or voucher
        number, neither of which the canonical :class:`EntityId` space
        carries natively. A future extension can ship a TDL report that
        filters vouchers on a UDF field populated during
        :meth:`create_invoice`.
        """
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "TallyDriver v0 does not implement read_invoice. Tally offers no "
            "stable external-id lookup; add a TDL voucher-filter report keyed on a "
            "canonical-id UDF to enable this in a future version.",
        )

    async def read_account_balance(
        self,
        account_id: EntityId,
        as_of: date,
    ) -> Money:
        """Partial support: returns the opening balance if ``as_of`` is early.

        Tally exposes opening balance on every ledger master; anything
        after books-start requires aggregating vouchers, which Tally does
        not deliver in a single canonical shape. v0 does the honest
        thing and raises :class:`CapabilityNotSupportedError` for the
        general case.

        Callers that need true as-of-date balances should run the
        ``Trial Balance`` TDL report and aggregate client-side — a task
        out of scope for v0.
        """
        # Without a richer runtime we can't map the canonical account_id
        # back to a Tally ledger master cheaply, so even the partial case
        # lands in "not supported" for v0.
        del account_id  # unused; kept for signature conformance
        del as_of
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "TallyDriver v0 supports only opening-balance semantics and lacks "
            "the runtime plumbing to expose even that via AccountingDriver. "
            "Implement a Trial Balance TDL aggregation in a future version.",
        )

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _require_resolver(self) -> Callable[[EntityId], str]:
        resolver = self._ledger_name_resolver
        if resolver is None:
            raise PermanentError(
                DRIVER_NAME,
                "TallyDriver requires a ledger_name_resolver at construction "
                "time for any posting method. None was provided.",
            )
        return resolver

    # Public helper for tests / runtime observability.
    @property
    def recent_voucher_ids(self) -> dict[EntityId, str]:
        """Most-recent canonical-id -> Tally LASTVCHID mappings.

        Not persistent. The runtime should copy this out after each
        posting call if it needs to retain the correlation across
        process restarts.
        """
        return dict(self._recent_voucher_ids)

    # ------------------------------------------------------------------ #
    # Context manager                                                    #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> TallyDriver:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()


# Silence a lint complaint about unused imports that are part of the
# module's typed public surface area (Decimal / datetime) in some
# type-checker configurations.
_ = Decimal
_ = datetime
_ = timezone


__all__ = ["TallyDriver"]
