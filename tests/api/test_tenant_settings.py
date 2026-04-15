"""Tests for the /tenant-settings HTTP surface."""

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
from voyagent_api.auth_inhouse.repository import UserRepository  # noqa: E402
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


async def _demote_to_agent(email: str) -> None:
    """Demote a just-signed-up user from agency_admin → agent."""
    from schemas.storage import User, UserRole
    from sqlalchemy import update

    sm = db_module.get_sessionmaker()
    async with sm() as db:
        async with db.begin():
            await db.execute(
                update(User)
                .where(User.email == email)
                .values(role=UserRole.AGENT)
            )


def test_get_requires_auth(client: TestClient) -> None:
    r = client.get("/tenant-settings")
    assert r.status_code == 401


def test_patch_requires_auth(client: TestClient) -> None:
    r = client.patch("/tenant-settings", json={"model": "claude-sonnet-4-5"})
    assert r.status_code == 401


def test_get_returns_default_row_for_fresh_tenant(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Agency A")
    r = client.get(
        "/tenant-settings",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == signup["user"]["tenant_id"]
    assert body["model"] is None
    assert body["system_prompt_suffix"] is None
    assert body["rate_limit_per_minute"] == 60
    assert body["rate_limit_per_hour"] == 1000
    assert body["daily_token_budget"] is None
    assert body["locale"] == "en"
    assert body["timezone"] == "UTC"
    assert body["default_currency"] == "INR"


def test_patch_updates_specific_fields(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Agency A")
    token = signup["access_token"]

    r = client.patch(
        "/tenant-settings",
        json={
            "model": "claude-haiku-4-5-20251001",
            "system_prompt_suffix": "Quote in INR.",
            "locale": "hi",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert body["system_prompt_suffix"] == "Quote in INR."
    assert body["locale"] == "hi"
    # Untouched fields keep defaults.
    assert body["rate_limit_per_minute"] == 60

    # A second PATCH that only touches rate limit must leave model alone.
    r = client.patch(
        "/tenant-settings",
        json={"rate_limit_per_minute": 120},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["rate_limit_per_minute"] == 120
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert body["system_prompt_suffix"] == "Quote in INR."


def test_patch_rejects_invalid_model(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        "/tenant-settings",
        json={"model": "claude-does-not-exist"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


def test_patch_rejects_invalid_currency(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        "/tenant-settings",
        json={"default_currency": "usd"},  # lowercase → reject
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


def test_patch_rejects_invalid_locale(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        "/tenant-settings",
        json={"locale": "fr"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


def test_patch_rejects_negative_budget(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        "/tenant-settings",
        json={"daily_token_budget": -1},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


def test_patch_non_admin_is_forbidden(client: TestClient) -> None:
    import asyncio

    signup = _sign_up(client, email="alice@a.com", agency="A")
    asyncio.get_event_loop().run_until_complete(
        _demote_to_agent("alice@a.com")
    )
    # Re-sign in to get a fresh token with the downgraded role.
    r = client.post(
        "/auth/sign-in",
        json={"email": "alice@a.com", "password": _PASSWORD},
    )
    assert r.status_code == 200, r.text
    agent_token = r.json()["access_token"]

    # GET is still allowed (role-agnostic).
    r = client.get(
        "/tenant-settings",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert r.status_code == 200

    # PATCH must be refused.
    r = client.patch(
        "/tenant-settings",
        json={"model": "claude-sonnet-4-5"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert r.status_code == 403


def test_tenant_isolation(client: TestClient) -> None:
    s_a = _sign_up(client, email="alice@a.com", agency="Agency A")
    s_b = _sign_up(client, email="bob@b.com", agency="Agency B")

    # A writes settings.
    r = client.patch(
        "/tenant-settings",
        json={"model": "claude-opus-4-6", "system_prompt_suffix": "A-only"},
        headers={"Authorization": f"Bearer {s_a['access_token']}"},
    )
    assert r.status_code == 200

    # B must see its own defaults, not A's row.
    r = client.get(
        "/tenant-settings",
        headers={"Authorization": f"Bearer {s_b['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == s_b["user"]["tenant_id"]
    assert body["model"] is None
    assert body["system_prompt_suffix"] is None
