"""Tests for the Postgres-backed StoragePassengerResolver using aiosqlite.

Follows the pattern in ``test_stores_pg.py``: an in-memory aiosqlite
engine with ``Base.metadata.create_all``, no SQLAlchemy mocking. Real
rows, real queries, real tenant isolation.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from drivers._contracts.errors import NotFoundError
from schemas.storage import Base, Tenant, uuid7

from voyagent_agent_runtime.passenger_resolver import (
    InMemoryPassengerResolver,
    StoragePassengerResolver,
    build_passenger_resolver,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed_tenant(engine: AsyncEngine, tenant_uuid: uuid.UUID) -> None:
    Sess = async_sessionmaker(engine, expire_on_commit=False)
    async with Sess() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_uuid,
                    display_name="T",
                    default_currency="USD",
                )
            )


def _eid(value: uuid.UUID) -> str:
    return str(value)


async def test_build_factory_returns_storage_when_engine(
    engine: AsyncEngine,
) -> None:
    resolver = build_passenger_resolver(engine=engine)
    assert isinstance(resolver, StoragePassengerResolver)


async def test_build_factory_falls_back_to_memory_without_engine() -> None:
    resolver = build_passenger_resolver(engine=None)
    assert isinstance(resolver, InMemoryPassengerResolver)


async def test_upsert_creates_then_updates(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    await _seed_tenant(engine, tenant_uuid)
    resolver = StoragePassengerResolver(engine)

    created = await resolver.upsert(
        _eid(tenant_uuid),
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone="+14155550100",
        date_of_birth=date(1815, 12, 10),
        nationality="GB",
    )
    assert created.tenant_id == _eid(tenant_uuid)
    assert created.given_name == "Ada"
    assert created.family_name == "Lovelace"

    updated = await resolver.upsert(
        _eid(tenant_uuid),
        full_name="Ada King",
        email="ada@example.com",
        nationality="GB",
    )
    # Same tenant+email must resolve to the same row (no duplicate).
    assert updated.id == created.id
    assert updated.family_name == "King"

    # Idempotency: third call with same email does not raise.
    again = await resolver.upsert(
        _eid(tenant_uuid),
        full_name="Ada King",
        email="ada@example.com",
    )
    assert again.id == created.id


async def test_find_by_email_and_passport(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    await _seed_tenant(engine, tenant_uuid)
    resolver = StoragePassengerResolver(engine)

    created = await resolver.upsert(
        _eid(tenant_uuid),
        full_name="Grace Hopper",
        email="grace@example.com",
        passport_number="X1234567",
        passport_expiry=date(2030, 1, 1),
        nationality="US",
    )

    by_email = await resolver.find_by_email(_eid(tenant_uuid), "grace@example.com")
    assert by_email is not None
    assert by_email.id == created.id

    by_passport = await resolver.find_by_passport(_eid(tenant_uuid), "X1234567")
    assert by_passport is not None
    assert by_passport.id == created.id

    missing = await resolver.find_by_email(_eid(tenant_uuid), "nope@example.com")
    assert missing is None


async def test_get_by_id_round_trip(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    await _seed_tenant(engine, tenant_uuid)
    resolver = StoragePassengerResolver(engine)
    created = await resolver.upsert(
        _eid(tenant_uuid),
        full_name="Alan Turing",
        email="alan@example.com",
    )
    fetched = await resolver.get_by_id(_eid(tenant_uuid), created.id)
    assert fetched is not None
    assert fetched.given_name == "Alan"


async def test_resolve_preserves_order_and_raises_on_missing(
    engine: AsyncEngine,
) -> None:
    tenant_uuid = uuid7()
    await _seed_tenant(engine, tenant_uuid)
    resolver = StoragePassengerResolver(engine)

    a = await resolver.upsert(
        _eid(tenant_uuid), full_name="A X", email="a@example.com"
    )
    b = await resolver.upsert(
        _eid(tenant_uuid), full_name="B Y", email="b@example.com"
    )

    out = await resolver.resolve(_eid(tenant_uuid), [b.id, a.id])
    assert [p.id for p in out] == [b.id, a.id]

    with pytest.raises(NotFoundError):
        await resolver.resolve(_eid(tenant_uuid), [a.id, _eid(uuid7())])


async def test_tenant_isolation(engine: AsyncEngine) -> None:
    tenant_a = uuid7()
    tenant_b = uuid7()
    await _seed_tenant(engine, tenant_a)
    await _seed_tenant(engine, tenant_b)
    resolver = StoragePassengerResolver(engine)

    pax_a = await resolver.upsert(
        _eid(tenant_a),
        full_name="Shared Name",
        email="shared@example.com",
        passport_number="P000001",
    )

    # Same email + passport are allowed under a different tenant —
    # unique indexes are (tenant_id, email) / (tenant_id, passport).
    pax_b = await resolver.upsert(
        _eid(tenant_b),
        full_name="Shared Name",
        email="shared@example.com",
        passport_number="P000001",
    )
    assert pax_a.id != pax_b.id

    # Tenant B's lookups must not see Tenant A's row.
    from_b_by_email = await resolver.find_by_email(
        _eid(tenant_b), "shared@example.com"
    )
    assert from_b_by_email is not None
    assert from_b_by_email.id == pax_b.id

    # Resolving tenant A's id from tenant B must fail.
    with pytest.raises(NotFoundError):
        await resolver.resolve(_eid(tenant_b), [pax_a.id])

    # get_by_id scoped to wrong tenant returns None.
    assert await resolver.get_by_id(_eid(tenant_b), pax_a.id) is None
