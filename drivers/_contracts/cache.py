"""Offer-cache contract shared by drivers and the runtime.

Some vendor booking APIs (notably Amadeus Self-Service) require the
full vendor-native offer JSON at ``create`` time, not just the
canonical fare id. We cache those offers in the runtime with a short
TTL and surface them to drivers through this Protocol.

Keeping the Protocol here — in ``drivers/_contracts`` — avoids an
import cycle: the runtime concrete implementation depends on the
driver contract, and drivers depend on the contract, but neither side
imports the other directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OfferCache(Protocol):
    """Tiny key-value cache for vendor offer payloads.

    Implementations may be in-process, Redis-backed, or something else
    entirely. All methods are async so the concrete implementation can
    talk to a network store without blocking.
    """

    async def put(
        self, key: str, offer: dict[str, Any], *, ttl_seconds: int
    ) -> None:
        """Store ``offer`` under ``key`` with an explicit TTL.

        The cache must evict the entry automatically once the TTL
        expires. Callers pick a TTL conservatively — for Amadeus,
        something like ``20 * 60`` seconds is safe (offers expire
        between 15 and 30 minutes).
        """
        ...

    async def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached offer, or ``None`` if missing / expired."""
        ...

    async def delete(self, key: str) -> None:
        """Remove ``key`` from the cache. No-op if absent."""
        ...


__all__ = ["OfferCache"]
