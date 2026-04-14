"""Smoke-level round-trip test for every storage model.

Covers: Tenant, TenantCredential, User, SessionRow, MessageRow,
PendingApprovalRow, AuditEventRow. The test does not exercise every
constraint — that's what the dedicated store tests are for — it just
proves the ORM mappings, foreign keys, and defaults line up.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from schemas.storage import (
    ActorKindEnum,
    AuditEventRow,
    AuditStatusEnum,
    MessageRow,
    PendingApprovalRow,
    SessionRow,
    Tenant,
    TenantCredential,
    User,
    UserRole,
    uuid7,
)

pytestmark = pytest.mark.asyncio


async def test_full_round_trip(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)

    tenant_id = uuid7()
    user_id = uuid7()
    session_id = uuid7()

    async with Session() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_id,
                    display_name="ACME Travels",
                    default_currency="INR",
                )
            )
            db.add(
                TenantCredential(
                    tenant_id=tenant_id,
                    provider="amadeus",
                    encrypted_blob=b"\x00\x01",
                    nonce=b"\x02",
                    meta={"api_base": "https://test.api.amadeus.example"},
                )
            )
            db.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    external_id=str(user_id),
                    display_name="Ada",
                    email="ada@example.com",
                    password_hash="$argon2id$v=19$m=65536,t=3,p=4$stub$stub",
                    role=UserRole.AGENCY_ADMIN,
                )
            )
            db.add(
                SessionRow(
                    id=session_id,
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    actor_kind=ActorKindEnum.HUMAN,
                )
            )

        async with db.begin():
            db.add(
                MessageRow(
                    session_id=session_id,
                    role="user",
                    content=[{"type": "text", "text": "hi"}],
                    sequence=0,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                PendingApprovalRow(
                    id="ap-turn1-issue_ticket",
                    session_id=session_id,
                    tool_name="issue_ticket",
                    summary="Approve issue_ticket?",
                    turn_id="turn1",
                    requested_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    actor_kind=ActorKindEnum.HUMAN,
                    tool="issue_ticket",
                    driver="amadeus",
                    inputs={"pnr_id": "abc"},
                    outputs={},
                    started_at=datetime.now(timezone.utc),
                    status=AuditStatusEnum.STARTED,
                )
            )

    async with Session() as db:
        tenant_row = (
            await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one()
        assert tenant_row.display_name == "ACME Travels"
        assert tenant_row.default_currency == "INR"

        cred = (
            await db.execute(
                select(TenantCredential).where(
                    TenantCredential.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        assert cred.provider == "amadeus"
        assert cred.encrypted_blob == b"\x00\x01"
        assert cred.meta["api_base"].startswith("https://")

        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        assert user.role == UserRole.AGENCY_ADMIN

        session_row = (
            await db.execute(
                select(SessionRow).where(SessionRow.id == session_id)
            )
        ).scalar_one()
        assert session_row.actor_kind == ActorKindEnum.HUMAN

        msg = (
            await db.execute(
                select(MessageRow).where(MessageRow.session_id == session_id)
            )
        ).scalar_one()
        assert msg.sequence == 0
        assert msg.content[0]["text"] == "hi"

        ap = (
            await db.execute(
                select(PendingApprovalRow).where(
                    PendingApprovalRow.session_id == session_id
                )
            )
        ).scalar_one()
        assert ap.tool_name == "issue_ticket"
        assert ap.granted is None

        audit = (
            await db.execute(
                select(AuditEventRow).where(AuditEventRow.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert audit.tool == "issue_ticket"
        assert audit.status == AuditStatusEnum.STARTED
