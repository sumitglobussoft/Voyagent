"""Tests for the advanced search query params on GET /enquiries.

Extends the existing ``test_enquiries.py`` coverage — this file only
exercises the new filter params added in wave 2 (customer_email,
destination, origin, depart_from/to, created_from/to).
"""

from __future__ import annotations

import os

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

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(client: TestClient, token: str, **overrides) -> dict:
    body = {
        "customer_name": "Default Customer",
        "customer_email": "default@example.com",
        "customer_phone": "+91-90000-00000",
        "origin": "DEL",
        "destination": "DXB",
        "depart_date": "2026-07-01",
        "return_date": "2026-07-10",
        "pax_count": 2,
        "budget_amount": "80000.00",
        "budget_currency": "INR",
    }
    body.update(overrides)
    r = client.post("/enquiries", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #


def test_list_advanced_search_requires_auth(client: TestClient) -> None:
    r = client.get("/enquiries?customer_email=foo")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Filter each new param                                                       #
# --------------------------------------------------------------------------- #


def test_filter_customer_email(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tok = signup["access_token"]
    _create(client, tok, customer_name="X1", customer_email="priya@example.com")
    _create(client, tok, customer_name="X2", customer_email="rahul@example.com")
    _create(client, tok, customer_name="X3", customer_email="priyanka@other.io")

    r = client.get(
        "/enquiries?customer_email=priya",
        headers=_auth(tok),
    )
    assert r.status_code == 200
    body = r.json()
    # Matches "priya@..." and "priyanka@..." (substring).
    assert body["total"] == 2


def test_filter_destination(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tok = signup["access_token"]
    _create(client, tok, customer_name="X1", destination="Dubai")
    _create(client, tok, customer_name="X2", destination="Paris")
    _create(client, tok, customer_name="X3", destination="Dublin")

    r = client.get("/enquiries?destination=du", headers=_auth(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    names = {i["customer_name"] for i in body["items"]}
    assert names == {"X1", "X3"}


def test_filter_origin(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tok = signup["access_token"]
    _create(client, tok, customer_name="X1", origin="DEL")
    _create(client, tok, customer_name="X2", origin="BOM")

    r = client.get("/enquiries?origin=DEL", headers=_auth(tok))
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_filter_depart_date_range(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tok = signup["access_token"]
    _create(
        client,
        tok,
        customer_name="X1",
        depart_date="2026-06-01",
        return_date="2026-06-10",
    )
    _create(
        client,
        tok,
        customer_name="X2",
        depart_date="2026-07-15",
        return_date="2026-07-20",
    )
    _create(
        client,
        tok,
        customer_name="X3",
        depart_date="2026-08-20",
        return_date="2026-08-25",
    )

    r = client.get(
        "/enquiries?depart_from=2026-07-01&depart_to=2026-07-31",
        headers=_auth(tok),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["customer_name"] == "X2"


def test_filter_created_range(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tok = signup["access_token"]
    _create(client, tok, customer_name="X1")

    # Today is 2026-04-14 in fixture config, but we just filter loose
    # around the actual row timestamps by using a wide range that will
    # always match.
    r_match = client.get(
        "/enquiries?created_from=2020-01-01&created_to=2099-12-31",
        headers=_auth(tok),
    )
    assert r_match.status_code == 200
    assert r_match.json()["total"] == 1

    # Range that excludes everything.
    r_none = client.get(
        "/enquiries?created_from=2000-01-01&created_to=2000-01-02",
        headers=_auth(tok),
    )
    assert r_none.status_code == 200
    assert r_none.json()["total"] == 0


def test_filter_combined_and_semantics(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tok = signup["access_token"]
    _create(
        client,
        tok,
        customer_name="X1",
        customer_email="priya@example.com",
        destination="Dubai",
    )
    _create(
        client,
        tok,
        customer_name="X2",
        customer_email="priya@example.com",
        destination="Paris",
    )
    _create(
        client,
        tok,
        customer_name="X3",
        customer_email="rahul@example.com",
        destination="Dubai",
    )

    r = client.get(
        "/enquiries?customer_email=priya&destination=Dubai",
        headers=_auth(tok),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["customer_name"] == "X1"


def test_depart_range_inverted_returns_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get(
        "/enquiries?depart_from=2026-08-01&depart_to=2026-07-01",
        headers=_auth(signup["access_token"]),
    )
    assert r.status_code == 422


def test_created_range_inverted_returns_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get(
        "/enquiries?created_from=2026-08-01&created_to=2026-07-01",
        headers=_auth(signup["access_token"]),
    )
    assert r.status_code == 422


def test_filter_tenant_isolation(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")

    _create(
        client,
        a["access_token"],
        customer_name="A-1",
        customer_email="shared@example.com",
    )
    _create(
        client,
        b["access_token"],
        customer_name="B-1",
        customer_email="shared@example.com",
    )

    r_a = client.get(
        "/enquiries?customer_email=shared",
        headers=_auth(a["access_token"]),
    )
    body_a = r_a.json()
    assert body_a["total"] == 1
    assert body_a["items"][0]["customer_name"] == "A-1"

    r_b = client.get(
        "/enquiries?customer_email=shared",
        headers=_auth(b["access_token"]),
    )
    body_b = r_b.json()
    assert body_b["total"] == 1
    assert body_b["items"][0]["customer_name"] == "B-1"
