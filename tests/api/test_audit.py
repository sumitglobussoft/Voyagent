"""Tests for the /audit HTTP read surface.

Mirrors the fixture style of ``tests/api/test_enquiries.py`` and
``tests/api/test_reports.py`` — fresh in-memory SQLite, real FastAPI
``TestClient``, in-house auth tokens minted via ``/auth/sign-up``.

The audit table is already populated in production by the agent
runtime + auth-failure middleware. These tests seed rows directly via
the storage model so we do not have to stand up the full runtime.
"""

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
from sqlalchemy.pool import StaticPool  # noqa: E402

from schemas.storage import Base  # noqa: E402
from schemas.storage.audit import AuditEventRow, AuditStatusEnum  # noqa: E402
from schemas.storage.session import ActorKindEnum  # noqa: E402

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
async def _fresh_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)

    get_auth_settings.cache_clear()
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())

    yield

    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
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


async def _insert_audit(
    *,
    tenant_id: uuid.UUID,
    tool: str = "issue_ticket",
    actor_id: uuid.UUID | None = None,
    actor_kind: ActorKindEnum = ActorKindEnum.HUMAN,
    status: AuditStatusEnum = AuditStatusEnum.SUCCEEDED,
    started_at: datetime | None = None,
    inputs: dict | None = None,
    error: str | None = None,
) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as db:
        row = AuditEventRow(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_kind=actor_kind,
            tool=tool,
            inputs=inputs or {},
            outputs={},
            entity_refs={},
            started_at=started_at or datetime.now(timezone.utc),
            status=status,
            error=error,
        )
        db.add(row)
        await db.commit()
        return row.id


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #


def test_list_requires_auth(client: TestClient) -> None:
    r = client.get("/audit")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Empty case                                                                  #
# --------------------------------------------------------------------------- #


def test_empty_returns_zero(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get("/audit", headers=_auth_headers(signup["access_token"]))
    assert r.status_code == 200
    body = r.json()
    # Sign-up itself does not synthesise audit_events rows (auth-failure
    # middleware only fires on 401/403), so a freshly-signed-up tenant
    # sees an empty audit log.
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 50
    assert body["offset"] == 0


# --------------------------------------------------------------------------- #
# Tenant isolation                                                            #
# --------------------------------------------------------------------------- #


async def test_tenant_isolation(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])
    tenant_b = uuid.UUID(b["user"]["tenant_id"])

    await _insert_audit(tenant_id=tenant_a, tool="issue_ticket")
    await _insert_audit(tenant_id=tenant_a, tool="auth.verify")
    await _insert_audit(tenant_id=tenant_b, tool="issue_ticket")

    r_a = client.get("/audit", headers=_auth_headers(a["access_token"]))
    assert r_a.status_code == 200
    body_a = r_a.json()
    assert body_a["total"] == 2
    assert {item["tenant_id"] for item in body_a["items"]} == {str(tenant_a)}

    r_b = client.get("/audit", headers=_auth_headers(b["access_token"]))
    assert r_b.status_code == 200
    body_b = r_b.json()
    assert body_b["total"] == 1
    assert body_b["items"][0]["tenant_id"] == str(tenant_b)


# --------------------------------------------------------------------------- #
# Filter: kind                                                                #
# --------------------------------------------------------------------------- #


async def test_filter_by_kind(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])

    await _insert_audit(tenant_id=tenant_a, tool="issue_ticket")
    await _insert_audit(tenant_id=tenant_a, tool="issue_ticket")
    await _insert_audit(tenant_id=tenant_a, tool="auth.verify")
    await _insert_audit(tenant_id=tenant_a, tool="hold_fare")

    r = client.get(
        "/audit?kind=issue_ticket",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert all(item["kind"] == "issue_ticket" for item in body["items"])

    # Multi-value via comma-separated.
    r2 = client.get(
        "/audit?kind=auth.verify,hold_fare",
        headers=_auth_headers(a["access_token"]),
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["total"] == 2
    assert {item["kind"] for item in body2["items"]} == {"auth.verify", "hold_fare"}

    # Multi-value via repeated query param.
    r3 = client.get(
        "/audit?kind=auth.verify&kind=hold_fare",
        headers=_auth_headers(a["access_token"]),
    )
    assert r3.status_code == 200
    assert r3.json()["total"] == 2


# --------------------------------------------------------------------------- #
# Filter: actor_id                                                            #
# --------------------------------------------------------------------------- #


async def test_filter_by_actor_id(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])
    user_a = uuid.UUID(a["user"]["id"])
    other_actor = uuid.uuid4()

    # We need a real users row for ``actor_id`` because the column has
    # a FK to ``users.id``. The sign-up above minted ``user_a``; the
    # third row uses ``actor_id=None`` (system-initiated event) which
    # the FK accepts.
    await _insert_audit(tenant_id=tenant_a, tool="issue_ticket", actor_id=user_a)
    await _insert_audit(tenant_id=tenant_a, tool="issue_ticket", actor_id=user_a)
    await _insert_audit(
        tenant_id=tenant_a,
        tool="auth.verify",
        actor_id=None,
        actor_kind=ActorKindEnum.SYSTEM,
    )

    r = client.get(
        f"/audit?actor_id={user_a}",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert all(item["actor_id"] == str(user_a) for item in body["items"])
    # ``actor_email`` is populated from the users table for real users.
    assert all(item["actor_email"] == "alice@a.com" for item in body["items"])

    # Unknown actor → zero rows (not an error).
    r_none = client.get(
        f"/audit?actor_id={other_actor}",
        headers=_auth_headers(a["access_token"]),
    )
    assert r_none.status_code == 200
    assert r_none.json()["total"] == 0


# --------------------------------------------------------------------------- #
# Filter: from / to                                                           #
# --------------------------------------------------------------------------- #


async def test_filter_by_date_range(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])

    # Seed three rows at known timestamps.
    base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    await _insert_audit(
        tenant_id=tenant_a, tool="early", started_at=base - timedelta(days=5)
    )  # 2026-04-05
    await _insert_audit(
        tenant_id=tenant_a, tool="inside", started_at=base
    )  # 2026-04-10
    await _insert_audit(
        tenant_id=tenant_a, tool="late", started_at=base + timedelta(days=5)
    )  # 2026-04-15

    r = client.get(
        "/audit?from=2026-04-08&to=2026-04-12",
        headers=_auth_headers(a["access_token"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["kind"] == "inside"

    # Inclusive on both ends: matching a single day bracket.
    r2 = client.get(
        "/audit?from=2026-04-10&to=2026-04-10",
        headers=_auth_headers(a["access_token"]),
    )
    assert r2.json()["total"] == 1


# --------------------------------------------------------------------------- #
# Pagination                                                                  #
# --------------------------------------------------------------------------- #


async def test_pagination(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])

    # Seed 75 rows with strictly-increasing timestamps so the default
    # ``ORDER BY started_at DESC`` is deterministic.
    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(75):
        await _insert_audit(
            tenant_id=tenant_a,
            tool=f"tool_{i:02d}",
            started_at=base + timedelta(minutes=i),
        )

    r1 = client.get(
        "/audit?limit=50&offset=0",
        headers=_auth_headers(a["access_token"]),
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["total"] == 75
    assert len(body1["items"]) == 50

    r2 = client.get(
        "/audit?limit=50&offset=50",
        headers=_auth_headers(a["access_token"]),
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["total"] == 75
    assert len(body2["items"]) == 25

    # Pages disjoint.
    ids1 = {item["id"] for item in body1["items"]}
    ids2 = {item["id"] for item in body2["items"]}
    assert ids1.isdisjoint(ids2)
    assert len(ids1 | ids2) == 75


# --------------------------------------------------------------------------- #
# Invalid params                                                              #
# --------------------------------------------------------------------------- #


def test_invalid_actor_id_returns_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get(
        "/audit?actor_id=not-a-uuid",
        headers=_auth_headers(signup["access_token"]),
    )
    assert r.status_code == 422


def test_limit_out_of_range_returns_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    # The route caps ``limit`` at 200; 201 should trip FastAPI's
    # automatic validation.
    r = client.get(
        "/audit?limit=201",
        headers=_auth_headers(signup["access_token"]),
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Shape                                                                       #
# --------------------------------------------------------------------------- #


async def test_response_shape_includes_summary_status_payload(
    client: TestClient,
) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])

    await _insert_audit(
        tenant_id=tenant_a,
        tool="issue_ticket",
        inputs={"pnr": "ABC123"},
        status=AuditStatusEnum.FAILED,
        error="timeout",
    )

    r = client.get("/audit", headers=_auth_headers(a["access_token"]))
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["kind"] == "issue_ticket"
    assert item["status"] == "error"
    assert "timeout" in item["summary"]
    assert item["payload"]["inputs"] == {"pnr": "ABC123"}
    assert item["payload"]["error"] == "timeout"
