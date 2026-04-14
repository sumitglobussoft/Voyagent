"""Tests for the read-only /reports/* endpoints.

Mirrors the fixture style used in ``tests/api/test_auth_inhouse.py`` —
fresh in-memory SQLite, real FastAPI ``TestClient``, in-house auth
tokens minted via the sign-up endpoint so the principal dependency
validates end-to-end.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base  # noqa: E402
from schemas.storage.session import (  # noqa: E402
    ActorKindEnum,
    MessageRow,
    SessionRow,
)

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
async def _fresh_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
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


async def _insert_session(tenant_id: str) -> uuid.UUID:
    """Insert a SessionRow for ``tenant_id`` and return its id."""
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = SessionRow(
            tenant_id=uuid.UUID(tenant_id),
            actor_id=None,
            actor_kind=ActorKindEnum.HUMAN,
        )
        s.add(row)
        await s.flush()
        sid = row.id
        # messages — include one structured "flight" block the report
        # scraper should pick up, plus noise.
        s.add(
            MessageRow(
                id=uuid.uuid4(),
                session_id=sid,
                role="assistant",
                sequence=1,
                created_at=datetime.now(timezone.utc),
                content=[
                    {"type": "text", "text": "hello"},
                    {
                        "type": "tool_result",
                        "data": {
                            "kind": "flight",
                            "value": {
                                "pnr": "ABC123",
                                "origin": "DEL",
                                "dest": "DXB",
                                "depart": "2026-05-01T09:00:00Z",
                                "carrier": "EK",
                            },
                        },
                    },
                    {
                        "type": "tool_result",
                        "data": {
                            "kind": "passenger",
                            "value": {
                                "full_name": "Alice Example",
                                "passport_number": "P1234567",
                            },
                        },
                    },
                ],
            )
        )
        await s.commit()
        return sid


# --------------------------------------------------------------------------- #
# Unauthenticated access                                                      #
# --------------------------------------------------------------------------- #


def test_receivables_requires_auth(client: TestClient) -> None:
    r = client.get("/reports/receivables?from=2026-01-01&to=2026-01-31")
    assert r.status_code == 401


def test_payables_requires_auth(client: TestClient) -> None:
    r = client.get("/reports/payables?from=2026-01-01&to=2026-01-31")
    assert r.status_code == 401


def test_itinerary_requires_auth(client: TestClient) -> None:
    r = client.get(f"/reports/itinerary?session_id={uuid.uuid4()}")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Happy-path receivables / payables                                           #
# --------------------------------------------------------------------------- #


def test_receivables_returns_empty_shape(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/receivables?from=2026-01-01&to=2026-01-31",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == signup["user"]["tenant_id"]
    assert body["period"] == {"from": "2026-01-01", "to": "2026-01-31"}
    assert body["total_outstanding"] == {"amount": "0.00", "currency": "INR"}
    buckets = {b["bucket"]: b for b in body["aging_buckets"]}
    assert set(buckets) == {"0-30", "31-60", "61-90", "90+"}
    for b in buckets.values():
        assert b["count"] == 0
        assert b["amount"]["amount"] == "0.00"
    assert body["top_debtors"] == []


def test_payables_returns_empty_shape(client: TestClient) -> None:
    signup = _sign_up(client, email="bob@example.com", agency="Bob Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/payables?from=2026-01-01&to=2026-03-31",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == {"from": "2026-01-01", "to": "2026-03-31"}
    assert len(body["aging_buckets"]) == 4
    assert body["top_creditors"] == []


def test_invalid_date_range_rejects_with_422(client: TestClient) -> None:
    signup = _sign_up(client, email="carol@example.com", agency="Carol Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/receivables?from=2026-05-01&to=2026-04-01",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 422


def test_malformed_date_rejects_with_422(client: TestClient) -> None:
    signup = _sign_up(client, email="dave@example.com", agency="Dave Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/receivables?from=not-a-date&to=2026-04-01",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Itinerary — happy path + tenant isolation                                   #
# --------------------------------------------------------------------------- #


async def test_itinerary_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    tenant_id = signup["user"]["tenant_id"]

    sid = await _insert_session(tenant_id)

    r = client.get(
        f"/reports/itinerary?session_id={sid}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == tenant_id
    assert body["session_id"] == str(sid)
    assert body["total_cost"] == {"amount": "0.00", "currency": "INR"}
    assert body["hotels"] == []
    assert body["visas"] == []
    assert len(body["flights"]) == 1
    assert body["flights"][0]["pnr"] == "ABC123"
    assert body["flights"][0]["origin"] == "DEL"
    assert len(body["passengers"]) == 1
    assert body["passengers"][0]["full_name"] == "Alice Example"


async def test_itinerary_tenant_isolation(client: TestClient) -> None:
    # Tenant A owns a session.
    a = _sign_up(client, email="alice@a.com", agency="Tenant A")
    a_tenant_id = a["user"]["tenant_id"]
    a_sid = await _insert_session(a_tenant_id)

    # Tenant B has a different token.
    b = _sign_up(client, email="bob@b.com", agency="Tenant B")
    b_access = b["access_token"]

    # Tenant B asks for Tenant A's session -> 404, not 403.
    r = client.get(
        f"/reports/itinerary?session_id={a_sid}",
        headers={"Authorization": f"Bearer {b_access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "session_not_found"


def test_itinerary_missing_session_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    r = client.get(
        f"/reports/itinerary?session_id={uuid.uuid4()}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404


def test_itinerary_invalid_session_id_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/itinerary?session_id=not-a-uuid",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404
