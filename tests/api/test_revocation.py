"""Tests for the token revocation layer.

The :class:`NullRevocationList` is the default in tests; we exercise
its interaction with :func:`verify_token` and the ``/auth/revoke``
endpoint (simulated by calling the handler function directly).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from fastapi import HTTPException

from voyagent_api import auth, revocation


_JWKS_URL = "https://fake-clerk.test/.well-known/jwks.json"
_ISSUER = "https://fake-clerk.test"


@pytest.fixture
def rsa_keypair() -> dict[str, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private.public_key().public_numbers()
    import base64

    def _b64(i: int) -> str:
        raw = i.to_bytes((i.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test-key-rev",
                "alg": "RS256",
                "use": "sig",
                "n": _b64(public_numbers.n),
                "e": _b64(public_numbers.e),
            }
        ]
    }
    return {"private_pem": private_pem, "jwks": jwks, "kid": "test-key-rev"}


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    auth._reset_jwks_cache_for_test()
    auth.set_auth_settings_for_test(None)
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())
    yield
    auth._reset_jwks_cache_for_test()
    auth.set_auth_settings_for_test(None)
    revocation.set_revocation_list_for_test(None)


def _sign(payload: dict[str, Any], keypair: dict[str, Any]) -> str:
    return jwt.encode(
        payload,
        keypair["private_pem"],
        algorithm="RS256",
        headers={"kid": keypair["kid"]},
    )


def _enable_auth() -> None:
    auth.set_auth_settings_for_test(
        auth.AuthSettings(
            provider="clerk",
            jwks_url=_JWKS_URL,
            issuer=_ISSUER,
            audience=None,
            enabled=True,
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_revoked_token_returns_401(rsa_keypair: dict[str, Any]) -> None:
    _enable_auth()
    respx.get(_JWKS_URL).mock(
        return_value=httpx.Response(200, json=rsa_keypair["jwks"])
    )

    now = int(time.time())
    token = _sign(
        {
            "sub": "user_abc",
            "org_id": "org_xyz",
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 300,
            "jti": "jti-to-revoke",
        },
        rsa_keypair,
    )

    # First verify OK.
    principal = await auth.verify_token(token)
    assert principal.user_external_id == "user_abc"

    # Revoke and retry — must fail.
    rev = revocation.build_revocation_list()
    await rev.revoke("jti-to-revoke", now + 300)

    with pytest.raises(HTTPException) as excinfo:
        await auth.verify_token(token)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "token_revoked"


@pytest.mark.asyncio
async def test_revoke_is_idempotent() -> None:
    rev = revocation.NullRevocationList()
    exp = int(time.time()) + 300
    await rev.revoke("jti-1", exp)
    await rev.revoke("jti-1", exp)
    assert await rev.is_revoked("jti-1")


@pytest.mark.asyncio
async def test_redis_unreachable_is_fail_open(
    rsa_keypair: dict[str, Any],
) -> None:
    """A Redis outage must not 401 valid tokens (fail-open)."""
    _enable_auth()

    class _BrokenClient:
        async def get(self, key: str) -> Any:
            raise RuntimeError("redis boom")

        async def set(self, key: str, value: Any, ex: int | None = None) -> Any:
            raise RuntimeError("redis boom")

    revocation.set_revocation_list_for_test(
        revocation.RedisRevocationList(_BrokenClient())
    )

    now = int(time.time())
    token = _sign(
        {
            "sub": "user_abc",
            "org_id": "org_xyz",
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 300,
            "jti": "jti-fail-open",
        },
        rsa_keypair,
    )

    with respx.mock:
        respx.get(_JWKS_URL).mock(
            return_value=httpx.Response(200, json=rsa_keypair["jwks"])
        )
        # Must NOT raise — Redis failure is fail-open.
        principal = await auth.verify_token(token)
    assert principal.user_external_id == "user_abc"


@pytest.mark.asyncio
async def test_null_revocation_list_is_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation.set_revocation_list_for_test(None)
    monkeypatch.delenv("VOYAGENT_REDIS_URL", raising=False)
    rev = revocation.build_revocation_list(env={})
    assert isinstance(rev, revocation.NullRevocationList)


@pytest.mark.asyncio
async def test_jti_absent_skips_revocation_check(
    rsa_keypair: dict[str, Any],
) -> None:
    _enable_auth()
    now = int(time.time())
    token = _sign(
        {
            "sub": "user_abc",
            "org_id": "org_xyz",
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 300,
            # no jti
        },
        rsa_keypair,
    )
    with respx.mock:
        respx.get(_JWKS_URL).mock(
            return_value=httpx.Response(200, json=rsa_keypair["jwks"])
        )
        principal = await auth.verify_token(token)
    assert principal.user_external_id == "user_abc"
