"""Tests for the /api/approvals HTTP surface."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)
os.environ.setdefault("VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", "true")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base  # noqa: E402
from schemas.storage.audit import AuditEventRow  # noqa: E402
from schemas.storage.session import (  # noqa: E402
    ActorKindEnum,
    ApprovalStatusEnum,
    PendingApprovalRow,
    SessionRow,
)
from sqlalchemy import func, select  # noqa: E402

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
async def _fresh_db(tmp_path):
    from voyagent_api import audit as _audit_module

    # A file-based SQLite DB rather than ``:memory:`` — under
    # ``aiosqlite + StaticPool + fastapi.TestClient`` the in-memory DB
    # is discarded when the TestClient's worker thread recycles the
    # aiosqlite connection, which silently drops all tables mid-test.
    # A tmp file survives across threads; the file is auto-cleaned at
    # end of the test session by pytest's ``tmp_path`` fixture.
    db_path = tmp_path / "voyagent-approvals-test.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)

    get_auth_settings.cache_clear()
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())
    # Reset the auth-failure sink singleton so previous tests don't bleed
    # through. Harmless if it wasn't set.
    _audit_module.set_api_audit_sink_for_test(None)

    yield

    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    _audit_module.set_api_audit_sink_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_PASSWORD = "Sup3rSecretValue!"


def _sign_up(client: TestClient, *, email: str, agency: str) -> dict:
    body = {
        "email": email,
        "password": _PASSWORD,
        "full_name": f"User {email}",
        "agency_name": agency,
    }
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _insert_session(tenant_id: str) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = SessionRow(
            tenant_id=uuid.UUID(tenant_id),
            actor_id=None,
            actor_kind=ActorKindEnum.HUMAN,
        )
        s.add(row)
        await s.commit()
        return row.id


async def _insert_approval(
    *,
    approval_id: str,
    session_id: uuid.UUID,
    tool_name: str = "issue_ticket",
    summary: str = "Issue ticket for PNR ABC123",
    turn_id: str = "turn-1",
    status: ApprovalStatusEnum = ApprovalStatusEnum.PENDING,
    requested_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> None:
    sm = db_module.get_sessionmaker()
    now = datetime.now(timezone.utc)
    req = requested_at or now
    exp = expires_at if expires_at is not None else (req + timedelta(minutes=15))
    async with sm() as s:
        s.add(
            PendingApprovalRow(
                id=approval_id,
                session_id=session_id,
                tool_name=tool_name,
                summary=summary,
                turn_id=turn_id,
                requested_at=req,
                status=status,
                expires_at=exp,
            )
        )
        await s.commit()


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #


def test_list_requires_auth(client: TestClient) -> None:
    r = client.get("/approvals")
    assert r.status_code == 401


def test_get_requires_auth(client: TestClient) -> None:
    r = client.get(f"/approvals/{uuid.uuid4()}")
    assert r.status_code == 401


def test_resolve_requires_auth(client: TestClient) -> None:
    r = client.post(
        f"/approvals/{uuid.uuid4()}/resolve",
        json={"granted": True},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# List                                                                        #
# --------------------------------------------------------------------------- #


async def test_list_returns_tenant_pending_approvals(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Tenant A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-1", session_id=sid)
    await _insert_approval(
        approval_id="ap-2",
        session_id=sid,
        tool_name="refund_ticket",
        summary="Refund TK-42",
    )

    r = client.get(
        "/approvals",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    ids = {i["id"] for i in body["items"]}
    assert ids == {"ap-1", "ap-2"}
    first = body["items"][0]
    assert first["session_id"] == str(sid)
    assert first["status"] == "pending"
    assert first["payload"] == {}
    assert first["resolved_at"] is None
    assert first["resolved_by_user_id"] is None


async def test_list_filters_by_session_id(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Tenant A")
    tenant_id = signup["user"]["tenant_id"]
    sid_a = await _insert_session(tenant_id)
    sid_b = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-a", session_id=sid_a)
    await _insert_approval(approval_id="ap-b", session_id=sid_b)

    r = client.get(
        f"/approvals?session_id={sid_b}",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "ap-b"


async def test_list_status_all_shows_resolved_and_pending(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Tenant A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-1", session_id=sid)
    await _insert_approval(
        approval_id="ap-2",
        session_id=sid,
        status=ApprovalStatusEnum.GRANTED,
    )

    # Default status=pending hides the granted one.
    r = client.get(
        "/approvals",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert {i["id"] for i in r.json()["items"]} == {"ap-1"}

    # status=all shows both.
    r_all = client.get(
        "/approvals?status=all",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert {i["id"] for i in r_all.json()["items"]} == {"ap-1", "ap-2"}


async def test_list_tenant_isolation(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    sid_a = await _insert_session(a["user"]["tenant_id"])
    sid_b = await _insert_session(b["user"]["tenant_id"])
    await _insert_approval(approval_id="ap-a", session_id=sid_a)
    await _insert_approval(approval_id="ap-b", session_id=sid_b)

    r_a = client.get(
        "/approvals",
        headers={"Authorization": f"Bearer {a['access_token']}"},
    )
    assert {i["id"] for i in r_a.json()["items"]} == {"ap-a"}

    r_b = client.get(
        "/approvals",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert {i["id"] for i in r_b.json()["items"]} == {"ap-b"}


async def test_list_lazy_sweep_expires_past_deadline(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await _insert_approval(
        approval_id="ap-expired",
        session_id=sid,
        requested_at=past - timedelta(minutes=15),
        expires_at=past,
    )

    # status=pending should now be empty because the sweep flipped it.
    r = client.get(
        "/approvals",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["items"] == []

    # status=all shows the row as expired.
    r_all = client.get(
        "/approvals?status=all",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    items = r_all.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "expired"


# --------------------------------------------------------------------------- #
# Single-item GET                                                             #
# --------------------------------------------------------------------------- #


async def test_get_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-1", session_id=sid)

    r = client.get(
        "/approvals/ap-1",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "ap-1"


async def test_get_cross_tenant_returns_404(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    sid_a = await _insert_session(a["user"]["tenant_id"])
    await _insert_approval(approval_id="ap-a", session_id=sid_a)

    r = client.get(
        "/approvals/ap-a",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "approval_not_found"


def test_get_unknown_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get(
        "/approvals/does-not-exist",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Resolve                                                                     #
# --------------------------------------------------------------------------- #


async def test_resolve_grant_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-1", session_id=sid)

    r = client.post(
        "/approvals/ap-1/resolve",
        json={"granted": True, "reason": "looks good"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "granted"
    assert body["resolved_at"] is not None


async def test_resolve_reject_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-1", session_id=sid)

    r = client.post(
        "/approvals/ap-1/resolve",
        json={"granted": False},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


async def test_resolve_already_resolved_returns_409(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(
        approval_id="ap-1",
        session_id=sid,
        status=ApprovalStatusEnum.GRANTED,
    )

    r = client.post(
        "/approvals/ap-1/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "approval_already_resolved"


async def test_resolve_idempotent_second_call_returns_409(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-1", session_id=sid)
    token = signup["access_token"]

    r1 = client.post(
        "/approvals/ap-1/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/approvals/ap-1/resolve",
        json={"granted": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 409


async def test_resolve_cross_tenant_returns_404_not_403(
    client: TestClient,
) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    sid_a = await _insert_session(a["user"]["tenant_id"])
    await _insert_approval(approval_id="ap-a", session_id=sid_a)

    r = client.post(
        "/approvals/ap-a/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "approval_not_found"


def test_resolve_unknown_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/approvals/no-such-thing/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404


def test_resolve_422_on_missing_granted(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/approvals/ap-x/resolve",
        json={},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


async def _count_audit_rows() -> int:
    """Count rows in ``audit_events`` via a freshly-opened session bound
    to the live engine. We go through ``AsyncSession(bind=engine)`` (vs
    the process-wide sessionmaker) to dodge an intermittent
    ``no such table`` observed under ``aiosqlite + StaticPool +
    fastapi.TestClient`` when the sessionmaker is acquired across a
    TestClient thread boundary."""
    from sqlalchemy.ext.asyncio import AsyncSession

    engine = db_module.get_engine()
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        return int(
            (await s.execute(select(func.count()).select_from(AuditEventRow)))
            .scalar_one()
            or 0
        )


async def _fetch_audit_rows() -> list[AuditEventRow]:
    from sqlalchemy.ext.asyncio import AsyncSession

    engine = db_module.get_engine()
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        rows = (
            (
                await s.execute(
                    select(AuditEventRow).order_by(AuditEventRow.started_at)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def test_resolve_grant_writes_audit_event(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-aud-1", session_id=sid)

    r = client.post(
        "/approvals/ap-aud-1/resolve",
        json={"granted": True, "reason": "ok with this"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text

    # Fresh DB per test — exactly one audit row should exist now.
    rows = await _fetch_audit_rows()
    assert len(rows) == 1
    row = rows[-1]
    assert row.tool == "approval.granted"
    assert str(row.tenant_id) == tenant_id
    assert str(row.actor_id) == signup["user"]["id"]
    # ``HUMAN`` in storage surfaces as ``user`` on the wire, which is
    # what the task spec calls for.
    assert row.actor_kind == ActorKindEnum.HUMAN
    assert row.inputs["approval_id"] == "ap-aud-1"
    assert row.inputs["session_id"] == str(sid)
    assert row.inputs["tool_name"] == "issue_ticket"
    assert row.inputs["reason"] == "ok with this"


async def test_resolve_reject_writes_audit_event(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(
        approval_id="ap-aud-2",
        session_id=sid,
        tool_name="refund_ticket",
    )

    r = client.post(
        "/approvals/ap-aud-2/resolve",
        json={"granted": False, "reason": "policy violation"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text

    rows = await _fetch_audit_rows()
    assert len(rows) == 1
    row = rows[-1]
    assert row.tool == "approval.rejected"
    assert row.inputs["approval_id"] == "ap-aud-2"
    assert row.inputs["tool_name"] == "refund_ticket"
    assert row.inputs["reason"] == "policy violation"


async def test_resolve_409_does_not_write_audit(client: TestClient) -> None:
    """409 already-resolved must not append to ``audit_events`` — only
    successful state transitions write a row. The fresh-DB fixture
    starts this test with zero audit rows, so the post-call count must
    still be zero."""
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(
        approval_id="ap-aud-409",
        session_id=sid,
        status=ApprovalStatusEnum.GRANTED,
    )

    r = client.post(
        "/approvals/ap-aud-409/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 409
    assert await _count_audit_rows() == 0


async def test_resolve_404_does_not_write_audit(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")

    r = client.post(
        "/approvals/no-such-id/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404
    assert await _count_audit_rows() == 0


async def test_resolve_cross_tenant_does_not_write_audit(
    client: TestClient,
) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    sid_a = await _insert_session(a["user"]["tenant_id"])
    await _insert_approval(approval_id="ap-x-tenant", session_id=sid_a)

    r = client.post(
        "/approvals/ap-x-tenant/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    # Cross-tenant surfaces as 404 (the handler refuses to confirm
    # existence across tenants), not 403.
    assert r.status_code == 404
    assert await _count_audit_rows() == 0


async def test_resolve_audit_write_failure_does_not_block_resolution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Schema drift / DB hiccup on the audit insert must not roll back
    the approval state transition — the approval table is the source of
    truth; the audit table is a best-effort read-only history."""
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    await _insert_approval(approval_id="ap-fail-aud", session_id=sid)

    from voyagent_api import approvals as _approvals

    async def _boom(*args, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError("simulated audit DB outage")

    monkeypatch.setattr(_approvals, "_write_approval_audit", _boom)

    r = client.post(
        "/approvals/ap-fail-aud/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    # The resolution still succeeds ...
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "granted"
    # ... and the approval row is actually updated in the DB.
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(
                select(PendingApprovalRow).where(
                    PendingApprovalRow.id == "ap-fail-aud"
                )
            )
        ).scalar_one()
        assert row.status == ApprovalStatusEnum.GRANTED
        assert row.resolved_at is not None


async def test_resolve_past_deadline_returns_409_and_expires(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_id = signup["user"]["tenant_id"]
    sid = await _insert_session(tenant_id)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    # Insert a raw pending row that hasn't been swept yet.
    await _insert_approval(
        approval_id="ap-stale",
        session_id=sid,
        requested_at=past - timedelta(minutes=15),
        expires_at=past,
    )

    # Resolve bypasses the list sweep — verify the per-row deadline check.
    r = client.post(
        "/approvals/ap-stale/resolve",
        json={"granted": True},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    # Either the upfront list-style sweep already flipped it (409), or
    # the per-row deadline guard catches it (also 409). Both pathways
    # should produce the same observable result.
    assert r.status_code == 409
    assert r.json()["detail"] == "approval_already_resolved"
