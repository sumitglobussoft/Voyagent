"""Error-path tests for the in-house auth subsystem.

Complements ``test_auth_inhouse.py``, which covers the happy path plus
a handful of obvious failures. This file fills in the gaps:

  * duplicate email -> 409
  * invalid email   -> 422 (pydantic validation)
  * expired refresh token -> 401
  * revoked refresh token -> 401
  * /me with a revoked jti -> 401
  * /me with a foreign-secret JWT -> 401
  * disabled-user sign-in -> flagged as ``xfail`` (see docstring below)
  * concurrent sign-in issues two independent, valid token pairs
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

# Set the auth secret BEFORE importing voyagent_api modules — pydantic
# settings are lru-cached on first access.
os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, update  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base, RefreshTokenRow, User  # noqa: E402

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.auth_inhouse.tokens import hash_refresh_token  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures (parallel to tests/api/test_auth_inhouse.py)                       #
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

    yield sm

    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
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


def test_sign_up_duplicate_email_in_same_tenant_returns_409(
    client: TestClient,
) -> None:
    r1 = client.post("/auth/sign-up", json=_SIGNUP_BODY)
    assert r1.status_code == 201, r1.text
    r2 = client.post("/auth/sign-up", json=_SIGNUP_BODY)
    assert r2.status_code == 409
    assert r2.json()["detail"] == "email_already_registered"


def test_sign_up_with_invalid_email_returns_422(client: TestClient) -> None:
    body = {**_SIGNUP_BODY, "email": "not-an-email"}
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 422
    # pydantic attaches a structured error list under "detail".
    body = r.json()
    assert isinstance(body.get("detail"), list)


# --------------------------------------------------------------------------- #
# Sign-in — disabled user                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    reason=(
        "The ``email_verified`` column exists on the User row but the "
        "sign-in service does not currently gate on it, so a disabled / "
        "unverified user can still sign in. Once AuthService.sign_in "
        "enforces the flag this test should pass."
    ),
    strict=False,
)
async def test_sign_in_with_unverified_user_is_rejected(
    client: TestClient, _fresh_db
) -> None:
    client.post("/auth/sign-up", json=_SIGNUP_BODY)

    # Force the user into an unverified state directly on the DB.
    sm = _fresh_db
    async with sm() as session:
        await session.execute(
            update(User)
            .where(User.email == "alice@example.com")
            .values(email_verified=False)
        )
        await session.commit()

    r = client.post(
        "/auth/sign-in",
        json={"email": "alice@example.com", "password": _VALID_PASSWORD},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Refresh errors                                                              #
# --------------------------------------------------------------------------- #


async def test_refresh_with_expired_token_returns_401(
    client: TestClient, _fresh_db
) -> None:
    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    refresh_token = signup["refresh_token"]

    # Fast-forward the row's expires_at to the past.
    digest = hash_refresh_token(refresh_token)
    sm = _fresh_db
    async with sm() as session:
        await session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.token_hash == digest)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        await session.commit()

    r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_refresh_token"


async def test_refresh_with_revoked_token_returns_401(
    client: TestClient, _fresh_db
) -> None:
    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    refresh_token = signup["refresh_token"]

    digest = hash_refresh_token(refresh_token)
    sm = _fresh_db
    async with sm() as session:
        await session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.token_hash == digest)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await session.commit()

    r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# /me with a revoked jti                                                      #
# --------------------------------------------------------------------------- #


async def test_me_with_revoked_jti_returns_401(client: TestClient) -> None:
    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    access = signup["access_token"]

    # Decode locally to pull the jti and expiry.
    settings = get_auth_settings()
    decoded = jwt.decode(
        access,
        settings.secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.audience,
        issuer=settings.issuer,
    )
    jti = decoded["jti"]
    exp = int(decoded["exp"])

    # Install a denylist entry for this jti.
    rev_list = revocation.NullRevocationList()
    await rev_list.revoke(jti, exp)
    revocation.set_revocation_list_for_test(rev_list)

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# /me with a JWT signed by a different secret                                 #
# --------------------------------------------------------------------------- #


def test_me_with_foreign_secret_jwt_returns_401(client: TestClient) -> None:
    settings = get_auth_settings()
    # Mint a JWT locally with the wrong secret but otherwise plausible claims.
    payload = {
        "sub": "00000000-0000-7000-8000-000000000001",
        "tid": "00000000-0000-7000-8000-000000000002",
        "role": "agency_admin",
        "email": "alice@example.com",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
        "jti": "00000000000000000000000000000000",
        "iss": settings.issuer,
        "aud": settings.audience,
    }
    bad = jwt.encode(payload, "totally-different-secret", algorithm="HS256")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Concurrent sign-in — two token pairs, both valid, neither invalidates       #
# --------------------------------------------------------------------------- #


def test_concurrent_sign_in_yields_two_independent_valid_token_pairs(
    client: TestClient,
) -> None:
    """Existing behaviour: sign-in appends a fresh refresh-token row each
    time; refresh rotation is per-token, not per-user. Two sign-ins should
    therefore produce two independent, concurrently-valid pairs.

    NOTE: if Voyagent later enforces single-session rotation this test
    should be rewritten to assert the stricter contract. Picking the
    stricter interpretation today would contradict the implementation.
    """
    client.post("/auth/sign-up", json=_SIGNUP_BODY).raise_for_status()

    first = client.post(
        "/auth/sign-in",
        json={"email": "alice@example.com", "password": _VALID_PASSWORD},
    )
    second = client.post(
        "/auth/sign-in",
        json={"email": "alice@example.com", "password": _VALID_PASSWORD},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    a = first.json()
    b = second.json()
    assert a["refresh_token"] != b["refresh_token"]
    assert a["access_token"] != b["access_token"]

    # Both access tokens independently authorise /me.
    r1 = client.get("/auth/me", headers={"Authorization": f"Bearer {a['access_token']}"})
    r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {b['access_token']}"})
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Both refresh tokens can be redeemed independently.
    r1 = client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    r2 = client.post("/auth/refresh", json={"refresh_token": b["refresh_token"]})
    assert r1.status_code == 200
    assert r2.status_code == 200
