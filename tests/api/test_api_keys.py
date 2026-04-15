"""API key CRUD + verification tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)
os.environ.setdefault("VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", "true")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import ApiKeyRow, Base  # noqa: E402

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse import verification as verification_mod  # noqa: E402
from voyagent_api.auth_inhouse.api_keys import (  # noqa: E402
    hash_api_key,
    parse_api_key,
    resolve_api_key,
)
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


_PASS_A = "Sup3rSecretValue!"
_SIGNUP_A = {
    "email": "a@example.com",
    "password": _PASS_A,
    "full_name": "Agent A",
    "agency_name": "Agency A",
}
_PASS_B = "An0therStrongPass!"
_SIGNUP_B = {
    "email": "b@example.com",
    "password": _PASS_B,
    "full_name": "Agent B",
    "agency_name": "Agency B",
}


@pytest.fixture
def engine_and_sm():  # type: ignore[no-untyped-def]
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    return engine, sm


@pytest.fixture(autouse=True)
async def _fresh_db(engine_and_sm):  # type: ignore[no-untyped-def]
    engine, sm = engine_and_sm
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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


def _sign_up(client: TestClient, body: dict[str, str]) -> str:
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_list_revoke_happy_path(client: TestClient) -> None:
    tok = _sign_up(client, _SIGNUP_A)

    r = client.post(
        "/auth/api-keys", json={"name": "CI key"}, headers=_auth(tok)
    )
    assert r.status_code == 201, r.text
    body = r.json()
    full = body["key"]
    assert full.startswith("vy_")
    assert body["api_key"]["prefix"] in full
    key_id = body["api_key"]["id"]

    # List
    r = client.get("/auth/api-keys", headers=_auth(tok))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "CI key"
    # Plaintext never returned on list.
    assert "key" not in items[0]

    # Revoke
    r = client.post(
        f"/auth/api-keys/{key_id}/revoke", headers=_auth(tok)
    )
    assert r.status_code == 204

    r = client.get("/auth/api-keys", headers=_auth(tok))
    assert r.json()["items"][0]["revoked_at"] is not None


def test_key_format_hash_consistency() -> None:
    full = "vy_abcdefgh_" + ("x" * 32)
    parsed = parse_api_key(full)
    assert parsed == ("abcdefgh", "x" * 32)
    assert len(hash_api_key(full)) == 64


def test_parse_rejects_bad_shapes() -> None:
    assert parse_api_key("notavy") is None
    assert parse_api_key("vy_short_body") is None
    assert parse_api_key("vy_abcdefgh_tooshort") is None


async def test_resolve_api_key_happy(client: TestClient, engine_and_sm):  # type: ignore[no-untyped-def]
    _engine, sm = engine_and_sm
    tok = _sign_up(client, _SIGNUP_A)
    r = client.post(
        "/auth/api-keys", json={"name": "K"}, headers=_auth(tok)
    )
    full = r.json()["key"]

    async with sm() as session:
        principal = await resolve_api_key(session, full)
    assert principal is not None
    assert principal.email == _SIGNUP_A["email"]


async def test_resolve_api_key_rejects_tampered(
    client: TestClient, engine_and_sm
):  # type: ignore[no-untyped-def]
    _engine, sm = engine_and_sm
    tok = _sign_up(client, _SIGNUP_A)
    r = client.post(
        "/auth/api-keys", json={"name": "K"}, headers=_auth(tok)
    )
    full = r.json()["key"]
    # Flip one body char
    tampered = full[:-1] + ("A" if full[-1] != "A" else "B")
    async with sm() as session:
        assert await resolve_api_key(session, tampered) is None


async def test_resolve_api_key_rejects_revoked(
    client: TestClient, engine_and_sm
):  # type: ignore[no-untyped-def]
    _engine, sm = engine_and_sm
    tok = _sign_up(client, _SIGNUP_A)
    r = client.post(
        "/auth/api-keys", json={"name": "K"}, headers=_auth(tok)
    )
    full = r.json()["key"]
    key_id = r.json()["api_key"]["id"]
    client.post(f"/auth/api-keys/{key_id}/revoke", headers=_auth(tok))
    async with sm() as session:
        assert await resolve_api_key(session, full) is None


async def test_resolve_api_key_rejects_expired(
    client: TestClient, engine_and_sm
):  # type: ignore[no-untyped-def]
    _engine, sm = engine_and_sm
    tok = _sign_up(client, _SIGNUP_A)
    r = client.post(
        "/auth/api-keys",
        json={"name": "K", "expires_in_days": 1},
        headers=_auth(tok),
    )
    full = r.json()["key"]
    # Push the expiry into the past.
    async with sm() as session:
        await session.execute(
            update(ApiKeyRow).values(
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
            )
        )
        await session.commit()
    async with sm() as session:
        assert await resolve_api_key(session, full) is None


async def test_last_used_at_updates_on_success(
    client: TestClient, engine_and_sm
):  # type: ignore[no-untyped-def]
    _engine, sm = engine_and_sm
    tok = _sign_up(client, _SIGNUP_A)
    r = client.post(
        "/auth/api-keys", json={"name": "K"}, headers=_auth(tok)
    )
    full = r.json()["key"]
    async with sm() as session:
        await resolve_api_key(session, full)
    r = client.get("/auth/api-keys", headers=_auth(tok))
    assert r.json()["items"][0]["last_used_at"] is not None


def test_tenant_isolation(client: TestClient) -> None:
    tok_a = _sign_up(client, _SIGNUP_A)
    tok_b = _sign_up(client, _SIGNUP_B)

    r = client.post(
        "/auth/api-keys", json={"name": "A key"}, headers=_auth(tok_a)
    )
    assert r.status_code == 201
    a_key_id = r.json()["api_key"]["id"]

    # B lists — should NOT see A's key.
    r = client.get("/auth/api-keys", headers=_auth(tok_b))
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["items"]}
    assert a_key_id not in ids

    # B revoke attempt on A's key → 404.
    r = client.post(
        f"/auth/api-keys/{a_key_id}/revoke", headers=_auth(tok_b)
    )
    assert r.status_code == 404
