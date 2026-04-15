"""TOTP 2FA foundation for the in-house auth subsystem.

Separate module from :mod:`service` / :mod:`repository` so the
team-onboarding parallel agent's edits don't collide with ours. Every
DB helper we need lives here next to the routes that call it.

Flow
----
1. ``POST /auth/totp/setup``   — authenticated. Mints a fresh base32
   secret, stores it on ``users.totp_secret`` with ``totp_enabled``
   still ``False``, and returns ``{secret, otpauth_url}`` so the
   client can draw a QR.
2. ``POST /auth/totp/verify``  — authenticated. Checks a 6-digit code
   against the stored secret. On success flips ``totp_enabled=True``.
3. ``POST /auth/totp/disable`` — authenticated. Requires BOTH the
   user's password AND a current TOTP code so a compromised session
   can't unilaterally disable 2FA. Clears the secret.
4. Sign-in: when a user has ``totp_enabled=True`` the normal
   ``/auth/sign-in`` endpoint returns 401 ``totp_required`` instead
   of issuing tokens. The client then re-posts to
   ``/auth/sign-in-totp`` with the 6-digit code to receive tokens.

TODO(security): ``totp_secret`` is currently stored as base32
plaintext. Wrap it with :class:`schemas.storage.crypto.FernetEnvKMS`
once the envelope format is agreed. Follow-up ticket.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pyotp
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import User

from .passwords import burn_dummy_verify, verify_password
from .tokens import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
)

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


TOTP_ISSUER = "Voyagent"
# ``valid_window=1`` accepts the previous / next 30s window to absorb
# clock skew between the server and the authenticator app.
_VALID_WINDOW = 1


# --------------------------------------------------------------------------- #
# Secret helpers                                                              #
# --------------------------------------------------------------------------- #


def generate_totp_secret() -> str:
    """Return a fresh base32-encoded TOTP secret (default 32 chars)."""
    return pyotp.random_base32()


def build_otpauth_url(secret: str, email: str) -> str:
    """Return an ``otpauth://totp/...`` URL for a QR code."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=email, issuer_name=TOTP_ISSUER
    )


def verify_totp_code(secret: str, code: str) -> bool:
    """Return ``True`` iff ``code`` is a valid TOTP for ``secret``."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    try:
        return bool(pyotp.TOTP(secret).verify(code, valid_window=_VALID_WINDOW))
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# DB helpers (scoped to this module to avoid editing repository.py)           #
# --------------------------------------------------------------------------- #


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _load_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def store_totp_secret(
    db: AsyncSession, user_id: uuid.UUID, secret: str
) -> None:
    """Persist a freshly-generated secret on the user row."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(totp_secret=secret, totp_enabled=False)
    )
    await db.commit()


async def enable_totp(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Flip ``totp_enabled=True`` for the given user."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(totp_enabled=True)
    )
    await db.commit()


async def clear_totp(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Disable TOTP and wipe the stored secret."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(totp_enabled=False, totp_secret=None)
    )
    await db.commit()


# --------------------------------------------------------------------------- #
# Setup / verify / disable service entrypoints                                #
# --------------------------------------------------------------------------- #


async def setup_totp_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[str, str]:
    """Mint + persist a new secret; return ``(secret, otpauth_url)``.

    Re-running setup before verify overwrites any previously-stored
    unconfirmed secret so a cancelled setup flow can be retried.
    """
    user = await _load_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unauthorized")

    secret = generate_totp_secret()
    await store_totp_secret(db, user_id, secret)
    url = build_otpauth_url(secret, user.email)
    return secret, url


async def verify_totp_for_user(
    db: AsyncSession, user_id: uuid.UUID, code: str
) -> None:
    """Verify the first-time TOTP code and flip ``totp_enabled=True``."""
    user = await _load_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="totp_not_initialized")
    if user.totp_enabled:
        # Idempotent — re-verifying an already-enabled user is a no-op.
        return
    if not verify_totp_code(user.totp_secret, code):
        raise HTTPException(status_code=401, detail="totp_invalid")
    await enable_totp(db, user_id)


async def disable_totp_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    password: str,
    code: str,
) -> None:
    """Disable 2FA. Requires both password and a valid TOTP code.

    Snapshot the user row fields eagerly and ``commit()`` the implicit
    read transaction BEFORE any branch that might raise HTTPException.
    Otherwise Starlette's middleware drains the exception through
    the session's __aexit__, aiosqlite invalidates the pooled
    connection mid-rollback, and (in SQLite-in-memory tests) the
    whole schema evaporates for subsequent requests.
    """
    user = await _load_user(db, user_id)
    # Pull the fields we need off the ORM row before we commit — once
    # the session commits, lazy-loaded attribute access can reopen a
    # transaction we don't want.
    if user is None or user.password_hash is None:
        await db.commit()
        raise HTTPException(status_code=401, detail="unauthorized")
    password_hash = user.password_hash
    totp_enabled = bool(user.totp_enabled)
    totp_secret = user.totp_secret
    await db.commit()

    if not verify_password(password_hash, password):
        raise HTTPException(status_code=403, detail="invalid_password")
    if not totp_enabled or not totp_secret:
        # Already disabled — nothing to do.
        return
    if not verify_totp_code(totp_secret, code):
        raise HTTPException(status_code=403, detail="totp_invalid")
    await clear_totp(db, user_id)


# --------------------------------------------------------------------------- #
# Sign-in helpers                                                             #
# --------------------------------------------------------------------------- #


async def user_requires_totp(
    db: AsyncSession, email: str
) -> bool:
    """Return ``True`` iff the user with this email has 2FA enabled.

    Consulted by the regular ``sign_in`` endpoint BEFORE minting
    tokens: if TOTP is required, the endpoint raises 401 with detail
    ``totp_required`` and the client retries via ``sign-in-totp``.
    """
    user = await _load_user_by_email(db, email)
    if user is None:
        return False
    return bool(getattr(user, "totp_enabled", False))


class TotpRequiredError(Exception):
    """Raised by the sign-in flow when the user has 2FA enabled.

    Carries a stable error code so the route handler can translate it
    to a ``401 totp_required`` without string-matching.
    """

    def __init__(self) -> None:
        super().__init__("totp_required")


async def sign_in_with_totp(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    code: str,
) -> User:
    """Verify ``(password, totp_code)`` and return the user row.

    Mirrors the shape of the normal sign-in credential check so the
    route handler can fall through into the same token-minting path
    without modifying the parallel-agent-owned ``AuthService.sign_in``.
    """
    user = await _load_user_by_email(db, email)
    if user is None or user.password_hash is None:
        burn_dummy_verify()
        raise InvalidCredentialsError("invalid_credentials")
    if not verify_password(user.password_hash, password):
        raise InvalidCredentialsError("invalid_credentials")
    if not bool(getattr(user, "email_verified", False)):
        raise EmailNotVerifiedError("email_not_verified")
    if not user.totp_enabled or not user.totp_secret:
        # 2FA isn't on — the caller should have used /auth/sign-in.
        raise HTTPException(status_code=400, detail="totp_not_enabled")
    if not verify_totp_code(user.totp_secret, code):
        raise HTTPException(status_code=401, detail="totp_invalid")
    # Best-effort last-login touch.
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_login_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return user


__all__ = [
    "TOTP_ISSUER",
    "TotpRequiredError",
    "build_otpauth_url",
    "clear_totp",
    "disable_totp_for_user",
    "enable_totp",
    "generate_totp_secret",
    "setup_totp_for_user",
    "sign_in_with_totp",
    "store_totp_secret",
    "user_requires_totp",
    "verify_totp_code",
    "verify_totp_for_user",
]
