"""Tests for ``PATCH /auth/profile``."""

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
    db_path = tmp_path / "voyagent-profile-test.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)
    get_auth_settings.cache_clear()
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())
    _verif.set_verification_token_store_for_test(
        _verif.NullVerificationTokenStore()
    )
    _verif.set_password_reset_token_store_for_test(
        _verif.NullVerificationTokenStore()
    )
    yield
    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    _verif.set_verification_token_store_for_test(None)
    _verif.set_password_reset_token_store_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_PW = "Sup3rSecretValue!"


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


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_patch_profile_requires_auth(client: TestClient) -> None:
    r = client.patch("/auth/profile", json={"full_name": "Bob"})
    assert r.status_code == 401


def test_patch_profile_full_name(client: TestClient) -> None:
    me = _sign_up(client, "alice@a.com")
    r = client.patch(
        "/auth/profile",
        json={"full_name": "Alice Wonderland"},
        headers=_auth(me["access_token"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["full_name"] == "Alice Wonderland"
    assert body["email_verification_required"] is False


def test_patch_profile_email_change_flips_verified(client: TestClient) -> None:
    me = _sign_up(client, "alice@a.com")
    assert me["user"]["email_verified"] is True
    r = client.patch(
        "/auth/profile",
        json={"email": "alice2@a.com"},
        headers=_auth(me["access_token"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "alice2@a.com"
    assert body["user"]["email_verified"] is False
    assert body["email_verification_required"] is True


def test_patch_profile_same_email_is_noop(client: TestClient) -> None:
    me = _sign_up(client, "alice@a.com")
    r = client.patch(
        "/auth/profile",
        json={"email": "alice@a.com"},
        headers=_auth(me["access_token"]),
    )
    assert r.status_code == 200
    assert r.json()["email_verification_required"] is False


def test_patch_profile_email_collision_409(client: TestClient) -> None:
    _sign_up(client, "taken@a.com")
    me = _sign_up(client, "alice@a.com")
    r = client.patch(
        "/auth/profile",
        json={"email": "taken@a.com"},
        headers=_auth(me["access_token"]),
    )
    assert r.status_code == 409


def test_patch_profile_rejects_extra_fields(client: TestClient) -> None:
    me = _sign_up(client, "alice@a.com")
    r = client.patch(
        "/auth/profile",
        json={"role": "agency_admin"},
        headers=_auth(me["access_token"]),
    )
    assert r.status_code == 422


def test_patch_profile_blank_full_name_422(client: TestClient) -> None:
    me = _sign_up(client, "alice@a.com")
    r = client.patch(
        "/auth/profile",
        json={"full_name": "   "},
        headers=_auth(me["access_token"]),
    )
    assert r.status_code == 422
