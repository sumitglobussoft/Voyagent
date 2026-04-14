"""Tenant + user resolution on top of an authenticated principal.

In the in-house auth world this module is much thinner than it used
to be: the access JWT carries the canonical ``tenant_id`` and
``user_id`` directly, so resolving a :class:`TenantContext` is a
straight lookup against the ``tenants`` table — no JIT provisioning,
no deterministic-id fallback.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.canonical import EntityId

from .auth import AuthenticatedPrincipal, get_principal
from .auth_inhouse.deps import db_session
from .auth_inhouse.repository import UserRepository

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Context                                                                     #
# --------------------------------------------------------------------------- #


class TenantContext(BaseModel):
    """Per-request tenant + user context.

    Mirrors the legacy field names so :mod:`chat` does not change.
    ``external_id`` and ``user_external_id`` carry the same string id
    as the canonical id in the in-house world (we no longer have a
    distinct upstream IDP id).
    """

    tenant_id: EntityId
    external_id: str = Field(min_length=1)
    display_name: str
    user_id: EntityId
    user_external_id: str = Field(min_length=1)
    role: str = Field(default="agent")


# --------------------------------------------------------------------------- #
# Resolver                                                                    #
# --------------------------------------------------------------------------- #


async def resolve_tenant(
    principal: AuthenticatedPrincipal,
    session: AsyncSession,
) -> TenantContext:
    """Look up the tenant row referenced by the principal's ``tid`` claim."""
    try:
        tenant_uuid = uuid.UUID(principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        ) from exc

    repo = UserRepository(session)
    tenant = await repo.find_tenant(tenant_uuid)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )

    return TenantContext(
        tenant_id=str(tenant.id),
        external_id=str(tenant.id),
        display_name=tenant.display_name,
        user_id=principal.user_id,
        user_external_id=principal.user_id,
        role=principal.role,
    )


async def get_tenant(
    principal: AuthenticatedPrincipal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
) -> TenantContext:
    """FastAPI dependency — the per-request :class:`TenantContext`."""
    try:
        return await resolve_tenant(principal, session)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("resolve_tenant failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"tenant_resolution_failed: {exc}",
        ) from exc


__all__ = [
    "TenantContext",
    "get_tenant",
    "resolve_tenant",
]
