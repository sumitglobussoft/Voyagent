"""Tests for the /api/enquiries HTTP surface."""

from __future__ import annotations

import os
import uuid
from datetime import date

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


_BASE_PAYLOAD = {
    "customer_name": "Alice Customer",
    "customer_email": "alice@example.com",
    "customer_phone": "+91-90000-00000",
    "origin": "DEL",
    "destination": "DXB",
    "depart_date": "2026-07-01",
    "return_date": "2026-07-10",
    "pax_count": 2,
    "budget_amount": "80000.00",
    "budget_currency": "INR",
    "notes": "Honeymoon trip",
}


def _create(
    client: TestClient,
    token: str,
    *,
    overrides: dict | None = None,
) -> dict:
    body = {**_BASE_PAYLOAD, **(overrides or {})}
    r = client.post(
        "/enquiries",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #


def test_list_requires_auth(client: TestClient) -> None:
    r = client.get("/enquiries")
    assert r.status_code == 401


def test_post_requires_auth(client: TestClient) -> None:
    r = client.post("/enquiries", json=_BASE_PAYLOAD)
    assert r.status_code == 401


def test_get_one_requires_auth(client: TestClient) -> None:
    r = client.get(f"/enquiries/{uuid.uuid4()}")
    assert r.status_code == 401


def test_patch_requires_auth(client: TestClient) -> None:
    r = client.patch(
        f"/enquiries/{uuid.uuid4()}", json={"customer_name": "X"}
    )
    assert r.status_code == 401


def test_promote_requires_auth(client: TestClient) -> None:
    r = client.post(
        f"/enquiries/{uuid.uuid4()}/promote-to-session",
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Create                                                                      #
# --------------------------------------------------------------------------- #


def test_create_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Tenant A")
    created = _create(client, signup["access_token"])
    assert created["customer_name"] == "Alice Customer"
    assert created["tenant_id"] == signup["user"]["tenant_id"]
    assert created["created_by_user_id"] == signup["user"]["id"]
    assert created["status"] == "new"
    assert created["pax_count"] == 2
    assert created["budget_amount"] == "80000.00"
    assert created["id"]


def test_create_rejects_invalid_currency(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/enquiries",
        json={**_BASE_PAYLOAD, "budget_currency": "usd"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_currency"


def test_create_rejects_invalid_date_range(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/enquiries",
        json={
            **_BASE_PAYLOAD,
            "depart_date": "2026-07-10",
            "return_date": "2026-07-01",
        },
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_date_range"


def test_create_rejects_invalid_pax_count(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/enquiries",
        json={**_BASE_PAYLOAD, "pax_count": 0},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_pax_count"


def test_create_rejects_unknown_field_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/enquiries",
        json={**_BASE_PAYLOAD, "tenant_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


def test_create_rejects_empty_customer_name(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.post(
        "/enquiries",
        json={**_BASE_PAYLOAD, "customer_name": ""},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# List                                                                        #
# --------------------------------------------------------------------------- #


def test_list_shows_tenant_enquiries(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    _create(client, token, overrides={"customer_name": "Alpha"})
    _create(client, token, overrides={"customer_name": "Beta"})
    r = client.get(
        "/enquiries",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    names = {i["customer_name"] for i in body["items"]}
    assert names == {"Alpha", "Beta"}


def test_list_tenant_isolation(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    _create(client, a["access_token"], overrides={"customer_name": "A-only"})
    _create(client, b["access_token"], overrides={"customer_name": "B-only"})

    r_a = client.get(
        "/enquiries",
        headers={"Authorization": f"Bearer {a['access_token']}"},
    )
    names_a = {i["customer_name"] for i in r_a.json()["items"]}
    assert names_a == {"A-only"}


def test_list_filters_by_status(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token, overrides={"customer_name": "Alpha"})
    # Promote one to 'quoted'.
    r_patch = client.patch(
        f"/enquiries/{created['id']}",
        json={"status": "quoted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_patch.status_code == 200
    _create(client, token, overrides={"customer_name": "Beta"})

    r = client.get(
        "/enquiries?status=quoted",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["customer_name"] == "Alpha"


def test_list_search_q_is_case_insensitive(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    _create(
        client,
        token,
        overrides={"customer_name": "Raj Malhotra", "destination": "DXB"},
    )
    _create(
        client,
        token,
        overrides={"customer_name": "Priya Iyer", "destination": "BKK"},
    )

    r = client.get(
        "/enquiries?q=MALHOTRA",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["customer_name"] == "Raj Malhotra"

    # Match in destination too.
    r2 = client.get(
        "/enquiries?q=bkk",
        headers={"Authorization": f"Bearer {token}"},
    )
    items2 = r2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["customer_name"] == "Priya Iyer"


# --------------------------------------------------------------------------- #
# Get one                                                                     #
# --------------------------------------------------------------------------- #


def test_get_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)

    r = client.get(
        f"/enquiries/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_cross_tenant_returns_404(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    created = _create(client, a["access_token"])

    r = client.get(
        f"/enquiries/{created['id']}",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "enquiry_not_found"


def test_get_invalid_uuid_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get(
        "/enquiries/not-a-uuid",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404


def test_get_unknown_uuid_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.get(
        f"/enquiries/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Patch                                                                       #
# --------------------------------------------------------------------------- #


def test_patch_partial_update_leaves_omitted_alone(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)

    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"customer_name": "Alice New"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["customer_name"] == "Alice New"
    # Other fields unchanged.
    assert body["customer_email"] == "alice@example.com"
    assert body["destination"] == "DXB"


def test_patch_explicit_null_clears_nullable_field(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)

    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"customer_email": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["customer_email"] is None


def test_patch_rejects_cancelled_to_open_transition(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)

    # Move to cancelled (terminal).
    r_cancel = client.patch(
        f"/enquiries/{created['id']}",
        json={"status": "cancelled"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "cancelled"

    # Attempt to reopen to 'new' — forbidden.
    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"status": "new"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_status_transition"


def test_patch_rejects_booked_to_open_transition(client: TestClient) -> None:
    signup = _sign_up(client, email="bob@b.com", agency="B")
    token = signup["access_token"]
    created = _create(client, token, overrides={"customer_name": "Second"})

    # Move to booked (terminal).
    r_book = client.patch(
        f"/enquiries/{created['id']}",
        json={"status": "booked"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_book.status_code == 200
    assert r_book.json()["status"] == "booked"

    # Attempt to revert to 'quoted' — forbidden.
    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"status": "quoted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_status_transition"


def test_patch_cross_tenant_returns_404(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    created = _create(client, a["access_token"])

    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"customer_name": "sneaky"},
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404


def test_patch_validates_currency(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)
    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"budget_currency": "eur"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_currency"


def test_patch_validates_pax(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)
    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"pax_count": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_pax_count"


def test_patch_validates_date_range_cross_field(client: TestClient) -> None:
    """Cross-field validation considers the *post-patch* state."""
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)  # depart 2026-07-01, return 2026-07-10

    # Patch only depart so return_date < depart_date after merging.
    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"depart_date": "2026-08-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_date_range"


def test_patch_unknown_field_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)
    r = client.patch(
        f"/enquiries/{created['id']}",
        json={"not_a_real_field": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Promote                                                                     #
# --------------------------------------------------------------------------- #


def test_promote_creates_session_and_writes_link(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)

    r = client.post(
        f"/enquiries/{created['id']}/promote-to-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"]
    assert body["enquiry"]["session_id"] == body["session_id"]


def test_promote_is_idempotent(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = signup["access_token"]
    created = _create(client, token)

    r1 = client.post(
        f"/enquiries/{created['id']}/promote-to-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    sid_1 = r1.json()["session_id"]

    r2 = client.post(
        f"/enquiries/{created['id']}/promote-to-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    sid_2 = r2.json()["session_id"]

    assert sid_1 == sid_2


def test_promote_cross_tenant_returns_404(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    created = _create(client, a["access_token"])

    r = client.post(
        f"/enquiries/{created['id']}/promote-to-session",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404


# Date quoted to silence an "unused import" lint on debug iterations.
_ = date
