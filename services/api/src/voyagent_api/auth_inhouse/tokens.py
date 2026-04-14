"""JWT and refresh-token primitives for the in-house auth service.

All tokens are minted and verified here so the rest of the codebase
never reaches into ``jwt`` or ``secrets`` directly. Two token kinds:

* **Access JWT** — HS256, short-lived (1 h), carries the user id,
  tenant id, role and email. Verified on every request via
  :func:`verify_access_token`.

* **Refresh token** — opaque 256-bit random value, returned to the
  client as a base64url string. The plain value never goes to the
  database; only its sha256 digest is stored.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pydantic import BaseModel

from .settings import get_auth_settings

# --------------------------------------------------------------------------- #
# Errors                                                                      #
# --------------------------------------------------------------------------- #


class AuthError(Exception):
    """Base class for in-house auth errors."""


class InvalidCredentialsError(AuthError):
    """Sign-in failed: bad email or bad password."""


class InvalidTokenError(AuthError):
    """Access token failed signature, expiry or claim validation."""


class EmailAlreadyRegisteredError(AuthError):
    """Sign-up rejected because the email is already in use."""


class RefreshTokenExpiredError(AuthError):
    """Refresh token has passed its expiry."""


class RefreshTokenRevokedError(AuthError):
    """Refresh token has been revoked or never existed."""


# --------------------------------------------------------------------------- #
# Models                                                                      #
# --------------------------------------------------------------------------- #


class AccessTokenPayload(BaseModel):
    """Decoded access JWT claims."""

    sub: str
    tid: str
    role: str
    email: str
    iat: int
    exp: int
    jti: str


# --------------------------------------------------------------------------- #
# Access tokens (JWT)                                                         #
# --------------------------------------------------------------------------- #


def issue_access_token(
    *,
    user_id: str | uuid.UUID,
    tenant_id: str | uuid.UUID,
    email: str,
    role: str,
) -> tuple[str, datetime, str]:
    """Mint a signed access JWT.

    Returns a ``(jwt, expires_at, jti)`` tuple. The ``jti`` is also
    embedded in the token so :class:`RevocationList` can blacklist it.
    """
    settings = get_auth_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=settings.access_ttl_seconds)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "iss": settings.issuer,
        "aud": settings.audience,
    }
    token = jwt.encode(
        payload,
        settings.secret.get_secret_value(),
        algorithm="HS256",
    )
    return token, exp, jti


def verify_access_token(token: str) -> AccessTokenPayload:
    """Verify ``token`` and return its claims.

    Raises :class:`InvalidTokenError` for any failure (expired,
    bad signature, wrong issuer/audience, missing claim).
    """
    settings = get_auth_settings()
    try:
        decoded = jwt.decode(
            token,
            settings.secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.issuer,
            audience=settings.audience,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        return AccessTokenPayload(
            sub=str(decoded["sub"]),
            tid=str(decoded["tid"]),
            role=str(decoded.get("role", "agent")),
            email=str(decoded.get("email", "")),
            iat=int(decoded["iat"]),
            exp=int(decoded["exp"]),
            jti=str(decoded["jti"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError("malformed_claims") from exc


# --------------------------------------------------------------------------- #
# Refresh tokens (opaque)                                                     #
# --------------------------------------------------------------------------- #


def hash_refresh_token(plain: str) -> bytes:
    """Return the sha256 digest of a refresh token (32 bytes)."""
    return hashlib.sha256(plain.encode("utf-8")).digest()


def mint_refresh_token() -> tuple[str, bytes, datetime]:
    """Mint a fresh opaque refresh token.

    Returns ``(plain, sha256_digest, expires_at)``. The plain value is
    returned to the client; the digest is what the server persists.
    """
    settings = get_auth_settings()
    raw = secrets.token_bytes(32)
    plain = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    digest = hash_refresh_token(plain)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.refresh_ttl_seconds
    )
    return plain, digest, expires_at


__all__ = [
    "AccessTokenPayload",
    "AuthError",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "RefreshTokenExpiredError",
    "RefreshTokenRevokedError",
    "hash_refresh_token",
    "issue_access_token",
    "mint_refresh_token",
    "verify_access_token",
]
