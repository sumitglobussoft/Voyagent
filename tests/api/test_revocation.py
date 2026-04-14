"""Tests for the JWT revocation list wiring.

Covers:
  * ``build_revocation_list`` picks Null in-memory when no Redis URL is set.
  * ``build_revocation_list`` picks the Redis-backed list when a URL is set
    (mocked at the ``redis.asyncio.from_url`` boundary — no live Redis).
  * Adding a ``jti`` to the denylist invalidates ``/me`` on the next request.
  * Fail-open: a Redis GET failure does not 401 the user.
"""

from __future__ import annotations

import os
from typing import Any

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


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
async def _fresh_state() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
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


_SIGNUP_BODY = {
    "email": "rev@example.com",
    "password": "Sup3rSecretValue!",
    "full_name": "Rev Tester",
    "agency_name": "Rev Travel",
}


# --------------------------------------------------------------------------- #
# Factory wiring                                                              #
# --------------------------------------------------------------------------- #


def test_build_revocation_list_without_redis_url_returns_null() -> None:
    """Env without VOYAGENT_REDIS_URL must fall back to the in-memory list."""
    revocation.set_revocation_list_for_test(None)
    try:
        lst = revocation.build_revocation_list(env={})
        assert isinstance(lst, revocation.NullRevocationList)
    finally:
        revocation.set_revocation_list_for_test(None)


def test_build_revocation_list_with_redis_url_uses_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured VOYAGENT_REDIS_URL must yield a RedisRevocationList.

    We mock ``redis.asyncio.from_url`` so no real Redis is involved — the
    invariant we care about is the *selection*, not the IO.
    """
    import redis.asyncio as redis_async  # type: ignore[import-not-found]

    class _FakeClient:
        async def get(self, key: str) -> str | None:  # pragma: no cover
            return None

        async def set(self, *a: Any, **kw: Any) -> None:  # pragma: no cover
            return None

    def _fake_from_url(url: str, **kwargs: Any) -> _FakeClient:
        assert url == "redis://fake:6379/0"
        return _FakeClient()

    monkeypatch.setattr(redis_async, "from_url", _fake_from_url)
    revocation.set_revocation_list_for_test(None)
    try:
        lst = revocation.build_revocation_list(
            env={"VOYAGENT_REDIS_URL": "redis://fake:6379/0"}
        )
        assert isinstance(lst, revocation.RedisRevocationList)
    finally:
        revocation.set_revocation_list_for_test(None)


# --------------------------------------------------------------------------- #
# Integration: denylist blocks /me                                            #
# --------------------------------------------------------------------------- #


def test_revoked_jti_causes_next_me_to_401(client: TestClient) -> None:
    """Adding a jti to the denylist immediately invalidates /me."""
    import asyncio

    import jwt

    signup = client.post("/auth/sign-up", json=_SIGNUP_BODY).json()
    access = signup["access_token"]

    ok = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert ok.status_code == 200

    settings = get_auth_settings()
    decoded = jwt.decode(
        access,
        settings.secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.audience,
        issuer=settings.issuer,
    )
    jti = decoded["jti"]
    exp = decoded["exp"]

    lst = revocation.build_revocation_list()

    async def _revoke() -> None:
        await lst.revoke(jti, exp)

    asyncio.run(_revoke())

    after = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert after.status_code == 401


def test_redis_revocation_fail_open_does_not_401_on_client_error() -> None:
    """When Redis GET raises, is_revoked must return False (fail-open)."""
    import asyncio

    class _BrokenClient:
        async def get(self, key: str) -> str | None:
            raise RuntimeError("connection refused")

        async def set(self, *a: Any, **kw: Any) -> None:
            raise RuntimeError("connection refused")

    rl = revocation.RedisRevocationList(_BrokenClient())

    async def _assert() -> None:
        assert await rl.is_revoked("any-jti") is False
        # revoke() must also swallow to avoid 500s in sign-out.
        await rl.revoke("any-jti", int(1e18))

    asyncio.run(_assert())
