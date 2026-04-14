"""Tenant + user resolution on top of an authenticated principal.

Responsibilities
----------------
* Map an IDP-minted ``(tenant_external_id, user_external_id)`` pair onto
  Voyagent's canonical ``(tenant_id, user_id)`` :class:`EntityId` pair.
* Just-in-time provision a tenant + user row on first sight. New tenants
  are bootstrapped with sensible defaults (display name from the JWT,
  ``default_currency="USD"``); operators tighten them later.
* Tolerate the parallel persistence agent not having landed yet. If
  ``schemas.storage`` can't be imported we mint deterministic in-memory
  :class:`EntityId` values so the auth layer stays functional in local
  dev. A WARNING is logged so the fallback is never silent.

The fallback path is explicitly not a substitute for real persistence —
every non-ephemeral deployment needs the storage schema + Postgres.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from schemas.canonical import EntityId

from .auth import AuthenticatedPrincipal, get_principal

if TYPE_CHECKING:
    # Nothing to import for typing today — kept for future db session type.
    pass

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Context                                                                     #
# --------------------------------------------------------------------------- #


class TenantContext(BaseModel):
    """Per-request tenant + user context.

    Canonical ids (``tenant_id``, ``user_id``) are what the runtime, the
    session store, and audit rows speak. External ids are retained so
    debugging / admin tools can cross-reference against the IDP.
    """

    tenant_id: EntityId
    external_id: str = Field(min_length=1)
    display_name: str
    user_id: EntityId
    user_external_id: str = Field(min_length=1)
    role: str = Field(default="agent")


# --------------------------------------------------------------------------- #
# Storage import — guarded                                                    #
# --------------------------------------------------------------------------- #


def _load_storage() -> Any | None:
    """Attempt to import :mod:`schemas.storage`.

    Returns the module or ``None`` if the parallel persistence work is
    not yet available. We never raise — a missing persistence layer is a
    known gap while the work is in flight.
    """
    try:
        import schemas.storage as storage  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.debug("schemas.storage not available: %s", exc)
        return None
    return storage


# --------------------------------------------------------------------------- #
# Deterministic id fallback                                                   #
# --------------------------------------------------------------------------- #


def _uuidv7_from_seed(namespace: str, seed: str) -> EntityId:
    """Derive a UUIDv7-shaped id deterministically from ``seed``.

    Used only by the in-memory fallback so repeated logins for the same
    IDP tenant / user produce the same canonical id. The generated value
    satisfies the UUIDv7 regex canonical ids are validated against.
    """
    digest = hashlib.sha256(f"{namespace}:{seed}".encode("utf-8")).hexdigest()
    parts = (
        digest[0:8],
        digest[8:12],
        "7" + digest[13:16],
        "8" + digest[17:20],
        digest[20:32],
    )
    return "-".join(parts)


def _fallback_context(principal: AuthenticatedPrincipal) -> TenantContext:
    """Build a :class:`TenantContext` without touching the database.

    Emits a WARNING once per process per external tenant id so operators
    know the storage layer is not engaged.
    """
    tenant_id = _uuidv7_from_seed("voyagent.tenant", principal.tenant_external_id)
    user_id = _uuidv7_from_seed(
        f"voyagent.user:{principal.tenant_external_id}",
        principal.user_external_id,
    )
    _warn_fallback_once(principal.tenant_external_id)
    return TenantContext(
        tenant_id=tenant_id,
        external_id=principal.tenant_external_id,
        display_name=principal.display_name or principal.tenant_external_id,
        user_id=user_id,
        user_external_id=principal.user_external_id,
        role=principal.role,
    )


_warned_tenants: set[str] = set()


def _warn_fallback_once(external_id: str) -> None:
    """Log the in-memory fallback once per external tenant id."""
    if external_id in _warned_tenants:
        return
    _warned_tenants.add(external_id)
    logger.warning(
        "tenancy falling back to deterministic in-memory ids for tenant=%s — "
        "schemas.storage is not importable; install voyagent-schemas-storage "
        "to persist tenants.",
        external_id,
    )


# --------------------------------------------------------------------------- #
# Storage-backed resolution                                                   #
# --------------------------------------------------------------------------- #


async def _resolve_with_storage(
    principal: AuthenticatedPrincipal, storage: Any
) -> TenantContext:
    """Resolve (or provision) tenant + user rows through :mod:`schemas.storage`.

    TODO(voyagent-persistence): the parallel persistence work owns the
    AsyncSession / engine wiring. Until that lands, this path unwraps to
    the in-memory fallback rather than attempting to open a connection
    without configuration. When the engine + session factory are
    exposed, replace this function body with a real SELECT-or-INSERT
    against the ``tenants`` and ``users`` tables.
    """
    get_session_factory = getattr(storage, "get_async_session_factory", None)
    if get_session_factory is None:
        # Persistence types exist but no engine is wired yet — fall back.
        return _fallback_context(principal)

    # TODO(voyagent-persistence): flesh this out once the session factory
    # is provided. We deliberately do not half-implement a db write here,
    # because doing so without a tested migration path would mask bugs in
    # the parallel agent's schema.
    logger.warning(
        "schemas.storage present but session factory integration is pending — "
        "using deterministic fallback for tenant=%s",
        principal.tenant_external_id,
    )
    return _fallback_context(principal)


# --------------------------------------------------------------------------- #
# Public resolver                                                             #
# --------------------------------------------------------------------------- #


async def resolve_tenant(principal: AuthenticatedPrincipal) -> TenantContext:
    """Resolve the :class:`TenantContext` for ``principal``.

    Tries to load :mod:`schemas.storage` and defers to it when available.
    Falls back to deterministic in-memory ids otherwise.
    """
    storage = _load_storage()
    if storage is None:
        return _fallback_context(principal)
    try:
        return await _resolve_with_storage(principal, storage)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "tenant resolution via storage failed, falling back: %s", exc
        )
        return _fallback_context(principal)


async def get_tenant(
    principal: AuthenticatedPrincipal = Depends(get_principal),
) -> TenantContext:
    """FastAPI dependency — composes :func:`get_principal` + :func:`resolve_tenant`."""
    try:
        return await resolve_tenant(principal)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Any unexpected failure in resolution is an infra problem, not
        # a client problem. Surface as 503 so the client retries.
        logger.exception("resolve_tenant failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"tenant_resolution_failed: {exc}",
        ) from exc


# --------------------------------------------------------------------------- #
# Deterministic helpers exported for tests / other modules                    #
# --------------------------------------------------------------------------- #


def tenant_id_from_external(external_id: str) -> EntityId:
    """Return the canonical tenant id the fallback path would mint for ``external_id``."""
    return _uuidv7_from_seed("voyagent.tenant", external_id)


def user_id_from_external(tenant_external_id: str, user_external_id: str) -> EntityId:
    """Return the canonical user id for an ``(tenant, user)`` external pair."""
    return _uuidv7_from_seed(
        f"voyagent.user:{tenant_external_id}", user_external_id
    )


__all__ = [
    "TenantContext",
    "get_tenant",
    "resolve_tenant",
    "tenant_id_from_external",
    "user_id_from_external",
]


# Silence an unused-import warning for ``uuid`` on Python 3.12 where the
# stdlib module is imported for forward-compat even though it is not
# directly referenced below.
_ = uuid
