"""Tests for the team-invite HTTP surface."""

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

from schemas.storage import Base  # noqa: E402
from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse import verification as _verif  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def _fresh_db(tmp_path):
    db_path = tmp_path / "voyagent-invites-test.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)

    get_auth_settings.cache_clear()
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())
    _verif.set_password_reset_token_store_for_test(
        _verif.NullVerificationTokenStore()
    )
    _verif.set_verification_token_store_for_test(
        _verif.NullVerificationTokenStore()
    )

    yield

    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    _verif.set_password_reset_token_store_for_test(None)
    _verif.set_verification_token_store_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_PW = "Sup3rSecretValue!"


def _sign_up(client: TestClient, *, email: str, agency: str = "Acme") -> dict:
    r = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": _PW,
            "full_name": f"U {email}",
            "agency_name": agency,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_invite_requires_admin(client: TestClient) -> None:
    r = client.post(
        "/auth/invites", json={"email": "bob@acme.test", "role": "agent"}
    )
    assert r.status_code == 401


def test_create_invite_happy_path(client: TestClient) -> None:
    owner = _sign_up(client, email="owner@a.com", agency="A")
    r = client.post(
        "/auth/invites",
        json={"email": "bob@a.com", "role": "agent"},
        headers=_auth(owner["access_token"]),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["invite"]["email"] == "bob@a.com"
    assert body["invite"]["role"] == "agent"
    assert body["invite"]["status"] == "pending"
    assert body["invite_link"].startswith(
        "https://voyagent.globusdemos.com/app/accept-invite?token="
    )


def test_create_invite_duplicate_returns_409(client: TestClient) -> None:
    owner = _sign_up(client, email="owner@a.com", agency="A")
    h = _auth(owner["access_token"])
    r1 = client.post(
        "/auth/invites", json={"email": "bob@a.com", "role": "agent"}, headers=h
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/auth/invites", json={"email": "bob@a.com", "role": "agent"}, headers=h
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "invite_already_exists"


def test_create_invite_invalid_role_422(client: TestClient) -> None:
    owner = _sign_up(client, email="owner@a.com", agency="A")
    r = client.post(
        "/auth/invites",
        json={"email": "bob@a.com", "role": "god"},
        headers=_auth(owner["access_token"]),
    )
    assert r.status_code == 422


def test_list_invites_admin_only(client: TestClient) -> None:
    owner = _sign_up(client, email="owner@a.com", agency="A")
    client.post(
        "/auth/invites",
        json={"email": "b1@a.com", "role": "agent"},
        headers=_auth(owner["access_token"]),
    )
    client.post(
        "/auth/invites",
        json={"email": "b2@a.com", "role": "viewer"},
        headers=_auth(owner["access_token"]),
    )
    r = client.get(
        "/auth/invites?status=pending", headers=_auth(owner["access_token"])
    )
    assert r.status_code == 200
    emails = {i["email"] for i in r.json()["items"]}
    assert emails == {"b1@a.com", "b2@a.com"}


def test_revoke_invite(client: TestClient) -> None:
    owner = _sign_up(client, email="owner@a.com", agency="A")
    h = _auth(owner["access_token"])
    created = client.post(
        "/auth/invites",
        json={"email": "bob@a.com", "role": "agent"},
        headers=h,
    ).json()
    inv_id = created["invite"]["id"]

    r = client.post(f"/auth/invites/{inv_id}/revoke", headers=h)
    assert r.status_code == 200
    assert r.json()["invite"]["status"] == "revoked"

    # Second call is 409 — no longer pending.
    r2 = client.post(f"/auth/invites/{inv_id}/revoke", headers=h)
    assert r2.status_code == 409


def test_lookup_and_accept_invite(client: TestClient) -> None:
    owner = _sign_up(client, email="owner@a.com", agency="Acme Travel")
    h = _auth(owner["access_token"])
    created = client.post(
        "/auth/invites",
        json={"email": "bob@a.com", "role": "agent"},
        headers=h,
    ).json()
    link = created["invite_link"]
    token = link.split("token=", 1)[1]

    # Lookup is public and returns safe metadata only.
    r = client.get(f"/auth/invites/lookup?token={token}")
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["email"] == "bob@a.com"
    assert meta["tenant_name"] == "Acme Travel"
    assert meta["inviter_email"] == "owner@a.com"
    assert "token_hash" not in meta

    # Accept the invite — creates a new user in the SAME tenant.
    r_acc = client.post(
        "/auth/accept-invite",
        json={"token": token, "password": _PW, "full_name": "Bob"},
    )
    assert r_acc.status_code == 201, r_acc.text
    payload = r_acc.json()
    assert payload["user"]["email"] == "bob@a.com"
    assert payload["user"]["role"] == "agent"
    # Critical contract: same tenant, not a new one.
    assert payload["user"]["tenant_id"] == owner["user"]["tenant_id"]
    assert payload["user"]["tenant_name"] == "Acme Travel"

    # Token is single-use.
    r2 = client.post(
        "/auth/accept-invite",
        json={"token": token, "password": _PW, "full_name": "Bob"},
    )
    assert r2.status_code == 400


def test_accept_invite_bad_token(client: TestClient) -> None:
    r = client.post(
        "/auth/accept-invite",
        json={"token": "not-a-real-token", "password": _PW, "full_name": "X"},
    )
    assert r.status_code == 404


def test_invite_admin_only_non_admin_403(client: TestClient) -> None:
    # Owner creates an invite for Bob; Bob accepts and becomes an "agent".
    owner = _sign_up(client, email="owner@a.com", agency="A")
    created = client.post(
        "/auth/invites",
        json={"email": "bob@a.com", "role": "agent"},
        headers=_auth(owner["access_token"]),
    ).json()
    token = created["invite_link"].split("token=", 1)[1]
    accepted = client.post(
        "/auth/accept-invite",
        json={"token": token, "password": _PW, "full_name": "Bob"},
    ).json()
    bob_token = accepted["access_token"]

    # Bob tries to create an invite — must be forbidden.
    r = client.post(
        "/auth/invites",
        json={"email": "carol@a.com", "role": "agent"},
        headers=_auth(bob_token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden_role"

    # Bob also can't list invites.
    r2 = client.get("/auth/invites", headers=_auth(bob_token))
    assert r2.status_code == 403
