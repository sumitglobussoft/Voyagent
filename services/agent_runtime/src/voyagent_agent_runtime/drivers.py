"""Runtime-side driver registry.

A thin container that maps *capability protocol names* (``FareSearchDriver``,
``PNRDriver``, ...) to concrete driver instances. Tool handlers resolve
drivers from this registry via :attr:`ToolContext.extensions`.

Keeping the lookup keyed by protocol name rather than by driver name lets
a tenant swap vendors (Amadeus ↔ Sabre ↔ TBO) without changing any tool
code.
"""

from __future__ import annotations

import logging
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

    Reads Amadeus credentials via :class:`AmadeusConfig` (env prefix
    ``VOYAGENT_AMADEUS_``) and binds the driver under both
    ``FareSearchDriver`` and ``PNRDriver`` protocols. Network I/O does
    not occur here — the driver lazy-initialises its HTTP client.
    """
    # Local import to keep the module importable in tests that don't
    # have the Amadeus driver wheel installed.
    from drivers.amadeus import AmadeusConfig, AmadeusDriver

    config = AmadeusConfig()
    driver = AmadeusDriver(config)
    registry = DriverRegistry()
    registry.register("FareSearchDriver", driver)
    registry.register("PNRDriver", driver)
    return registry


__all__ = ["DriverRegistry", "build_default_registry"]
