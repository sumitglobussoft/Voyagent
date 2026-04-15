"""FastAPI dependencies for the in-house auth subsystem.

Exposes :class:`AuthenticatedPrincipal` and the principal-resolving
dependencies (:func:`get_current_principal`,
:func:`get_current_principal_optional`) used by chat, tenancy, and
audit.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import db_session as _db_session
from ..revocation import build_revocation_list
from .models import PublicUser
from .repository import UserRepository
from .tokens import (
    AccessTokenPayload,
    InvalidTokenError,
    verify_access_token,
)

logger = logging.getLogger(__name__)


# Re-export under the canonical module path so other code can import it
# from .deps without reaching into ..db.
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` for FastAPI dependency injection."""
    async for session in _db_session():
        yield session


class AuthenticatedPrincipal(BaseModel):
    """A verified caller identity, derived from a Voyagent access JWT."""

    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    email: str
    role: str = Field(default="agent")
    jti: str = Field(min_length=1)
    exp: int

    # Compatibility shims so legacy call sites that read the old names
    # still work without per-field renames.
    @property
    def user_external_id(self) -> str:
        """Legacy alias for :attr:`user_id`."""
        return self.user_id

    @property
    def tenant_external_id(self) -> str:
        """Legacy alias for :attr:`tenant_id`."""
        return self.tenant_id

    @property
    def display_name(self) -> str:
        """Legacy alias used by tenancy fallback display names."""
        return self.email


def _extract_bearer(authorization: str | None) -> str | None:
    """Return the token portion of an ``Authorization: Bearer <token>`` header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


async def _principal_from_token(token: str) -> AuthenticatedPrincipal:
    """Verify ``token`` and return a principal, or raise 401."""
    try:
        payload = verify_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc

    # Revocation check after signature verification so we don't query
    # Redis on garbage tokens.
    try:
        rev = build_revocation_list()
        if await rev.is_revoked(payload.jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Fail-open — denylist outage must not 401 everyone.
        logger.warning("revocation check failed (fail-open): %s", exc)

    return AuthenticatedPrincipal(
        user_id=payload.sub,
        tenant_id=payload.tid,
        email=payload.email,
        role=payload.role or "agent",
        jti=payload.jti,
        exp=payload.exp,
    )


async def get_current_principal(
    authorization: str | None = Header(default=None),
) -> AuthenticatedPrincipal:
    """FastAPI dependency — return the authenticated principal or 401."""
    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )
    return await _principal_from_token(token)


async def get_current_principal_optional(
    authorization: str | None = Header(default=None),
) -> AuthenticatedPrincipal | None:
    """Variant that returns ``None`` when no credentials are present.

    A bad token is still rejected; only a missing one returns ``None``.
    """
    token = _extract_bearer(authorization)
    if token is None:
        return None
    return await _principal_from_token(token)


async def get_current_access_payload(
    authorization: str | None = Header(default=None),
) -> AccessTokenPayload:
    """Return the raw decoded access JWT payload, or raise 401."""
    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )
    try:
        return verify_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc


async def require_agency_admin(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """FastAPI dependency — require ``role == "agency_admin"`` on the caller.

    Wraps :func:`get_current_principal`. Returns the principal unchanged
    when the check passes; raises 403 ``forbidden_role`` when it fails.
    Used by admin-only read surfaces (e.g. ``/audit``) to enforce the
    principle of least privilege — finance / ops staff don't need to
    see other staff's actions.

    Distinct from 401 ``unauthorized`` so the UI can tell "you aren't
    signed in" apart from "you're signed in but lack the role".
    """
    if principal.role != "agency_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden_role",
        )
    return principal


async def get_current_user(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> PublicUser:
    """Resolve the full :class:`PublicUser` row for the principal."""
    import uuid as _uuid

    repo = UserRepository(session)
    try:
        user_uuid = _uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc

    user = await repo.find_by_id(user_uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )
    tenant = await repo.find_tenant(user.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )
    return PublicUser(
        id=str(user.id),
        email=user.email,
        full_name=user.display_name,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        tenant_id=str(tenant.id),
        tenant_name=tenant.display_name,
        created_at=user.created_at,
        email_verified=bool(getattr(user, "email_verified", False)),
    )


__all__ = [
    "AuthenticatedPrincipal",
    "db_session",
    "get_current_access_payload",
    "get_current_principal",
    "get_current_principal_optional",
    "get_current_user",
    "require_agency_admin",
]
