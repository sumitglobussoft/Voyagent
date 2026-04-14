"""Passenger resolution — driver-layer contract.

PNR creation requires authoritative traveler data (legal name, DOB,
document numbers). Drivers that book flights never build synthetic
travelers; they look them up through a :class:`PassengerResolver`
supplied by the runtime.

The resolver lives at the driver boundary — not in canonical — because
"how do I load a passenger?" is an infrastructure concern. The resolver
returns canonical :class:`Passenger` records so drivers stay free of
storage details.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.canonical import EntityId, Passenger


@runtime_checkable
class PassengerResolver(Protocol):
    """Resolve canonical :class:`Passenger` records by id, within a tenant.

    Implementations must:

    * Return passengers in the same order as ``passenger_ids``. Callers
      rely on positional alignment (e.g. the Amadeus driver maps each
      passenger to a 1-indexed traveler id matching its position in the
      request).
    * Raise :class:`drivers._contracts.errors.NotFoundError` when any
      id is unknown for the tenant. Partial lookups are never returned
      — the caller can't safely continue booking with a missing traveler.
    * Never leak passengers from a different tenant. Tenant isolation
      is the resolver's job.

    Idempotent: yes. Safe for concurrent calls.
    """

    async def resolve(
        self,
        tenant_id: EntityId,
        passenger_ids: list[EntityId],
    ) -> list[Passenger]:
        ...


__all__ = ["PassengerResolver"]
