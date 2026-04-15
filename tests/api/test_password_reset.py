"""Tests for the password-reset flow."""

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
    db_path = tmp_path / "voyagent-pwreset-test.sqlite"
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
_NEW_PW = "Br4ndNewPassword!!"


def _sign_up(client: TestClient, email: str) -> dict:
    r = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": _PW,
            "full_name": "Alice",
            "agency_name": "Acme",
        },
    )
    assert r.status_code == 201
    return r.json()


def test_request_reset_unknown_email_still_200(client: TestClient) -> None:
    r = client.post(
        "/auth/request-password-reset", json={"email": "ghost@a.com"}
    )
    assert r.status_code == 200
    assert r.json()["queued"] is True
    # Bypass flag is on — but no user, so no debug token either.
    assert r.json()["debug_token"] is None


def test_request_reset_known_email_returns_debug_token(
    client: TestClient,
) -> None:
    _sign_up(client, "alice@a.com")
    r = client.post(
        "/auth/request-password-reset", json={"email": "alice@a.com"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["queued"] is True
    assert isinstance(body["debug_token"], str)
    assert len(body["debug_token"]) >= 20


def test_reset_password_happy_path_and_revokes_sessions(
    client: TestClient,
) -> None:
    me = _sign_up(client, "alice@a.com")
    old_refresh = me["refresh_token"]
    r_req = client.post(
        "/auth/request-password-reset", json={"email": "alice@a.com"}
    )
    token = r_req.json()["debug_token"]

    r = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": _NEW_PW},
    )
    assert r.status_code == 200
    assert r.json()["reset"] is True

    # Old refresh token has been invalidated.
    r_refresh = client.post(
        "/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert r_refresh.status_code == 401

    # Old password no longer works.
    r_old = client.post(
        "/auth/sign-in", json={"email": "alice@a.com", "password": _PW}
    )
    assert r_old.status_code == 401

    # New password works.
    r_new = client.post(
        "/auth/sign-in",
        json={"email": "alice@a.com", "password": _NEW_PW},
    )
    assert r_new.status_code == 200, r_new.text


def test_reset_password_invalid_token_400(client: TestClient) -> None:
    r = client.post(
        "/auth/reset-password",
        json={"token": "garbage", "new_password": _NEW_PW},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "token_invalid"


def test_reset_password_token_single_use(client: TestClient) -> None:
    _sign_up(client, "alice@a.com")
    token = (
        client.post(
            "/auth/request-password-reset", json={"email": "alice@a.com"}
        )
        .json()["debug_token"]
    )
    r1 = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": _NEW_PW},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": _NEW_PW},
    )
    assert r2.status_code == 400


def test_reset_password_rejects_weak(client: TestClient) -> None:
    _sign_up(client, "alice@a.com")
    token = (
        client.post(
            "/auth/request-password-reset", json={"email": "alice@a.com"}
        )
        .json()["debug_token"]
    )
    r = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "short"},
    )
    assert r.status_code == 422
