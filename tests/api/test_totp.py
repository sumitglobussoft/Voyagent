"""TOTP 2FA endpoint tests.

Covers setup, verify, disable, and the ``/auth/sign-in-totp`` second-
step flow. Uses the same in-memory SQLite fixture as the core auth
tests so the schema comes from ``Base.metadata.create_all``.
"""

from __future__ import annotations

import os

import pyotp
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
from voyagent_api.auth_inhouse import verification as verification_mod  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


_VALID_PASSWORD = "Sup3rSecretValue!"
_SIGNUP_BODY = {
    "email": "totp@example.com",
    "password": _VALID_PASSWORD,
    "full_name": "TOTP User",
    "agency_name": "TOTP Travel",
}


@pytest.fixture(autouse=True)
async def _fresh_db() -> None:
    from sqlalchemy.pool import StaticPool

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
    verification_mod.set_verification_token_store_for_test(
        verification_mod.NullVerificationTokenStore()
    )
    yield
    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    verification_mod.set_verification_token_store_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _sign_up(client: TestClient) -> str:
    r = client.post("/auth/sign-up", json=_SIGNUP_BODY)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_setup_generates_secret_and_verify_enables(client: TestClient) -> None:
    tok = _sign_up(client)

    r = client.post("/auth/totp/setup", headers=_auth(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    secret = body["secret"]
    assert secret
    assert "otpauth://totp/Voyagent" in body["otpauth_url"]

    # Verify with the current code
    code = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/totp/verify", json={"code": code}, headers=_auth(tok)
    )
    assert r.status_code == 200, r.text
    assert r.json()["totp_enabled"] is True


def test_sign_in_returns_totp_required_flag_via_sign_in_totp(
    client: TestClient,
) -> None:
    tok = _sign_up(client)
    r = client.post("/auth/totp/setup", headers=_auth(tok))
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    client.post(
        "/auth/totp/verify", json={"code": code}, headers=_auth(tok)
    )

    # Wrong TOTP code → 401 totp_invalid
    r = client.post(
        "/auth/sign-in-totp",
        json={
            "email": _SIGNUP_BODY["email"],
            "password": _VALID_PASSWORD,
            "totp_code": "000000",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "totp_invalid"


def test_sign_in_totp_with_correct_code_issues_tokens(
    client: TestClient,
) -> None:
    tok = _sign_up(client)
    r = client.post("/auth/totp/setup", headers=_auth(tok))
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    client.post(
        "/auth/totp/verify", json={"code": code}, headers=_auth(tok)
    )

    r = client.post(
        "/auth/sign-in-totp",
        json={
            "email": _SIGNUP_BODY["email"],
            "password": _VALID_PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]
    assert r.json()["refresh_token"]


def test_sign_in_totp_with_bad_password(client: TestClient) -> None:
    tok = _sign_up(client)
    r = client.post("/auth/totp/setup", headers=_auth(tok))
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    client.post(
        "/auth/totp/verify", json={"code": code}, headers=_auth(tok)
    )

    r = client.post(
        "/auth/sign-in-totp",
        json={
            "email": _SIGNUP_BODY["email"],
            "password": "NotTheRightPassword123",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


def test_disable_requires_password_and_code(client: TestClient) -> None:
    tok = _sign_up(client)
    r = client.post("/auth/totp/setup", headers=_auth(tok))
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    client.post(
        "/auth/totp/verify", json={"code": code}, headers=_auth(tok)
    )

    # Wrong password
    r = client.post(
        "/auth/totp/disable",
        json={"password": "WrongPassword1234", "code": pyotp.TOTP(secret).now()},
        headers=_auth(tok),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "invalid_password"

    # Wrong code
    r = client.post(
        "/auth/totp/disable",
        json={"password": _VALID_PASSWORD, "code": "000000"},
        headers=_auth(tok),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "totp_invalid"

    # Correct both
    r = client.post(
        "/auth/totp/disable",
        json={"password": _VALID_PASSWORD, "code": pyotp.TOTP(secret).now()},
        headers=_auth(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["totp_enabled"] is False
