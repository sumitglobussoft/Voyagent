"""The BSP India driver — satisfies :class:`BSPDriver` (partial).

Country-scoped by design. BSPs differ per country in file format,
submission cycle, and ADM/ACM workflows, so the driver explicitly
rejects any ``country`` argument other than ``"IN"``. A future
``drivers.bsp_uae`` / ``drivers.bsp_uk`` driver will mirror this
package's shape and live independently.

v0 supports:

  * ``fetch_statement``           — ``full`` when a local HAF drop is
                                     configured; HTTP path is scaffolded
                                     only.
  * ``raise_adm``                 — ``not_supported``.
  * ``raise_acm``                 — ``not_supported``.
  * ``make_settlement_payment``   — ``not_supported``. BSP settlement
                                     payments are rail-specific and
                                     belong behind a :class:`BankDriver`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from drivers._contracts.errors import (
    CapabilityNotSupportedError,
    ValidationFailedError,
)
from drivers._contracts.manifest import CapabilityManifest
from schemas.canonical import (
    BSPReport,
    CountryCode,
    EntityId,
    LocalizedText,
    Payment,
    Period,
)

from .client import BSPIndiaClient
from .config import BSPIndiaConfig
from .errors import DRIVER_NAME
from .haf_parser import parse_haf
from .mapping import _new_entity_id, haf_file_to_bsp_report

logger = logging.getLogger(__name__)


_SUPPORTED_COUNTRY: CountryCode = "IN"


class BSPIndiaDriver:
    """Reference driver implementing :class:`BSPDriver` for BSP India.

    Construct once per tenant with a :class:`BSPIndiaConfig`. Methods
    are ``async`` and safe for concurrent use. Tenant config (IATA
    agency code, BSPlink credentials) is consumed eagerly on
    construction but I/O is deferred until the first call.
    """

    name: ClassVar[str] = "bsp_india"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        config: BSPIndiaConfig,
        *,
        client: BSPIndiaClient | None = None,
        tenant_id: EntityId | None = None,
    ) -> None:
        self._config = config
        self._client = client or BSPIndiaClient(config)
        self._tenant_id: EntityId = tenant_id or _new_entity_id()

    async def aclose(self) -> None:
        """Release the underlying httpx client."""
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Driver protocol                                                    #
    # ------------------------------------------------------------------ #

    def manifest(self) -> CapabilityManifest:
        """Return the static capability manifest for this driver."""
        if self._config.file_source_dir:
            fetch_level = "full"
            transport = ["file_local"]
        else:
            # The HTTP path is a scaffold — advertise it as ``not_supported``
            # so the orchestrator does not attempt it and tenants know to
            # configure the file drop.
            fetch_level = "not_supported"
            transport = ["http"]

        return CapabilityManifest(
            driver=self.name,
            version=self.version,
            implements=["BSPDriver"],
            capabilities={
                "fetch_statement": fetch_level,
                "raise_adm": "not_supported",
                "raise_acm": "not_supported",
                "make_settlement_payment": "not_supported",
            },
            transport=transport,
            requires=["tenant_credentials"],
            tenant_config_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["agent_iata_code"],
                "properties": {
                    "bsplink_base_url": {"type": "string", "format": "uri"},
                    "agent_iata_code": {"type": "string", "minLength": 1},
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                    "file_source_dir": {"type": ["string", "null"]},
                    "timeout_seconds": {"type": "integer", "exclusiveMinimum": 0},
                    "max_retries": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        )

    # ------------------------------------------------------------------ #
    # BSPDriver                                                          #
    # ------------------------------------------------------------------ #

    async def fetch_statement(
        self,
        country: CountryCode,
        period: Period,
    ) -> BSPReport:
        """Fetch and parse the BSP India HAF statement for ``period``.

        The country argument is validated before any I/O so a
        misconfigured tenant does not leak credentials in a wrong-country
        call. Only ``"IN"`` is accepted.
        """
        self._require_country(country)

        start = period.start.astimezone(timezone.utc).date()
        # Canonical Period is half-open; HAF period_end is inclusive, so
        # subtract a day when the caller provides an explicit end.
        if period.end is None:
            end = start
        else:
            end_exclusive = period.end.astimezone(timezone.utc).date()
            from datetime import timedelta

            end = end_exclusive - timedelta(days=1) if end_exclusive > start else start

        file_bytes = await self._client.fetch_statement(start, end)
        source_ref = (
            f"HAF_{self._config.agent_iata_code}_"
            f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
        )
        haf = parse_haf(file_bytes, source_ref=source_ref)
        report = haf_file_to_bsp_report(haf, tenant_id=self._tenant_id)
        return report

    async def raise_adm(self, reference: str, reason: LocalizedText) -> str:
        """Not supported in v0."""
        del reference, reason
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "BSP India ADM submission is not supported in v0; use BSPlink directly.",
        )

    async def raise_acm(self, reference: str, reason: LocalizedText) -> str:
        """Not supported in v0."""
        del reference, reason
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "BSP India ACM submission is not supported in v0; use BSPlink directly.",
        )

    async def make_settlement_payment(self, report_id: EntityId) -> Payment:
        """Not supported — settlement payments route through a BankDriver."""
        del report_id
        raise CapabilityNotSupportedError(
            DRIVER_NAME,
            "BSP India settlement payments are not handled by the BSP driver — "
            "they use the tenant's bank/payment rail. Route via a BankDriver.",
        )

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _require_country(country: CountryCode) -> None:
        if country != _SUPPORTED_COUNTRY:
            raise ValidationFailedError(
                DRIVER_NAME,
                f"bsp_india only services {_SUPPORTED_COUNTRY}; country={country} not supported.",
            )

    # ------------------------------------------------------------------ #
    # Context manager                                                    #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> BSPIndiaDriver:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()


# Silence a lint complaint about datetime not being used at runtime in
# some type-checker configurations.
_ = datetime


__all__ = ["BSPIndiaDriver"]
