"""Round-trip + default-value tests for :mod:`schemas.storage.tenant_settings`."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import Tenant, TenantSettingsRow, uuid7

pytestmark = pytest.mark.asyncio


async def test_tenant_settings_round_trip(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tid = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tid, display_name="T", default_currency="INR"))
            db.add(
                TenantSettingsRow(
                    tenant_id=tid,
                    model="claude-opus-4-6",
                    system_prompt_suffix="Quote in INR by default.",
                    rate_limit_per_minute=120,
                    rate_limit_per_hour=2000,
                    daily_token_budget=500_000,
                    locale="hi",
                    timezone="Asia/Kolkata",
                    default_currency="INR",
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(TenantSettingsRow).where(
                    TenantSettingsRow.tenant_id == tid
                )
            )
        ).scalar_one()
        assert row.model == "claude-opus-4-6"
        assert row.system_prompt_suffix == "Quote in INR by default."
        assert row.rate_limit_per_minute == 120
        assert row.rate_limit_per_hour == 2000
        assert row.daily_token_budget == 500_000
        assert row.locale == "hi"
        assert row.timezone == "Asia/Kolkata"
        assert row.default_currency == "INR"
        assert row.created_at is not None
        assert row.updated_at is not None


async def test_tenant_settings_defaults(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tid = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=tid, display_name="T", default_currency="USD"))
            db.add(TenantSettingsRow(tenant_id=tid))

    async with Session() as db:
        row = (
            await db.execute(
                select(TenantSettingsRow).where(
                    TenantSettingsRow.tenant_id == tid
                )
            )
        ).scalar_one()
        assert row.model is None
        assert row.system_prompt_suffix is None
        assert row.rate_limit_per_minute == 60
        assert row.rate_limit_per_hour == 1000
        assert row.daily_token_budget is None
        assert row.locale == "en"
        assert row.timezone == "UTC"
        assert row.default_currency == "INR"


async def test_tenant_settings_isolation_per_tenant(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    a = uuid7()
    b = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(Tenant(id=a, display_name="A", default_currency="INR"))
            db.add(Tenant(id=b, display_name="B", default_currency="INR"))
            db.add(TenantSettingsRow(tenant_id=a, model="claude-sonnet-4-5"))
            db.add(TenantSettingsRow(tenant_id=b, model="claude-opus-4-6"))

    async with Session() as db:
        row_a = (
            await db.execute(
                select(TenantSettingsRow).where(
                    TenantSettingsRow.tenant_id == a
                )
            )
        ).scalar_one()
        row_b = (
            await db.execute(
                select(TenantSettingsRow).where(
                    TenantSettingsRow.tenant_id == b
                )
            )
        ).scalar_one()
        assert row_a.model == "claude-sonnet-4-5"
        assert row_b.model == "claude-opus-4-6"
