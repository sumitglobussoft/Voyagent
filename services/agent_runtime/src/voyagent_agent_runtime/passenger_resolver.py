"""Runtime-side :class:`PassengerResolver` implementations.

In-memory resolver for tests and a storage-backed stub for production.
The runtime bundle wires one of these into every driver that needs it
(today just Amadeus; hotels come next).

The well-known extensions key :data:`PASSENGER_RESOLVER_KEY` is how
tools read the configured resolver off :class:`ToolContext.extensions`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from drivers._contracts.errors import NotFoundError
from schemas.canonical import EntityId, Passenger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


PASSENGER_RESOLVER_KEY: str = "passenger_resolver"
"""Well-known :class:`ToolContext.extensions` key for the resolver."""


# --------------------------------------------------------------------------- #
# In-memory resolver                                                          #
# --------------------------------------------------------------------------- #


class InMemoryPassengerResolver:
    """Dict-backed resolver for tests and local dev loops.

    Takes a pre-populated ``passengers`` mapping at construction. Lookups
    enforce tenant isolation and preserve request ordering.
    """

    _DRIVER = "passenger_resolver.in_memory"

    def __init__(self, passengers: dict[EntityId, Passenger] | None = None) -> None:
        self._passengers: dict[EntityId, Passenger] = dict(passengers or {})

    def put(self, passenger: Passenger) -> None:
        """Insert or overwrite a passenger. Tests use this to seed state."""
        self._passengers[passenger.id] = passenger

    async def resolve(
        self,
        tenant_id: EntityId,
        passenger_ids: list[EntityId],
    ) -> list[Passenger]:
        out: list[Passenger] = []
        for pid in passenger_ids:
            pax = self._passengers.get(pid)
            if pax is None or pax.tenant_id != tenant_id:
                raise NotFoundError(
                    self._DRIVER,
                    f"passenger {pid} not found for tenant {tenant_id}",
                )
            out.append(pax)
        return out


# --------------------------------------------------------------------------- #
# Storage-backed resolver (stub — v1 work)                                    #
# --------------------------------------------------------------------------- #


class StoragePassengerResolver:
    """Postgres-backed resolver.

    TODO(voyagent-storage): the storage package doesn't yet model a
    passenger table — it ships with sessions, approvals, audit, and
    credentials. Once a ``passengers`` + ``passports`` table lands, this
    class gains a real implementation that joins those rows and maps
    back to canonical :class:`Passenger` + :class:`Passport`.

    Construct the class eagerly so the runtime can wire it; any call to
    :meth:`resolve` raises ``NotImplementedError`` until the storage
    surface exists.
    """

    _DRIVER = "passenger_resolver.storage"

    def __init__(self, engine: "AsyncEngine") -> None:
        self._engine = engine

    async def resolve(
        self,
        tenant_id: EntityId,
        passenger_ids: list[EntityId],
    ) -> list[Passenger]:
        raise NotImplementedError(
            "storage-backed resolver requires the passenger table — tracked for v1"
        )


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


def build_passenger_resolver(
    *,
    engine: "AsyncEngine | None" = None,
) -> InMemoryPassengerResolver | StoragePassengerResolver:
    """Return the resolver the runtime should wire into drivers.

    For v0 we always return an empty :class:`InMemoryPassengerResolver`
    — the CLI and API populate it explicitly when a passenger is
    materialised during a turn. Once :class:`StoragePassengerResolver`
    is real this factory will switch when ``engine`` is provided.
    """
    # Deliberately ignore ``engine`` for now — the storage path is a stub.
    _ = engine
    return InMemoryPassengerResolver()


__all__ = [
    "InMemoryPassengerResolver",
    "PASSENGER_RESOLVER_KEY",
    "StoragePassengerResolver",
    "build_passenger_resolver",
]
