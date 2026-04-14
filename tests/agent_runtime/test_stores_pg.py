"""Unit tests for the Postgres-backed stores using aiosqlite.

The ``PostgresSessionStore`` / ``PostgresAuditSink`` names reflect the
production target, but the shape (engine-driven, async SQLAlchemy) is
dialect-portable enough that aiosqlite is a faithful unit-test stand-in.
Integration tests against real Postgres live in a separate CI lane.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from schemas.canonical import ActorKind, AuditEvent, AuditStatus
from schemas.storage import (
    ActorKindEnum,
    AuditEventRow,
    Base,
    Tenant,
    User,
    UserRole,
    uuid7,
)

from voyagent_agent_runtime.session import Message, PendingApproval, Session
from voyagent_agent_runtime.stores_pg import (
    PostgresAuditSink,
    PostgresSessionStore,
    build_pg_stores,
)

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


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


async def _seed_tenant_and_user(
    engine: AsyncEngine, tenant_uuid: uuid.UUID, user_uuid: uuid.UUID
) -> None:
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
            db.add(
                User(
                    id=user_uuid,
                    tenant_id=tenant_uuid,
                    external_id="ext",
                    display_name="U",
                    email="u@example.com",
                    role=UserRole.AGENT,
                )
            )


def _eid(value: uuid.UUID) -> str:
    return str(value)


# --------------------------------------------------------------------------- #
# Session store tests                                                         #
# --------------------------------------------------------------------------- #


async def test_build_pg_stores_returns_both(engine: AsyncEngine) -> None:
    session_store, audit_sink = await build_pg_stores(engine)
    assert isinstance(session_store, PostgresSessionStore)
    assert isinstance(audit_sink, PostgresAuditSink)


async def test_put_and_get_round_trip(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    store = PostgresSessionStore(engine)
    session_uuid = uuid7()
    sess = Session(
        id=_eid(session_uuid),
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(sess)

    fetched = await store.get(_eid(session_uuid))
    assert fetched is not None
    assert fetched.tenant_id == _eid(tenant_uuid)
    assert fetched.actor_kind == ActorKind.HUMAN
    assert fetched.message_history == []
    assert fetched.pending_approvals == {}


async def test_put_is_upsert(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    store = PostgresSessionStore(engine)
    session_uuid = uuid7()
    sess = Session(
        id=_eid(session_uuid),
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(sess)
    # Re-put with same id must not duplicate.
    await store.put(sess)
    fetched = await store.get(_eid(session_uuid))
    assert fetched is not None


async def test_append_message_assigns_monotonic_sequence(
    engine: AsyncEngine,
) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    store = PostgresSessionStore(engine)
    session_uuid = uuid7()
    sess = Session(
        id=_eid(session_uuid),
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(sess)

    for text in ("one", "two", "three"):
        await store.append_message(
            _eid(session_uuid),
            Message(role="user", content=[{"type": "text", "text": text}]),
        )

    fetched = await store.get(_eid(session_uuid))
    assert fetched is not None
    assert [m.content[0]["text"] for m in fetched.message_history] == [
        "one",
        "two",
        "three",
    ]


async def test_add_and_resolve_approval(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    store = PostgresSessionStore(engine)
    session_uuid = uuid7()
    sess = Session(
        id=_eid(session_uuid),
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(sess)

    ap = PendingApproval(
        id="ap-turn1-issue_ticket",
        tool_name="issue_ticket",
        summary="Approve?",
        turn_id="turn1",
    )
    await store.add_approval(_eid(session_uuid), ap)
    fetched = await store.get(_eid(session_uuid))
    assert fetched is not None
    assert fetched.pending_approvals["ap-turn1-issue_ticket"].granted is None

    await store.resolve_approval(
        _eid(session_uuid), "ap-turn1-issue_ticket", granted=True
    )
    fetched = await store.get(_eid(session_uuid))
    assert fetched is not None
    resolved = fetched.pending_approvals["ap-turn1-issue_ticket"]
    assert resolved.granted is True
    assert resolved.resolved_at is not None


async def test_resolve_unknown_approval_raises_key_error(
    engine: AsyncEngine,
) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    store = PostgresSessionStore(engine)
    session_uuid = uuid7()
    sess = Session(
        id=_eid(session_uuid),
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(sess)

    with pytest.raises(KeyError):
        await store.resolve_approval(_eid(session_uuid), "nope", granted=False)


async def test_get_missing_session_returns_none(engine: AsyncEngine) -> None:
    store = PostgresSessionStore(engine)
    assert await store.get(_eid(uuid7())) is None


# --------------------------------------------------------------------------- #
# Audit sink tests                                                            #
# --------------------------------------------------------------------------- #


async def test_audit_write_roundtrip(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    sink = PostgresAuditSink(engine)
    event_id = uuid7()
    event = AuditEvent(
        id=_eid(event_id),
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
        tool="issue_ticket",
        driver="amadeus",
        inputs={"pnr_id": "abc"},
        started_at=datetime.now(timezone.utc),
        status=AuditStatus.STARTED,
    )
    await sink.write(event)

    Sess = async_sessionmaker(engine, expire_on_commit=False)
    async with Sess() as db:
        row = await db.get(AuditEventRow, event_id)
    assert row is not None
    assert row.tool == "issue_ticket"
    assert row.status.value == "started"

    # Writing again with the same id upserts status / outputs.
    event2 = event.model_copy(
        update={
            "status": AuditStatus.SUCCEEDED,
            "outputs": {"ok": True},
            "completed_at": datetime.now(timezone.utc),
        }
    )
    await sink.write(event2)
    async with Sess() as db:
        row = await db.get(AuditEventRow, event_id)
    assert row is not None
    assert row.status.value == "succeeded"
    assert row.outputs == {"ok": True}


async def test_audit_start_succeed_fail_cycle(engine: AsyncEngine) -> None:
    tenant_uuid = uuid7()
    user_uuid = uuid7()
    await _seed_tenant_and_user(engine, tenant_uuid, user_uuid)

    sink = PostgresAuditSink(engine)
    audit_id = await sink.start(
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
        tool="post_payment",
        inputs={"amount": "100.00"},
    )
    assert audit_id is not None
    await sink.succeed(audit_id, {"receipt": "r1"})

    Sess = async_sessionmaker(engine, expire_on_commit=False)
    async with Sess() as db:
        row = await db.get(AuditEventRow, audit_id)
    assert row is not None
    assert row.status.value == "succeeded"
    assert row.outputs == {"receipt": "r1"}
    assert row.completed_at is not None

    # Second event for a fail path.
    audit_id2 = await sink.start(
        tenant_id=_eid(tenant_uuid),
        actor_id=_eid(user_uuid),
        actor_kind=ActorKind.HUMAN,
        tool="post_payment",
    )
    assert audit_id2 is not None
    await sink.fail(audit_id2, "boom")
    async with Sess() as db:
        row = await db.get(AuditEventRow, audit_id2)
    assert row is not None
    assert row.status.value == "failed"
    assert row.error == "boom"


async def test_audit_best_effort_swallows_broken_engine(
    engine: AsyncEngine,
) -> None:
    """Disposing the engine and issuing a write must not raise.

    The sink swallows all exceptions so a tool call never fails purely
    because of an audit write. This is a load-bearing property of the
    implementation.
    """
    await engine.dispose()
    sink = PostgresAuditSink(engine)
    event = AuditEvent(
        id=_eid(uuid7()),
        tenant_id=_eid(uuid7()),
        actor_id=_eid(uuid7()),
        actor_kind=ActorKind.HUMAN,
        tool="issue_ticket",
        started_at=datetime.now(timezone.utc),
        status=AuditStatus.STARTED,
    )
    # No assertion — the bar is "does not raise".
    await sink.write(event)
