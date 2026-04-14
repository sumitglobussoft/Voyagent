"""Runtime-side driver registry.

A thin container that maps *capability protocol names* (``FareSearchDriver``,
``PNRDriver``, ``AccountingDriver``, ``BSPDriver``, ...) to concrete driver
instances. Tool handlers resolve drivers from this registry via
:attr:`ToolContext.extensions`.

Keeping the lookup keyed by protocol name rather than by driver name lets
a tenant swap vendors (Amadeus <-> Sabre <-> TBO, Tally <-> Zoho, etc.)
without changing any tool code.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class DriverRegistry:
    """Map protocol name → driver instance.

    Drivers may implement more than one protocol. Register the same
    instance under every protocol name it satisfies — the registry does
    not introspect manifests, because manifest-based resolution belongs
    higher up (tenant routing) and would add complexity not yet paid for.
    """

    def __init__(self) -> None:
        self._by_protocol: dict[str, Any] = {}
        self._all: list[Any] = []

    def register(self, protocol_name: str, driver: Any) -> None:
        """Register ``driver`` under ``protocol_name``. Overwrites on duplicate."""
        if protocol_name in self._by_protocol:
            logger.info("driver registry: replacing driver for %s", protocol_name)
        self._by_protocol[protocol_name] = driver
        if driver not in self._all:
            self._all.append(driver)

    def get(self, protocol_name: str) -> Any:
        """Return the driver registered under ``protocol_name``.

        Raises :class:`KeyError` if no driver is registered. Tool
        handlers convert this into a user-visible tool-result error.
        """
        try:
            return self._by_protocol[protocol_name]
        except KeyError as exc:
            raise KeyError(
                f"No driver registered for protocol {protocol_name!r}."
            ) from exc

    def drivers(self) -> list[Any]:
        """Return the distinct driver instances (useful for aclose())."""
        return list(self._all)

    async def aclose(self) -> None:
        """Close every registered driver that exposes ``aclose()``."""
        for drv in self._all:
            closer = getattr(drv, "aclose", None)
            if callable(closer):
                try:
                    await closer()
                except Exception:  # noqa: BLE001
                    logger.exception("driver aclose failed: %s", getattr(drv, "name", drv))


def build_default_registry() -> DriverRegistry:
    """Construct the default v0 registry from environment.

    Amadeus is always attempted (the prior behaviour). Tally and BSP
    India are registered opportunistically:

    * :class:`AccountingDriver` -> Tally, iff
      ``VOYAGENT_TALLY_COMPANY_NAME`` is set.
    * :class:`BSPDriver` -> BSP India, iff
      ``VOYAGENT_BSP_INDIA_AGENT_IATA_CODE`` is set.

    Missing env vars are logged at INFO and skipped — a tenant may
    legitimately not use Tally or BSP.
    """
    # Local imports keep the module importable in tests that don't have
    # every driver wheel installed.
    from drivers.amadeus import AmadeusConfig, AmadeusDriver

    registry = DriverRegistry()

    amadeus_config = AmadeusConfig()
    amadeus_driver = AmadeusDriver(amadeus_config)
    registry.register("FareSearchDriver", amadeus_driver)
    registry.register("PNRDriver", amadeus_driver)

    if os.environ.get("VOYAGENT_TALLY_COMPANY_NAME"):
        try:
            from drivers.tally import TallyConfig, TallyDriver

            tally_config = TallyConfig()
            tally_driver = TallyDriver(tally_config)
            registry.register("AccountingDriver", tally_driver)
            logger.info("driver registry: registered Tally as AccountingDriver")
        except Exception:  # noqa: BLE001
            logger.exception("driver registry: Tally registration failed; skipping")
    else:
        logger.info(
            "driver registry: VOYAGENT_TALLY_COMPANY_NAME unset; "
            "skipping AccountingDriver registration"
        )

    if os.environ.get("VOYAGENT_BSP_INDIA_AGENT_IATA_CODE"):
        try:
            from drivers.bsp_india import BSPIndiaConfig, BSPIndiaDriver

            bsp_config = BSPIndiaConfig()
            bsp_driver = BSPIndiaDriver(bsp_config)
            registry.register("BSPDriver", bsp_driver)
            logger.info("driver registry: registered BSP India as BSPDriver")
        except Exception:  # noqa: BLE001
            logger.exception("driver registry: BSP India registration failed; skipping")
    else:
        logger.info(
            "driver registry: VOYAGENT_BSP_INDIA_AGENT_IATA_CODE unset; "
            "skipping BSPDriver registration"
        )

    return registry


__all__ = ["DriverRegistry", "build_default_registry"]
