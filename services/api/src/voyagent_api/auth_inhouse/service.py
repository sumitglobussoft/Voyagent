"""High-level orchestration for the in-house auth subsystem.

The service layer is the only place that combines the password
hasher, the token issuer, the repositories and the revocation list.
Routes call services; services call repositories. No SQLAlchemy
imports here.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..revocation import build_revocation_list
from .models import (
    AuthResponse,
    PublicUser,
    RefreshRequest,
    SignInRequest,
    SignUpRequest,
    TokenPairResponse,
)
from .passwords import burn_dummy_verify, hash_password, verify_password
from .repository import RefreshTokenRepository, UserRepository
from .settings import get_auth_settings
from .tokens import (
    AccessTokenPayload,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    hash_refresh_token,
    issue_access_token,
    mint_refresh_token,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Sign-up, sign-in, refresh, sign-out and ``/me`` orchestration."""

    def __init__(self, db: AsyncSession, request: Request | None = None) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._refresh = RefreshTokenRepository(db)
        self._request = request

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _client_meta(self) -> tuple[str | None, str | None]:
        """Pull (user_agent, ip) off the active request, if any."""
        if self._request is None:
            return None, None
        ua = self._request.headers.get("user-agent")
        ip = self._request.client.host if self._request.client else None
        return (ua[:255] if ua else None), (ip[:64] if ip else None)

    async def _issue_pair_for_user(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        email: str,
        role: str,
    ) -> tuple[str, str, int]:
        """Mint + persist a new (access, refresh) pair for ``user_id``."""
        settings = get_auth_settings()
        access, _exp, _jti = issue_access_token(
            user_id=user_id, tenant_id=tenant_id, email=email, role=role
        )
        refresh_plain, refresh_digest, refresh_exp = mint_refresh_token()
        ua, ip = self._client_meta()
        await self._refresh.store(
            user_id=user_id,
            token_hash=refresh_digest,
            expires_at=refresh_exp,
            user_agent=ua,
            ip=ip,
        )
        return access, refresh_plain, settings.access_ttl_seconds

    @staticmethod
    def _public_user(user, tenant) -> PublicUser:  # type: ignore[no-untyped-def]
        return PublicUser(
            id=str(user.id),
            email=user.email,
            full_name=user.display_name,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
            tenant_id=str(tenant.id),
            tenant_name=tenant.display_name,
            created_at=user.created_at,
        )

    # ------------------------------------------------------------------ #
    # Sign-up                                                            #
    # ------------------------------------------------------------------ #

    async def sign_up(self, req: SignUpRequest) -> AuthResponse:
        """Create a new tenant + owner user and return a token pair."""
        # Pre-check duplicate email so we return the right error code
        # without burning the IntegrityError stack trace.
        existing = await self._users.find_by_email(req.email)
        if existing is not None:
            raise EmailAlreadyRegisteredError("email_already_registered")

        password_hash = hash_password(req.password)
        try:
            user, tenant = await self._users.create_user_with_tenant(
                email=req.email,
                full_name=req.full_name,
                password_hash=password_hash,
                agency_name=req.agency_name,
            )
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError("email_already_registered") from exc

        access, refresh, ttl = await self._issue_pair_for_user(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )
        return AuthResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=ttl,
            user=self._public_user(user, tenant),
        )

    # ------------------------------------------------------------------ #
    # Sign-in                                                            #
    # ------------------------------------------------------------------ #

    async def sign_in(self, req: SignInRequest) -> AuthResponse:
        """Verify credentials and return a fresh token pair.

        On a missing user we still call into argon2 against a dummy
        hash so the failure path takes the same wall-clock time as a
        wrong-password failure on a real user.
        """
        user = await self._users.find_by_email(req.email)
        if user is None or user.password_hash is None:
            burn_dummy_verify()
            raise InvalidCredentialsError("invalid_credentials")

        if not verify_password(user.password_hash, req.password):
            raise InvalidCredentialsError("invalid_credentials")

        tenant = await self._users.find_tenant(user.tenant_id)
        if tenant is None:
            # Should never happen — FK enforces it. Treat as auth failure.
            raise InvalidCredentialsError("invalid_credentials")

        await self._users.update_last_login(user.id)

        access, refresh, ttl = await self._issue_pair_for_user(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )
        return AuthResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=ttl,
            user=self._public_user(user, tenant),
        )

    # ------------------------------------------------------------------ #
    # Refresh                                                            #
    # ------------------------------------------------------------------ #

    async def refresh(self, req: RefreshRequest) -> TokenPairResponse:
        """Rotate the refresh token and mint a new access JWT."""
        digest = hash_refresh_token(req.refresh_token)
        row = await self._refresh.find_active(digest)
        if row is None:
            raise RefreshTokenRevokedError("invalid_refresh_token")

        user = await self._users.find_by_id(row.user_id)
        tenant = (
            await self._users.find_tenant(user.tenant_id) if user else None
        )
        if user is None or tenant is None:
            await self._refresh.revoke(digest)
            raise RefreshTokenRevokedError("invalid_refresh_token")

        # Single-use: revoke the presented refresh token before minting
        # the replacement so a stolen token can't be redeemed twice.
        await self._refresh.revoke(digest)

        access, refresh, ttl = await self._issue_pair_for_user(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )
        return TokenPairResponse(
            access_token=access, refresh_token=refresh, expires_in=ttl
        )

    # ------------------------------------------------------------------ #
    # Sign-out                                                           #
    # ------------------------------------------------------------------ #

    async def sign_out(
        self,
        access_payload: AccessTokenPayload | None,
        refresh_token: str | None,
    ) -> None:
        """Best-effort: revoke refresh + blacklist access ``jti``."""
        if refresh_token:
            try:
                await self._refresh.revoke(hash_refresh_token(refresh_token))
            except Exception:  # noqa: BLE001
                logger.debug("sign-out refresh revoke swallowed error")

        if access_payload is not None:
            try:
                rev = build_revocation_list()
                await rev.revoke(access_payload.jti, access_payload.exp)
            except Exception:  # noqa: BLE001
                logger.debug("sign-out access blacklist swallowed error")

    # ------------------------------------------------------------------ #
    # /me                                                                #
    # ------------------------------------------------------------------ #

    async def me(self, access_payload: AccessTokenPayload) -> PublicUser:
        """Return the :class:`PublicUser` for an authenticated principal."""
        try:
            user_uuid = uuid.UUID(access_payload.sub)
        except ValueError as exc:
            raise InvalidTokenError("malformed_subject") from exc

        user = await self._users.find_by_id(user_uuid)
        if user is None:
            raise InvalidTokenError("user_not_found")
        tenant = await self._users.find_tenant(user.tenant_id)
        if tenant is None:
            raise InvalidTokenError("tenant_not_found")
        return self._public_user(user, tenant)


__all__ = ["AuthService"]
