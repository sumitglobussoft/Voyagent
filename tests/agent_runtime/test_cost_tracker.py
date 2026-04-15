"""Tests for :mod:`voyagent_agent_runtime.cost_tracker`."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from voyagent_agent_runtime.cost_tracker import (
    DailyBudgetExceededError,
    InMemoryCostTracker,
    MODEL_PRICING,
    build_turn_cost,
    enforce_daily_budget,
    estimate_cost_usd,
)

pytestmark = pytest.mark.asyncio


def test_pricing_table_includes_all_required_models() -> None:
    # Smoke test — the hardcoded dict must cover every model the
    # tenant-settings API accepts.
    required = {
        "claude-sonnet-4-5",
        "claude-opus-4-6",
        "claude-haiku-4-5-20251001",
    }
    assert required <= set(MODEL_PRICING.keys())


def test_estimate_cost_sonnet_matches_expected() -> None:
    # 1M input + 1M output at $3 / $15 per million = $18.
    cost = estimate_cost_usd("claude-sonnet-4-5", 1_000_000, 1_000_000)
    assert cost == Decimal("18.00000000")


def test_estimate_cost_haiku_small_turn() -> None:
    # 1000 input + 500 output at $0.80 / $4 per million.
    #   input  = 1000 * 0.80 / 1_000_000 = 0.0008
    #   output =  500 * 4     / 1_000_000 = 0.002
    # total = 0.0028
    cost = estimate_cost_usd("claude-haiku-4-5-20251001", 1000, 500)
    assert cost == Decimal("0.00280000")


def test_estimate_cost_unknown_model_returns_zero(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        cost = estimate_cost_usd("totally-made-up", 100, 100)
    assert cost == Decimal("0")
    assert any("unknown model" in r.message for r in caplog.records)


async def test_record_and_total_for_session_round_trip() -> None:
    tracker = InMemoryCostTracker()
    now = datetime.now(timezone.utc)
    cost = build_turn_cost(
        tenant_id="tenant-a",
        session_id="sess-1",
        turn_id="t-1",
        model="claude-sonnet-4-5",
        input_tokens=1000,
        output_tokens=2000,
        created_at=now,
    )
    await tracker.record(cost)
    total = await tracker.total_for_session("sess-1")
    assert total == cost.cost_usd
    # Other session stays empty.
    assert await tracker.total_for_session("sess-2") == Decimal("0")


async def test_total_for_tenant_today_respects_date_boundary() -> None:
    tracker = InMemoryCostTracker()
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=2)
    await tracker.record(
        build_turn_cost(
            tenant_id="tenant-a",
            session_id="sess-1",
            turn_id="t-1",
            model="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=1000,
            created_at=yesterday,
        )
    )
    await tracker.record(
        build_turn_cost(
            tenant_id="tenant-a",
            session_id="sess-1",
            turn_id="t-2",
            model="claude-sonnet-4-5",
            input_tokens=500,
            output_tokens=500,
            created_at=today,
        )
    )
    today_total = await tracker.total_for_tenant_today("tenant-a")
    # Only today's row should count.
    assert today_total == estimate_cost_usd("claude-sonnet-4-5", 500, 500)


async def test_tokens_for_tenant_today_sums_only_today() -> None:
    tracker = InMemoryCostTracker()
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=3)
    await tracker.record(
        build_turn_cost(
            tenant_id="tenant-a",
            session_id="sess-1",
            turn_id="t-1",
            model="claude-haiku-4-5-20251001",
            input_tokens=9999,
            output_tokens=9999,
            created_at=yesterday,
        )
    )
    await tracker.record(
        build_turn_cost(
            tenant_id="tenant-a",
            session_id="sess-1",
            turn_id="t-2",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=200,
            created_at=today,
        )
    )
    assert await tracker.tokens_for_tenant_today("tenant-a") == 300


async def test_enforce_daily_budget_under_limit_is_noop() -> None:
    tracker = InMemoryCostTracker()
    await tracker.record(
        build_turn_cost(
            tenant_id="tenant-a",
            session_id="sess-1",
            turn_id="t-1",
            model="claude-sonnet-4-5",
            input_tokens=100,
            output_tokens=100,
        )
    )
    # 200 tokens used, budget 1000 — should pass.
    await enforce_daily_budget(tracker, "tenant-a", 1000)


async def test_enforce_daily_budget_exceeds_raises() -> None:
    tracker = InMemoryCostTracker()
    await tracker.record(
        build_turn_cost(
            tenant_id="tenant-a",
            session_id="sess-1",
            turn_id="t-1",
            model="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=1000,
        )
    )
    with pytest.raises(DailyBudgetExceededError) as exc_info:
        await enforce_daily_budget(tracker, "tenant-a", 500)
    assert exc_info.value.tenant_id == "tenant-a"
    assert exc_info.value.limit == 500
    assert exc_info.value.used == 2000


async def test_enforce_daily_budget_none_is_noop() -> None:
    tracker = InMemoryCostTracker()
    await enforce_daily_budget(tracker, "tenant-a", None)


async def test_storage_cost_tracker_round_trip(engine) -> None:
    # Functional test against the aiosqlite fixture from storage/conftest
    # — but tests/agent_runtime doesn't import that conftest by default,
    # so we build a local engine here.
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from schemas.storage import Base, Tenant
    from voyagent_agent_runtime.cost_tracker import StorageCostTracker

    local_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with local_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Insert a tenant so the FK is satisfied.
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker

    tenant_uuid = _uuid.uuid4()
    session_uuid = _uuid.uuid4()
    sm = async_sessionmaker(local_engine, expire_on_commit=False)
    async with sm() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_uuid,
                    display_name="Test",
                    default_currency="INR",
                )
            )

    tracker = StorageCostTracker(local_engine)
    await tracker.record(
        build_turn_cost(
            tenant_id=str(tenant_uuid),
            session_id=str(session_uuid),
            turn_id="t-1",
            model="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=2000,
        )
    )

    total_session = await tracker.total_for_session(str(session_uuid))
    assert total_session > Decimal("0")

    total_today = await tracker.total_for_tenant_today(str(tenant_uuid))
    assert total_today > Decimal("0")

    tokens = await tracker.tokens_for_tenant_today(str(tenant_uuid))
    assert tokens == 3000

    await local_engine.dispose()


@pytest.fixture
def engine():
    """Stub to make the storage test above self-contained."""
    return None
