"""Round-trip + constraint tests for :mod:`schemas.storage.invite`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import (
    InviteRow,
    InviteStatusEnum,
    Tenant,
    User,
    UserRole,
    uuid7,
)

pytestmark = pytest.mark.asyncio


async def _seed_tenant_and_inviter(engine: AsyncEngine) -> tuple[str, str]:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid7()
    user_id = uuid7()
    async with Session() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_id,
                    display_name="Acme Travel",
                    default_currency="USD",
                )
            )
            db.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    external_id="ext-1",
                    display_name="Owner",
                    email="owner@acme.test",
                    role=UserRole.AGENCY_ADMIN,
                    password_hash="x",
                    email_verified=True,
                )
            )
    return str(tenant_id), str(user_id)


async def test_invite_round_trip(engine: AsyncEngine) -> None:
    tenant_id, user_id = await _seed_tenant_and_inviter(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    import uuid

    expires = datetime.now(timezone.utc) + timedelta(days=7)
    async with Session() as db:
        async with db.begin():
            db.add(
                InviteRow(
                    tenant_id=uuid.UUID(tenant_id),
                    invited_by_user_id=uuid.UUID(user_id),
                    email="invitee@acme.test",
                    role="agent",
                    token_hash="a" * 64,
                    status=InviteStatusEnum.PENDING,
                    expires_at=expires,
                )
            )

    async with Session() as db:
        row = (
            await db.execute(
                select(InviteRow).where(
                    InviteRow.email == "invitee@acme.test"
                )
            )
        ).scalar_one()
        assert row.status == InviteStatusEnum.PENDING
        assert row.role == "agent"
        assert row.accepted_at is None
        assert row.revoked_at is None


async def test_invite_token_hash_unique(engine: AsyncEngine) -> None:
    tenant_id, user_id = await _seed_tenant_and_inviter(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    import uuid

    expires = datetime.now(timezone.utc) + timedelta(days=7)
    async with Session() as db:
        async with db.begin():
            db.add(
                InviteRow(
                    tenant_id=uuid.UUID(tenant_id),
                    invited_by_user_id=uuid.UUID(user_id),
                    email="a@acme.test",
                    role="agent",
                    token_hash="dup-hash",
                    status=InviteStatusEnum.PENDING,
                    expires_at=expires,
                )
            )

    with pytest.raises(IntegrityError):
        async with Session() as db:
            async with db.begin():
                db.add(
                    InviteRow(
                        tenant_id=uuid.UUID(tenant_id),
                        invited_by_user_id=uuid.UUID(user_id),
                        email="b@acme.test",
                        role="agent",
                        token_hash="dup-hash",
                        status=InviteStatusEnum.PENDING,
                        expires_at=expires,
                    )
                )


async def test_invite_tenant_email_unique_ci(engine: AsyncEngine) -> None:
    tenant_id, user_id = await _seed_tenant_and_inviter(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    import uuid

    expires = datetime.now(timezone.utc) + timedelta(days=7)
    async with Session() as db:
        async with db.begin():
            db.add(
                InviteRow(
                    tenant_id=uuid.UUID(tenant_id),
                    invited_by_user_id=uuid.UUID(user_id),
                    email="dup@acme.test",
                    role="agent",
                    token_hash="h1",
                    status=InviteStatusEnum.PENDING,
                    expires_at=expires,
                )
            )

    # SQLite honors the partial-free lower(email) expression-index too.
    with pytest.raises(IntegrityError):
        async with Session() as db:
            async with db.begin():
                db.add(
                    InviteRow(
                        tenant_id=uuid.UUID(tenant_id),
                        invited_by_user_id=uuid.UUID(user_id),
                        email="DUP@acme.test",
                        role="agent",
                        token_hash="h2",
                        status=InviteStatusEnum.PENDING,
                        expires_at=expires,
                    )
                )
