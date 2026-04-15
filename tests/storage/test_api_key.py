"""Storage-layer round-trip tests for :class:`ApiKeyRow`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import ApiKeyRow, Tenant, User, UserRole, uuid7

pytestmark = pytest.mark.asyncio


async def _seed_tenant_and_user(db) -> tuple[Tenant, User]:  # type: ignore[no-untyped-def]
    tenant = Tenant(display_name="Acme", default_currency="INR")
    db.add(tenant)
    await db.flush()
    user = User(
        tenant_id=tenant.id,
        external_id="ext-1",
        display_name="Agent",
        email="agent@acme.test",
        role=UserRole.AGENT,
        password_hash="argon-placeholder",
        email_verified=True,
    )
    db.add(user)
    await db.flush()
    return tenant, user


async def test_api_key_round_trip(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        async with db.begin():
            tenant, user = await _seed_tenant_and_user(db)
            db.add(
                ApiKeyRow(
                    tenant_id=tenant.id,
                    created_by_user_id=user.id,
                    name="CI key",
                    prefix="abcd1234",
                    key_hash="h" * 64,
                    scopes="full",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(ApiKeyRow).where(ApiKeyRow.prefix == "abcd1234")
            )
        ).scalar_one()
        assert row.name == "CI key"
        assert row.scopes == "full"
        assert row.revoked_at is None
        assert row.last_used_at is None
        assert row.expires_at is not None


async def test_api_key_unique_hash(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        async with db.begin():
            tenant, user = await _seed_tenant_and_user(db)
            db.add(
                ApiKeyRow(
                    tenant_id=tenant.id,
                    created_by_user_id=user.id,
                    name="k1",
                    prefix="aaaaaaaa",
                    key_hash="d" * 64,
                )
            )

    async with Session() as db:
        row_user = (
            await db.execute(select(User).where(User.email == "agent@acme.test"))
        ).scalar_one()
        db.add(
            ApiKeyRow(
                tenant_id=row_user.tenant_id,
                created_by_user_id=row_user.id,
                name="k2",
                prefix="bbbbbbbb",
                key_hash="d" * 64,  # duplicate
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
