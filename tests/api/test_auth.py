"""Tests for the API auth boundary.

Covered surface:

* :func:`verify_token` — valid RS256, expired, bad signature, missing org.
* :func:`get_principal` — dev-mode happy path + missing-header failure.

Strategy
--------
We generate an in-test RSA keypair, serve its public half as a JWKS
document through ``respx``, and mint tokens locally. This keeps the test
hermetic — no network, no dependency on a running Clerk instance.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from fastapi import HTTPException

from voyagent_api import auth


_JWKS_URL = "https://fake-clerk.test/.well-known/jwks.json"
_ISSUER = "https://fake-clerk.test"


# --------------------------------------------------------------------------- #
# Keypair + JWKS fixture                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture
def rsa_keypair() -> dict[str, Any]:
    """Generate a fresh 2048-bit RSA keypair for the test.

    Returns the private key (for signing) and the JWKS document (for
    :func:`verify_token`'s lookup).
    """
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private.public_key().public_numbers()

    # Build a minimal JWKS entry. ``kid`` must be stable so tokens signed
    # here resolve to the same entry via the JWKS client.
    import base64

    def _b64(i: int) -> str:
        raw = i.to_bytes((i.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test-key-1",
                "alg": "RS256",
                "use": "sig",
                "n": _b64(public_numbers.n),
                "e": _b64(public_numbers.e),
            }
        ]
    }

    return {"private_pem": private_pem, "jwks": jwks, "kid": "test-key-1"}


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Reset the JWKS cache and auth settings between tests."""
    auth._reset_jwks_cache_for_test()
    auth.set_auth_settings_for_test(None)
    yield
    auth._reset_jwks_cache_for_test()
    auth.set_auth_settings_for_test(None)


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


# --------------------------------------------------------------------------- #
# verify_token — positive and negative paths                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_happy_path(rsa_keypair: dict[str, Any]) -> None:
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
            "email": "a@b.test",
            "name": "Alice",
            "org_role": "agency_admin",
        },
        rsa_keypair,
    )

    principal = await auth.verify_token(token)

    assert principal.user_external_id == "user_abc"
    assert principal.tenant_external_id == "org_xyz"
    assert principal.email == "a@b.test"
    assert principal.display_name == "Alice"
    assert principal.role == "agency_admin"


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_expired(rsa_keypair: dict[str, Any]) -> None:
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
            "iat": now - 600,
            "exp": now - 300,
        },
        rsa_keypair,
    )

    with pytest.raises(HTTPException) as excinfo:
        await auth.verify_token(token)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "token_expired"


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_bad_signature(rsa_keypair: dict[str, Any]) -> None:
    """Tamper with the payload segment — signature verification must fail."""
    _enable_auth()
    respx.get(_JWKS_URL).mock(
        return_value=httpx.Response(200, json=rsa_keypair["jwks"])
    )

    now = int(time.time())
    good = _sign(
        {
            "sub": "user_abc",
            "org_id": "org_xyz",
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 300,
        },
        rsa_keypair,
    )
    header, payload, sig = good.split(".")
    # Flip a byte in the signature — still base64url, just not valid.
    bad_sig = "A" + sig[1:] if sig[0] != "A" else "B" + sig[1:]
    tampered = f"{header}.{payload}.{bad_sig}"

    with pytest.raises(HTTPException) as excinfo:
        await auth.verify_token(tampered)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "token_invalid"


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_missing_org(rsa_keypair: dict[str, Any]) -> None:
    _enable_auth()
    respx.get(_JWKS_URL).mock(
        return_value=httpx.Response(200, json=rsa_keypair["jwks"])
    )

    now = int(time.time())
    token = _sign(
        {
            "sub": "user_abc",
            # no org_id / tenant_id
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 300,
        },
        rsa_keypair,
    )

    with pytest.raises(HTTPException) as excinfo:
        await auth.verify_token(token)
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "no_tenant"


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_accepts_custom_tenant_claim(
    rsa_keypair: dict[str, Any],
) -> None:
    _enable_auth()
    respx.get(_JWKS_URL).mock(
        return_value=httpx.Response(200, json=rsa_keypair["jwks"])
    )

    now = int(time.time())
    token = _sign(
        {
            "sub": "user_abc",
            "tenant_id": "tenant_from_claim",
            "iss": _ISSUER,
            "iat": now,
            "exp": now + 300,
        },
        rsa_keypair,
    )

    principal = await auth.verify_token(token)
    assert principal.tenant_external_id == "tenant_from_claim"


# --------------------------------------------------------------------------- #
# Dev mode                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dev_mode_happy_path() -> None:
    auth.set_auth_settings_for_test(
        auth.AuthSettings(enabled=False, jwks_url="", issuer="")
    )
    principal = await auth.get_principal(
        authorization=None,
        x_voyagent_dev_tenant="t1",
        x_voyagent_dev_actor="a1",
        x_voyagent_dev_role="agency_admin",
        x_voyagent_dev_email="a@b.test",
    )
    assert principal.tenant_external_id == "t1"
    assert principal.user_external_id == "a1"
    assert principal.role == "agency_admin"
    assert principal.email == "a@b.test"


@pytest.mark.asyncio
async def test_dev_mode_missing_headers_rejects() -> None:
    auth.set_auth_settings_for_test(
        auth.AuthSettings(enabled=False, jwks_url="", issuer="")
    )
    with pytest.raises(HTTPException) as excinfo:
        await auth.get_principal(
            authorization=None,
            x_voyagent_dev_tenant=None,
            x_voyagent_dev_actor=None,
            x_voyagent_dev_role=None,
            x_voyagent_dev_email=None,
        )
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "dev_auth_headers_missing"


@pytest.mark.asyncio
async def test_production_mode_rejects_missing_authorization() -> None:
    _enable_auth()
    with pytest.raises(HTTPException) as excinfo:
        await auth.get_principal(
            authorization=None,
            x_voyagent_dev_tenant="ignored",
            x_voyagent_dev_actor="ignored",
            x_voyagent_dev_role=None,
            x_voyagent_dev_email=None,
        )
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "authorization_header_missing"


# Silence pyflakes for the stdlib json import used only when Clerk payload
# fields get expanded in future tests.
_ = json
