"""Runtime-side :class:`PassengerResolver` implementations.

Two implementations share the driver-layer
:class:`drivers._contracts.passenger_resolver.PassengerResolver` protocol:

* :class:`InMemoryPassengerResolver` — dict-backed, for tests and local
  dev loops where no database is available.
* :class:`StoragePassengerResolver` — Postgres-backed, used whenever the
  runtime is constructed with a SQLAlchemy :class:`AsyncEngine`. It
  reads/writes the ``passengers`` table introduced in alembic revision
  ``0003_passengers`` and enforces tenant isolation on every query.

The well-known extensions key :data:`PASSENGER_RESOLVER_KEY` is how
tools read the configured resolver off :class:`ToolContext.extensions`.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from drivers._contracts.errors import NotFoundError
from schemas.canonical import (
    EntityId,
    Gender,
    Passenger,
    PassengerType,
)
from schemas.storage import PassengerRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


PASSENGER_RESOLVER_KEY: str = "passenger_resolver"
"""Well-known :class:`ToolContext.extensions` key for the resolver."""


# --------------------------------------------------------------------------- #
# In-memory resolver                                                          #
# --------------------------------------------------------------------------- #


class InMemoryPassengerResolver:
    """Dict-backed resolver for tests and local dev loops."""

    _DRIVER = "passenger_resolver.in_memory"

    def __init__(self, passengers: dict[EntityId, Passenger] | None = None) -> None:
        self._passengers: dict[EntityId, Passenger] = dict(passengers or {})

    def put(self, passenger: Passenger) -> None:
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
# Storage-backed resolver                                                     #
# --------------------------------------------------------------------------- #


def _to_uuid(value: EntityId | str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[1]


def _row_to_passenger(row: PassengerRow) -> Passenger:
    # We deliberately do not reconstruct a full canonical ``Passport``
    # here: the canonical model has MRZ-grade required fields
    # (issue_date, gender, issuing_country) that the slim passengers
    # table does not carry. When a caller needs the full document it
    # should load it from a dedicated passports table — tracked for a
    # later revision.
    given, family = _split_name(row.full_name)

    emails = (
        [{"address": row.email}] if row.email else []
    )
    phones = (
        [{"e164": row.phone}] if row.phone and row.phone.startswith("+") else []
    )

    return Passenger.model_validate(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "type": PassengerType.ADULT,
            "given_name": given,
            "family_name": family,
            "date_of_birth": row.date_of_birth,
            "nationality": row.nationality,
            "emails": emails,
            "phones": phones,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


class StoragePassengerResolver:
    """Postgres-backed passenger resolver.

    Every query is ``WHERE tenant_id = :tid`` — a row belonging to
    tenant A is structurally invisible to tenant B because the class
    never issues a statement without the tenant predicate.

    The resolver satisfies the driver-layer ``PassengerResolver`` protocol
    plus a small CRUD surface (:meth:`get_by_id`, :meth:`find_by_email`,
    :meth:`find_by_passport`, :meth:`upsert`) that the API routes drive
    when a human mints or edits a traveler.
    """

    _DRIVER = "passenger_resolver.storage"

    def __init__(self, engine: "AsyncEngine") -> None:
        self._engine = engine
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

    # ------------------------------------------------------------------ #
    # PassengerResolver protocol                                          #
    # ------------------------------------------------------------------ #

    async def resolve(
        self,
        tenant_id: EntityId,
        passenger_ids: list[EntityId],
    ) -> list[Passenger]:
        if not passenger_ids:
            return []
        tid = _to_uuid(tenant_id)
        uuid_ids = [_to_uuid(pid) for pid in passenger_ids]
        async with self._sessionmaker() as db:
            stmt = select(PassengerRow).where(
                PassengerRow.tenant_id == tid,
                PassengerRow.id.in_(uuid_ids),
            )
            rows = {r.id: r for r in (await db.execute(stmt)).scalars()}

        out: list[Passenger] = []
        for pid, uid in zip(passenger_ids, uuid_ids):
            row = rows.get(uid)
            if row is None:
                raise NotFoundError(
                    self._DRIVER,
                    f"passenger {pid} not found for tenant {tenant_id}",
                )
            out.append(_row_to_passenger(row))
        return out

    # ------------------------------------------------------------------ #
    # CRUD surface                                                        #
    # ------------------------------------------------------------------ #

    async def get_by_id(
        self, tenant_id: EntityId, passenger_id: EntityId
    ) -> Passenger | None:
        tid = _to_uuid(tenant_id)
        pid = _to_uuid(passenger_id)
        async with self._sessionmaker() as db:
            stmt = select(PassengerRow).where(
                PassengerRow.tenant_id == tid,
                PassengerRow.id == pid,
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
        return _row_to_passenger(row) if row is not None else None

    async def find_by_email(
        self, tenant_id: EntityId, email: str
    ) -> Passenger | None:
        tid = _to_uuid(tenant_id)
        async with self._sessionmaker() as db:
            stmt = select(PassengerRow).where(
                PassengerRow.tenant_id == tid,
                PassengerRow.email == email,
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
        return _row_to_passenger(row) if row is not None else None

    async def find_by_passport(
        self, tenant_id: EntityId, passport_number: str
    ) -> Passenger | None:
        tid = _to_uuid(tenant_id)
        async with self._sessionmaker() as db:
            stmt = select(PassengerRow).where(
                PassengerRow.tenant_id == tid,
                PassengerRow.passport_number == passport_number,
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
        return _row_to_passenger(row) if row is not None else None

    async def upsert(
        self,
        tenant_id: EntityId,
        *,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
        date_of_birth: "object | None" = None,
        passport_number: str | None = None,
        passport_expiry: "object | None" = None,
        nationality: str | None = None,
        passenger_id: EntityId | None = None,
    ) -> Passenger:
        """Create-or-update a passenger keyed on ``(tenant_id, email)``.

        Uses Postgres ``INSERT ... ON CONFLICT`` so two concurrent
        inserts with the same tenant+email resolve to a single row
        instead of raising a UniqueViolation. On SQLite (unit tests)
        we fall back to a select-then-insert/update portable path.
        """
        tid = _to_uuid(tenant_id)
        new_id = _to_uuid(passenger_id) if passenger_id is not None else uuid.uuid4()

        values = {
            "tenant_id": tid,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "date_of_birth": date_of_birth,
            "passport_number": passport_number,
            "passport_expiry": passport_expiry,
            "nationality": nationality,
        }

        async with self._sessionmaker() as db:
            async with db.begin():
                dialect = db.bind.dialect.name if db.bind else ""
                if dialect == "postgresql" and email is not None:
                    stmt = pg_insert(PassengerRow).values(id=new_id, **values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["tenant_id", "email"],
                        set_={
                            "full_name": stmt.excluded.full_name,
                            "phone": stmt.excluded.phone,
                            "date_of_birth": stmt.excluded.date_of_birth,
                            "passport_number": stmt.excluded.passport_number,
                            "passport_expiry": stmt.excluded.passport_expiry,
                            "nationality": stmt.excluded.nationality,
                        },
                    ).returning(PassengerRow.id)
                    result = await db.execute(stmt)
                    row_id = result.scalar_one()
                else:
                    existing_stmt = select(PassengerRow).where(
                        PassengerRow.tenant_id == tid,
                    )
                    if email is not None:
                        existing_stmt = existing_stmt.where(
                            PassengerRow.email == email
                        )
                    elif passport_number is not None:
                        existing_stmt = existing_stmt.where(
                            PassengerRow.passport_number == passport_number
                        )
                    else:
                        existing_stmt = existing_stmt.where(
                            PassengerRow.id == new_id
                        )
                    existing = (
                        await db.execute(existing_stmt)
                    ).scalar_one_or_none()
                    if existing is None:
                        row = PassengerRow(id=new_id, **values)
                        db.add(row)
                        row_id = new_id
                    else:
                        existing.full_name = full_name
                        existing.phone = phone
                        existing.date_of_birth = date_of_birth  # type: ignore[assignment]
                        existing.passport_number = passport_number
                        existing.passport_expiry = passport_expiry  # type: ignore[assignment]
                        existing.nationality = nationality
                        row_id = existing.id

            stmt = select(PassengerRow).where(
                PassengerRow.tenant_id == tid,
                PassengerRow.id == row_id,
            )
            row = (await db.execute(stmt)).scalar_one()
        return _row_to_passenger(row)


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


def build_passenger_resolver(
    *,
    engine: "AsyncEngine | None" = None,
) -> "InMemoryPassengerResolver | StoragePassengerResolver":
    """Return the resolver the runtime should wire into drivers.

    When an :class:`AsyncEngine` is provided (``VOYAGENT_DB_URL`` set)
    the runtime gets the Postgres-backed :class:`StoragePassengerResolver`.
    Otherwise it falls back to :class:`InMemoryPassengerResolver` — the
    dev-only path that tests use when no database is configured.
    """
    if engine is not None:
        return StoragePassengerResolver(engine)
    return InMemoryPassengerResolver()


# ``Gender`` re-export anchor: kept imported so downstream test modules
# that already patched ``voyagent_agent_runtime.passenger_resolver.Gender``
# still find the symbol. No runtime effect.
_ = Gender


__all__ = [
    "InMemoryPassengerResolver",
    "PASSENGER_RESOLVER_KEY",
    "StoragePassengerResolver",
    "build_passenger_resolver",
]
