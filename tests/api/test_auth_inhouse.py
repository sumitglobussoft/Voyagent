"""Tests for the in-house auth subsystem.

Uses ``sqlite+aiosqlite`` so the suite runs without a Postgres
instance. Each test gets a brand-new in-memory database; the schema
is created via ``Base.metadata.create_all`` rather than Alembic
because we only need the table shapes here.
"""

from __future__ import annotations

import os

import pytest

# Set the auth secret BEFORE importing voyagent_api modules — pydantic
# settings are lru-cached on first access.
os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base  # noqa: E402

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api.auth_inhouse.passwords import hash_password  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.auth_inhouse.tokens import issue_access_token  # noqa: E402
from voyagent_api.main import app  # noqa: E402
from voyagent_api import revocation  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
async def _fresh_db() -> None:
    """Spin up an isolated SQLite DB and wire it into the API."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)

    # Clear cached settings + revocation list so each test sees a fresh
    # in-memory denylist.
    get_auth_settings.cache_clear()
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())

    yield

    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
    """Return a fresh FastAPI test client."""
    return TestClient(app)


_VALID_PASSWORD = "Sup3rSecretValue!"
_SIGNUP_BODY = {
    "email": "alice@example.com",
    "password": _VALID_PASSWORD,
    "full_name": "Alice Example",
    "agency_name": "Example Travel",
}


# --------------------------------------------------------------------------- #
# Sign-up                                                                     #
# --------------------------------------------------------------------------- #


def test_sign_up_creates_user_and_tenant(client: TestClient) -> None:
    r = client.post("/auth/sign-up", json=_SIGNUP_BODY)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0
    user = body["user"]
    assert user["email"] == "alice@example.com"
    assert user["full_name"] == "Alice Example"
    assert user["tenant_name"] == "Example Travel"
    assert user["id"]
    assert user["tenant_id"]


def test_sign_up_rejects_duplicate_email_with_409(client: TestClient) -> None:
    r1 = client.post("/auth/sign-up", json=_SIGNUP_BODY)
    assert r1.status_code == 201
    r2 = client.post("/auth/sign-up", json=_SIGNUP_BODY)
    assert r2.status_code == 409
    assert r2.json()["detail"] == "email_already_registered"


def test_sign_up_rejects_short_password_with_422(client: TestClient) -> None:
    body = {**_SIGNUP_BODY, "password": "short1A"}
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Sign-in                                                                     #
# --------------------------------------------------------------------------- #


def test_sign_in_with_correct_credentials_returns_tokens(client: TestClient) -> None:
    client.post("/auth/sign-up", json=_SIGNUP_BODY)
    r = client.post(
        "/auth/sign-in",
        json={"email": "alice@example.com", "password": _VALID_PASSWORD},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "alice@example.com"


def test_sign_in_with_wrong_password_returns_401(client: TestClient) -> None:
    client.post("/auth/sign-up", json=_SIGNUP_BODY)
    r = client.post(
        "/auth/sign-in",
        json={"email": "alice@example.com", "password": "WrongPassword123"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


def test_sign_in_with_unknown_email_returns_401(client: TestClient) -> None:
    r = client.post(
        "/auth/sign-in",
        json={"email": "ghost@example.com", "password": _VALID_PASSWORD},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


# --------------------------------------------------------------------------- #
# Refresh                                                                     #
# --------------------------------------------------------------------------- #


def test_refresh_rotates_token_and_revokes_old(client: TestClient) -> None:
    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    old_refresh = signup["refresh_token"]

    r = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200, r.text
    new_pair = r.json()
    assert new_pair["access_token"]
    assert new_pair["refresh_token"] != old_refresh

    # The old refresh token must be dead now.
    replay = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401


def test_refresh_with_revoked_token_returns_401(client: TestClient) -> None:
    r = client.post(
        "/auth/refresh",
        json={"refresh_token": "obviously-not-a-valid-token"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_refresh_token"


# --------------------------------------------------------------------------- #
# /me                                                                         #
# --------------------------------------------------------------------------- #


def test_me_returns_user_for_valid_access_token(client: TestClient) -> None:
    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    access = signup["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["tenant_name"] == "Example Travel"


def test_me_returns_401_for_expired_token(client: TestClient) -> None:
    # Mint a token with a tiny TTL by tweaking settings.
    settings = get_auth_settings()
    object.__setattr__(settings, "access_ttl_seconds", -1)

    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    user_id = signup["user"]["id"]
    tenant_id = signup["user"]["tenant_id"]
    token, _exp, _jti = issue_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="alice@example.com",
        role="agency_admin",
    )

    # restore so other tests aren't affected
    object.__setattr__(settings, "access_ttl_seconds", 3600)

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Sign-out                                                                    #
# --------------------------------------------------------------------------- #


def test_sign_out_revokes_refresh_and_blacklists_jti(client: TestClient) -> None:
    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    access = signup["access_token"]
    refresh = signup["refresh_token"]

    r = client.post(
        "/auth/sign-out",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204

    # Refresh is dead.
    bad = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert bad.status_code == 401

    # Access JTI is on the denylist — /me should now 401.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 401
