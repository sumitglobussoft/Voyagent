"""Shared SQLAlchemy base + column helpers for the Voyagent storage schema.

Storage is a separate concern from the canonical domain model. Canonical
is what agents/tools/drivers speak — storage is how rows, joins, and
indexes work. Keeping them in different packages lets us optimise each
for its own purpose (Pydantic validators there, SQLAlchemy mapped
attributes here).

All mapped classes inherit from :class:`Base`. Tables that care about
tenancy use :func:`tenant_id_fk`; tables that need created/updated
columns use the :class:`Timestamps` mixin. Primary keys are UUIDv7
strings stored as the native Postgres ``uuid`` type — SQLAlchemy's
``UUID(as_uuid=True)`` on Postgres, falling back to ``CHAR(36)`` on
dialects without native UUID support (SQLite in unit tests).
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# --------------------------------------------------------------------------- #
# UUIDv7 helper                                                               #
# --------------------------------------------------------------------------- #


def uuid7() -> uuid.UUID:
    """Mint a UUIDv7 as a :class:`uuid.UUID`.

    Python's stdlib does not ship v7 yet. We pack a 48-bit millisecond
    timestamp into the high bits and fill the rest with randomness, then
    fix the version + variant nibbles per RFC 9562. The result sorts
    monotonically by creation time, which is handy for `(tenant_id,
    created_at DESC)` indexes that want to leverage the PK as a tiebreak.
    """
    ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    high = (ms << 16) | (0x7 << 12) | rand_a
    low = (0b10 << 62) | rand_b
    value = (high << 64) | low
    return uuid.UUID(int=value)


# --------------------------------------------------------------------------- #
# Portable UUID column                                                        #
# --------------------------------------------------------------------------- #


class UUIDType(TypeDecorator):  # type: ignore[type-arg]
    """Portable UUID column type.

    Uses native ``uuid`` on PostgreSQL and a ``CHAR(36)`` string on
    other dialects (SQLite in unit tests). Always binds / loads Python
    :class:`uuid.UUID` instances so application code does not care
    which backend is active.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# --------------------------------------------------------------------------- #
# Declarative base                                                            #
# --------------------------------------------------------------------------- #


class Base(DeclarativeBase):
    """Declarative base for every Voyagent storage model."""


# --------------------------------------------------------------------------- #
# Column helpers                                                              #
# --------------------------------------------------------------------------- #


def uuid_pk() -> Mapped[uuid.UUID]:
    """A UUIDv7 primary-key column with a Python-side default."""
    return mapped_column(
        UUIDType(),
        primary_key=True,
        default=uuid7,
    )


def tenant_id_fk(*, nullable: bool = False) -> Mapped[uuid.UUID]:
    """A ``tenant_id`` foreign key that cascades on tenant deletion."""
    return mapped_column(
        UUIDType(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
    )


class Timestamps:
    """Mixin adding server-side ``created_at`` and ``updated_at`` columns.

    Server-side ``now()`` defaults keep writes honest even when the
    application forgets to set them — e.g., an alembic data migration or
    a stray ``INSERT`` from psql during a debugging session.
    """

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
        nullable=False,
    )


__all__ = [
    "Base",
    "Timestamps",
    "UUIDType",
    "tenant_id_fk",
    "uuid7",
    "uuid_pk",
]
