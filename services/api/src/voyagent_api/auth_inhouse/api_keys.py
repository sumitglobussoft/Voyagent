"""API key management for headless access.

Key format:  ``vy_<prefix>_<body>``

* ``prefix`` — 8 urlsafe chars, stored plaintext, displayed in the UI,
  used as the O(1) lookup index.
* ``body``   — 32 urlsafe chars, never stored.
* SHA-256 hex of the full ``vy_...`` string is stored as ``key_hash``
  (64 chars, unique).

The full plaintext is returned to the caller exactly ONCE at
creation. After that only the prefix + metadata is ever retrievable.

Routes (mounted by ``routes.py``):

* ``POST /auth/api-keys``              — create
* ``GET  /auth/api-keys``              — list
* ``POST /auth/api-keys/{id}/revoke``  — revoke

Verification is exposed via :func:`get_principal_from_api_key_or_jwt`
which callers can use as a FastAPI dependency on routes that should
accept either a Voyagent JWT or a ``vy_...`` API key in
``Authorization: Bearer``. The existing ``get_current_principal``
dependency is intentionally untouched — we don't want to race the
parallel agent working on ``deps.py``.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import ApiKeyRow, User

from .deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
    _extract_bearer,  # type: ignore[attr-defined]
    _principal_from_token,  # type: ignore[attr-defined]
)

# --------------------------------------------------------------------------- #
# Key shape                                                                   #
# --------------------------------------------------------------------------- #


API_KEY_SCHEME_PREFIX = "vy_"
PREFIX_LEN = 8
BODY_LEN = 32


def _urlsafe(n: int) -> str:
    """Return ``n`` urlsafe base64 chars (alphanumeric, no padding)."""
    # ``token_urlsafe`` returns ~1.3 chars per byte — request a few
    # extra and slice.
    raw = secrets.token_urlsafe(n * 2)
    clean = raw.replace("-", "").replace("_", "")
    while len(clean) < n:
        clean += secrets.token_urlsafe(n).replace("-", "").replace("_", "")
    return clean[:n]


def mint_api_key_plaintext() -> tuple[str, str]:
    """Return ``(full_key, prefix)``. Full key is ``vy_<prefix>_<body>``."""
    prefix = _urlsafe(PREFIX_LEN)
    body = _urlsafe(BODY_LEN)
    full = f"{API_KEY_SCHEME_PREFIX}{prefix}_{body}"
    return full, prefix


def hash_api_key(full_key: str) -> str:
    """Return the SHA-256 hex digest of ``full_key`` (64 chars)."""
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def parse_api_key(full_key: str) -> tuple[str, str] | None:
    """Return ``(prefix, body)`` for a ``vy_<prefix>_<body>`` string.

    Returns ``None`` on any shape mismatch — does NOT raise.
    """
    if not isinstance(full_key, str):
        return None
    if not full_key.startswith(API_KEY_SCHEME_PREFIX):
        return None
    rest = full_key[len(API_KEY_SCHEME_PREFIX) :]
    parts = rest.split("_", 1)
    if len(parts) != 2:
        return None
    prefix, body = parts
    if len(prefix) != PREFIX_LEN or len(body) != BODY_LEN:
        return None
    return prefix, body


# --------------------------------------------------------------------------- #
# CRUD                                                                        #
# --------------------------------------------------------------------------- #


async def create_api_key(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    name: str,
    expires_in_days: int | None = None,
) -> tuple[ApiKeyRow, str]:
    """Insert a new key row and return ``(row, full_plaintext)``.

    ``full_plaintext`` is the only time the caller will ever see the
    full key string.
    """
    full, prefix = mint_api_key_plaintext()
    digest = hash_api_key(full)

    expires_at: datetime | None = None
    if expires_in_days is not None and expires_in_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=expires_in_days
        )

    row = ApiKeyRow(
        tenant_id=tenant_id,
        created_by_user_id=created_by_user_id,
        name=name,
        prefix=prefix,
        key_hash=digest,
        scopes="full",
        expires_at=expires_at,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:  # pragma: no cover - extremely unlikely
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="api_key_mint_collision"
        ) from exc
    await db.commit()
    await db.refresh(row)
    return row, full


async def list_api_keys_for_tenant(
    db: AsyncSession, tenant_id: uuid.UUID
) -> list[ApiKeyRow]:
    """Return every API key for the tenant, newest first."""
    result = await db.execute(
        select(ApiKeyRow)
        .where(ApiKeyRow.tenant_id == tenant_id)
        .order_by(ApiKeyRow.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(
    db: AsyncSession, key_id: uuid.UUID, tenant_id: uuid.UUID
) -> bool:
    """Soft-revoke a key. Returns ``False`` if the key isn't in this tenant."""
    row = (
        await db.execute(
            select(ApiKeyRow).where(
                ApiKeyRow.id == key_id,
                ApiKeyRow.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.revoked_at is None:
        await db.execute(
            update(ApiKeyRow)
            .where(ApiKeyRow.id == key_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
    return True


# --------------------------------------------------------------------------- #
# Verification path                                                           #
# --------------------------------------------------------------------------- #


async def resolve_api_key(
    db: AsyncSession, full_key: str
) -> AuthenticatedPrincipal | None:
    """Validate a ``vy_...`` bearer and return the caller principal.

    Returns ``None`` on any failure — caller translates to 401. Also
    touches ``last_used_at`` on a successful match.
    """
    parsed = parse_api_key(full_key)
    if parsed is None:
        return None
    prefix, _body = parsed

    row = (
        await db.execute(
            select(ApiKeyRow).where(ApiKeyRow.prefix == prefix)
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    # Constant-time digest compare to avoid a timing oracle on the hash.
    expected = row.key_hash
    actual = hash_api_key(full_key)
    if not secrets.compare_digest(expected, actual):
        return None

    if row.revoked_at is not None:
        return None
    if row.expires_at is not None:
        # SQLite drops tzinfo; coerce both sides to UTC-aware before compare
        # so the same code path works in unit tests and against Postgres.
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            return None

    # Resolve the creating user so we can construct a principal.
    user = (
        await db.execute(
            select(User).where(User.id == row.created_by_user_id)
        )
    ).scalar_one_or_none()
    if user is None:
        return None

    await db.execute(
        update(ApiKeyRow)
        .where(ApiKeyRow.id == row.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await db.commit()

    # Synthesise a principal that looks the same shape as a JWT-based
    # one so downstream authz code can treat both uniformly. ``jti`` is
    # set to the key id so logs can attribute actions back to a key.
    return AuthenticatedPrincipal(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        jti=f"apikey:{row.id}",
        exp=0,
    )


async def get_principal_from_api_key_or_jwt(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(db_session),
) -> AuthenticatedPrincipal:
    """FastAPI dependency — accept either a Voyagent JWT or a ``vy_...`` key.

    Fallback-chained: if the bearer token starts with ``vy_`` it goes
    through :func:`resolve_api_key`; otherwise it falls through to the
    existing JWT verification path in ``deps.py``. Apply this to
    endpoints that should be callable from CI jobs.
    """
    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )
    if token.startswith(API_KEY_SCHEME_PREFIX):
        principal = await resolve_api_key(session, token)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )
        return principal
    return await _principal_from_token(token)


__all__ = [
    "API_KEY_SCHEME_PREFIX",
    "create_api_key",
    "get_principal_from_api_key_or_jwt",
    "hash_api_key",
    "list_api_keys_for_tenant",
    "mint_api_key_plaintext",
    "parse_api_key",
    "resolve_api_key",
    "revoke_api_key",
]
