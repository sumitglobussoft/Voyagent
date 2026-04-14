"""Authentication boundary for the Voyagent API.

Verifies an inbound ``Authorization: Bearer <JWT>`` minted by the identity
provider (Clerk in v0) and returns an :class:`AuthenticatedPrincipal` that
downstream code composes into a :class:`TenantContext`.

Design
------
* **Provider-agnostic behind an interface.** Clerk is the v0 implementation;
  the settings object carries a ``provider`` tag so swapping to WorkOS / Ory
  later is a driver-like swap rather than a code surgery.
* **JWKS-cached RS256.** We pull the JWKS document once, cache the decoded
  keys for 10 minutes, and verify the RS256 signature locally. No per-request
  network hop to Clerk.
* **Tenant from Clerk org.** Clerk puts the active organisation id on the
  JWT as ``org_id``. We also accept a custom ``tenant_id`` claim so
  deployments that use a different convention can wire their own. A token
  with neither is rejected with 403 — Voyagent is multi-tenant by design
  and a principal with no tenant is an invariant violation.
* **Dev mode is first-class but unsafe.** Setting ``VOYAGENT_AUTH_ENABLED=false``
  short-circuits signature verification and lets requests assert a tenant /
  actor via ``X-Voyagent-Dev-Tenant`` / ``X-Voyagent-Dev-Actor`` headers.
  This keeps the same dependency wired up in tests and local dev without
  requiring Clerk keys. A startup warning is emitted so this never ships
  by accident.

We **never** log the raw JWT. The claims we surface on
:class:`AuthenticatedPrincipal` are non-secret by construction, but any
logging of them should still scrub ``email`` for user-facing environments.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWKClient
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Settings                                                                    #
# --------------------------------------------------------------------------- #


class AuthSettings(BaseSettings):
    """Authentication configuration, loaded from ``VOYAGENT_AUTH_*`` env vars.

    * ``provider`` — identity provider tag. ``"clerk"`` for v0; retained so
      later WorkOS / Ory implementations can share the dependency surface.
    * ``jwks_url`` — URL serving the signing keys (``/.well-known/jwks.json``).
    * ``issuer`` — expected ``iss`` claim on every JWT.
    * ``audience`` — expected ``aud`` claim. Optional because Clerk short-
      session tokens default to no audience.
    * ``enabled`` — set to ``False`` for local dev / test to short-circuit
      signature verification and use header-driven principals instead.
    * ``jwks_cache_seconds`` — how long to cache the JWKS document.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_AUTH_",
        case_sensitive=False,
        extra="ignore",
    )

    provider: str = Field(default="clerk")
    jwks_url: str = Field(default="")
    issuer: str = Field(default="")
    audience: str | None = Field(default=None)
    enabled: bool = Field(default=True)
    jwks_cache_seconds: int = Field(default=600, ge=30)


_settings_singleton: AuthSettings | None = None


def get_auth_settings() -> AuthSettings:
    """Return the process-wide :class:`AuthSettings`.

    Constructed on first call. Tests override via
    :func:`set_auth_settings_for_test`.
    """
    global _settings_singleton
    if _settings_singleton is None:
        _settings_singleton = AuthSettings()
        if not _settings_singleton.enabled:
            logger.warning(
                "VOYAGENT_AUTH_ENABLED=false — auth is disabled. "
                "Dev principals will be derived from request headers. "
                "This is UNSAFE and must not be used in production."
            )
    return _settings_singleton


def set_auth_settings_for_test(settings: AuthSettings | None) -> None:
    """Test-only hook to swap the process-wide settings.

    Passing ``None`` resets the singleton so the next call re-reads env.
    """
    global _settings_singleton
    _settings_singleton = settings


# --------------------------------------------------------------------------- #
# Principal                                                                   #
# --------------------------------------------------------------------------- #


class AuthenticatedPrincipal(BaseModel):
    """A verified identity lifted from a JWT (or a dev-mode header set).

    ``user_external_id`` is the IDP-minted stable user id (``sub`` for
    Clerk). ``tenant_external_id`` is the IDP-minted tenant / org id
    (``org_id`` for Clerk). ``role`` is a coarse label that maps to
    :class:`schemas.storage.UserRole` when persistence is available.

    ``claims`` retains the original JWT payload so callers that need to
    inspect provider-specific claims (e.g. ``org_role`` for Clerk) do not
    need to re-parse the token.
    """

    user_external_id: str = Field(min_length=1)
    tenant_external_id: str = Field(min_length=1)
    email: str | None = None
    display_name: str | None = None
    role: str = Field(default="agent")
    claims: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# JWKS cache                                                                  #
# --------------------------------------------------------------------------- #


_jwks_client_cache: dict[str, tuple[PyJWKClient, float]] = {}


def _get_jwks_client(jwks_url: str, cache_seconds: int) -> PyJWKClient:
    """Return a cached :class:`PyJWKClient` for ``jwks_url``.

    :class:`PyJWKClient` already performs per-key caching, but we refresh
    the entire client on a coarse timer so key rotations are picked up
    without a process restart.
    """
    now = time.monotonic()
    cached = _jwks_client_cache.get(jwks_url)
    if cached is not None:
        client, expires_at = cached
        if now < expires_at:
            return client
    client = PyJWKClient(jwks_url, cache_keys=True, lifespan=cache_seconds)
    _jwks_client_cache[jwks_url] = (client, now + cache_seconds)
    return client


def _reset_jwks_cache_for_test() -> None:
    """Test hook — drop the process-wide JWKS client cache."""
    _jwks_client_cache.clear()


# --------------------------------------------------------------------------- #
# Token verification                                                          #
# --------------------------------------------------------------------------- #


async def verify_token(token: str) -> AuthenticatedPrincipal:
    """Verify ``token`` against the configured provider and return a principal.

    Raises :class:`HTTPException` (401 for bad signature / expired, 403 for
    missing tenant). The function is ``async`` so callers can ``await`` it,
    but the underlying PyJWKClient call is synchronous today — that's fine
    for v0 since JWKS is cached and the hot path is signature math.
    """
    settings = get_auth_settings()

    if not settings.jwks_url or not settings.issuer:
        logger.error("auth misconfigured: missing jwks_url / issuer")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="auth_not_configured",
        )

    try:
        jwks_client = _get_jwks_client(settings.jwks_url, settings.jwks_cache_seconds)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except jwt.exceptions.PyJWKClientError as exc:
        logger.warning("jwks lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_jwks_unavailable",
        ) from exc
    except httpx.HTTPError as exc:  # defensive — PyJWKClient uses urllib today
        logger.warning("jwks fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_jwks_unavailable",
        ) from exc

    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
        "issuer": settings.issuer,
        "options": {"require": ["exp", "iss"]},
    }
    if settings.audience:
        decode_kwargs["audience"] = settings.audience
    else:
        decode_kwargs["options"]["verify_aud"] = False

    try:
        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        # Covers bad signature, bad issuer, bad audience, missing claims.
        logger.info("jwt rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_invalid",
        ) from exc

    return _principal_from_claims(claims)


def _principal_from_claims(claims: dict[str, Any]) -> AuthenticatedPrincipal:
    """Build an :class:`AuthenticatedPrincipal` from verified JWT claims.

    Tenant resolution: prefer Clerk's ``org_id`` (active organisation), fall
    back to a custom ``tenant_id`` claim for deployments that use a
    different convention. Reject tokens that carry neither — Voyagent has
    no "tenantless" user mode.
    """
    user_external_id = str(claims.get("sub") or "").strip()
    if not user_external_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_missing_subject",
        )

    tenant_external_id = (
        str(claims.get("org_id") or "").strip()
        or str(claims.get("tenant_id") or "").strip()
    )
    if not tenant_external_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no_tenant",
        )

    role = (
        str(claims.get("org_role") or "").strip()
        or str(claims.get("role") or "").strip()
        or "agent"
    )

    email_raw = claims.get("email")
    email = str(email_raw).strip() if email_raw else None
    name_raw = (
        claims.get("name")
        or claims.get("display_name")
        or claims.get("given_name")
    )
    display_name = str(name_raw).strip() if name_raw else None

    return AuthenticatedPrincipal(
        user_external_id=user_external_id,
        tenant_external_id=tenant_external_id,
        email=email,
        display_name=display_name,
        role=role,
        claims=dict(claims),
    )


# --------------------------------------------------------------------------- #
# FastAPI dependencies                                                        #
# --------------------------------------------------------------------------- #


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


def _dev_principal(
    dev_tenant: str | None,
    dev_actor: str | None,
    dev_role: str | None,
    dev_email: str | None,
) -> AuthenticatedPrincipal:
    """Build a principal for dev mode from request headers.

    Headers:
      * ``X-Voyagent-Dev-Tenant`` — tenant external id (required).
      * ``X-Voyagent-Dev-Actor`` — user external id (required).
      * ``X-Voyagent-Dev-Role`` — coarse role (optional, default ``"agent"``).
      * ``X-Voyagent-Dev-Email`` — user email (optional).
    """
    if not dev_tenant or not dev_actor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="dev_auth_headers_missing",
        )
    return AuthenticatedPrincipal(
        user_external_id=dev_actor,
        tenant_external_id=dev_tenant,
        email=dev_email,
        display_name=dev_actor,
        role=dev_role or "agent",
        claims={"dev_mode": True},
    )


async def get_principal(
    authorization: str | None = Header(default=None),
    x_voyagent_dev_tenant: str | None = Header(default=None),
    x_voyagent_dev_actor: str | None = Header(default=None),
    x_voyagent_dev_role: str | None = Header(default=None),
    x_voyagent_dev_email: str | None = Header(default=None),
) -> AuthenticatedPrincipal:
    """FastAPI dependency — authenticated principal or 401.

    In dev mode (``VOYAGENT_AUTH_ENABLED=false``) the tenant / actor come
    from the ``X-Voyagent-Dev-*`` header set and no signature check runs.
    **Never** rely on this outside of local dev and tests.
    """
    settings = get_auth_settings()

    if not settings.enabled:
        return _dev_principal(
            x_voyagent_dev_tenant,
            x_voyagent_dev_actor,
            x_voyagent_dev_role,
            x_voyagent_dev_email,
        )

    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authorization_header_missing",
        )
    return await verify_token(token)


async def get_principal_optional(
    authorization: str | None = Header(default=None),
    x_voyagent_dev_tenant: str | None = Header(default=None),
    x_voyagent_dev_actor: str | None = Header(default=None),
    x_voyagent_dev_role: str | None = Header(default=None),
    x_voyagent_dev_email: str | None = Header(default=None),
) -> AuthenticatedPrincipal | None:
    """Dependency variant that returns ``None`` when no credentials are present.

    Use this for endpoints that allow anonymous callers. Any credentials
    that ARE supplied must still be valid — a bad JWT is not silently
    downgraded to anonymous.
    """
    settings = get_auth_settings()

    if not settings.enabled:
        if not x_voyagent_dev_tenant and not x_voyagent_dev_actor:
            return None
        return _dev_principal(
            x_voyagent_dev_tenant,
            x_voyagent_dev_actor,
            x_voyagent_dev_role,
            x_voyagent_dev_email,
        )

    token = _extract_bearer(authorization)
    if token is None:
        return None
    return await verify_token(token)


__all__ = [
    "AuthSettings",
    "AuthenticatedPrincipal",
    "get_auth_settings",
    "get_principal",
    "get_principal_optional",
    "set_auth_settings_for_test",
    "verify_token",
]
