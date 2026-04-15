"""Round-trip + index tests for :mod:`schemas.storage.session_cost`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import SessionCostRow, Tenant, uuid7

pytestmark = pytest.mark.asyncio


async def test_session_cost_round_trip(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tid = uuid7()
    sid = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tid, display_name="T", default_currency="INR"))
            db.add(
                SessionCostRow(
                    tenant_id=tid,
                    session_id=sid,
                    turn_id="t-abc",
                    model="claude-sonnet-4-5",
                    input_tokens=1000,
                    output_tokens=2000,
                    total_tokens=3000,
                    cost_usd=Decimal("0.03300000"),
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(SessionCostRow).where(SessionCostRow.session_id == sid)
            )
        ).scalar_one()
        assert row.tenant_id == tid
        assert row.turn_id == "t-abc"
        assert row.model == "claude-sonnet-4-5"
        assert row.input_tokens == 1000
        assert row.output_tokens == 2000
        assert row.total_tokens == 3000
        assert row.cost_usd == Decimal("0.03300000")
        assert row.created_at is not None


async def test_session_cost_sum_per_session(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tid = uuid7()
    sid = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tid, display_name="T", default_currency="INR"))
            for i in range(3):
                db.add(
                    SessionCostRow(
                        tenant_id=tid,
                        session_id=sid,
                        turn_id=f"t-{i}",
                        model="claude-sonnet-4-5",
                        input_tokens=100,
                        output_tokens=100,
                        total_tokens=200,
                        cost_usd=Decimal("0.01"),
                    )
                )

    async with Session() as db:
        total = (
            await db.execute(
                select(func.sum(SessionCostRow.cost_usd)).where(
                    SessionCostRow.session_id == sid
                )
            )
        ).scalar_one()
        assert Decimal(str(total)) == Decimal("0.03")


async def test_session_cost_tenant_isolation(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    a = uuid7()
    b = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=a, display_name="A", default_currency="INR"))
            db.add(Tenant(id=b, display_name="B", default_currency="INR"))
            db.add(
                SessionCostRow(
                    tenant_id=a,
                    session_id=uuid7(),
                    turn_id="t-a",
                    model="claude-sonnet-4-5",
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    cost_usd=Decimal("0.001"),
                )
            )
            db.add(
                SessionCostRow(
                    tenant_id=b,
                    session_id=uuid7(),
                    turn_id="t-b",
                    model="claude-sonnet-4-5",
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    cost_usd=Decimal("0.002"),
                )
            )

    async with Session() as db:
        rows_a = (
            (
                await db.execute(
                    select(SessionCostRow).where(SessionCostRow.tenant_id == a)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows_a) == 1
        assert rows_a[0].turn_id == "t-a"


async def test_session_cost_index_exists(engine: AsyncEngine) -> None:
    def _inspect(sync_conn):  # type: ignore[no-untyped-def]
        inspector = sa_inspect(sync_conn)
        return inspector.get_indexes("session_costs")

    async with engine.begin() as conn:
        indexes = await conn.run_sync(_inspect)

    names = {ix["name"] for ix in indexes}
    assert "ix_session_costs_tenant_created" in names
    assert "ix_session_costs_session_id" in names


async def test_session_cost_defaults(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tid = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tid, display_name="T", default_currency="INR"))
            db.add(
                SessionCostRow(
                    tenant_id=tid,
                    session_id=uuid7(),
                    turn_id="t-x",
                    model="claude-haiku-4-5-20251001",
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(SessionCostRow).where(
                    SessionCostRow.turn_id == "t-x"
                )
            )
        ).scalar_one()
        assert row.input_tokens == 0
        assert row.output_tokens == 0
        assert row.total_tokens == 0
        assert row.cost_usd == Decimal("0")
