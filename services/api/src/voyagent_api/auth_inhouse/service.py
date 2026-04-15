"""High-level orchestration for the in-house auth subsystem.

The service layer is the only place that combines the password
hasher, the token issuer, the repositories and the revocation list.
Routes call services; services call repositories. No SQLAlchemy
imports here.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import InviteRow, InviteStatusEnum

from ..revocation import build_revocation_list
from .models import (
    AcceptInviteRequest,
    AuthResponse,
    CreateInviteRequest,
    InviteSummary,
    PublicUser,
    RefreshRequest,
    SignInRequest,
    SignUpRequest,
    TokenPairResponse,
)
from .passwords import (
    PasswordTooWeakError,
    burn_dummy_verify,
    hash_password,
    validate_password_strength,
    verify_password,
)
from .repository import (
    InviteRepository,
    RefreshTokenRepository,
    UserRepository,
)
from .settings import get_auth_settings
from .tokens import (
    AccessTokenPayload,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    InvalidVerificationTokenError,
    RefreshTokenRevokedError,
    hash_refresh_token,
    issue_access_token,
    mint_refresh_token,
)
from .verification import (
    build_password_reset_token_store,
    build_verification_token_store,
    get_password_reset_ttl_seconds,
    get_verification_ttl_seconds,
)


class InviteAlreadyExistsError(Exception):
    """Raised when a pending invite already exists for an email in a tenant."""


class InviteNotFoundError(Exception):
    """Raised when an invite id / token cannot be resolved."""


class InviteInvalidStateError(Exception):
    """Raised when an invite is expired, revoked, or already accepted."""

logger = logging.getLogger(__name__)


class AuthService:
    """Sign-up, sign-in, refresh, sign-out and ``/me`` orchestration."""

    def __init__(self, db: AsyncSession, request: Request | None = None) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._refresh = RefreshTokenRepository(db)
        self._invites = InviteRepository(db)
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
            email_verified=bool(getattr(user, "email_verified", False)),
        )

    # ------------------------------------------------------------------ #
    # Sign-up                                                            #
    # ------------------------------------------------------------------ #

    async def sign_up(self, req: SignUpRequest) -> AuthResponse:
        """Create a new tenant + owner user and return a token pair."""
        # Auth hardening pack: enforce the deterministic password
        # strength rules before we even pre-check for a duplicate. A
        # weak password should never get to the hasher.
        validate_password_strength(req.password)
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

        # Block sign-in for unverified users with a distinct error code so
        # clients can branch into a "please verify" UX without having to
        # distinguish it from a wrong-password 401 by string-matching.
        if not bool(getattr(user, "email_verified", False)):
            raise EmailNotVerifiedError("email_not_verified")

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
        """Return the :class:`PublicUser` for an authenticated principal.

        An unverified user still sees their own ``/me`` — the client
        reads ``email_verified`` off the payload and renders a "please
        verify" banner. Revoking the access token on the server would
        force the user to the login screen where the bounced sign-in
        couldn't explain itself.
        """
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

    # ------------------------------------------------------------------ #
    # Email verification                                                 #
    # ------------------------------------------------------------------ #

    async def send_verification_email(
        self, access_payload: AccessTokenPayload
    ) -> str:
        """Mint + persist a verification token; returns the plain token."""
        try:
            user_uuid = uuid.UUID(access_payload.sub)
        except ValueError as exc:
            raise InvalidTokenError("malformed_subject") from exc

        user = await self._users.find_by_id(user_uuid)
        if user is None:
            raise InvalidTokenError("user_not_found")

        token = uuid.uuid4().hex
        ttl = get_verification_ttl_seconds()
        store = build_verification_token_store()
        await store.put(token, str(user.id), ttl)
        return token

    async def verify_email(self, token: str) -> None:
        """Consume ``token`` and flip ``email_verified`` on the user."""
        store = build_verification_token_store()
        user_id_str = await store.take(token)
        if user_id_str is None:
            raise InvalidVerificationTokenError("token_invalid")
        try:
            user_uuid = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise InvalidVerificationTokenError("token_invalid") from exc
        await self._users.mark_email_verified(user_uuid)

    # ------------------------------------------------------------------ #
    # Profile update                                                     #
    # ------------------------------------------------------------------ #

    async def update_profile(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str | None,
        email: str | None,
    ) -> tuple[PublicUser, bool]:
        user, email_changed = await self._users.update_profile(
            user_id=user_id, full_name=full_name, email=email
        )
        tenant = await self._users.find_tenant(user.tenant_id)
        if tenant is None:
            raise InvalidTokenError("tenant_not_found")
        return self._public_user(user, tenant), email_changed

    # ------------------------------------------------------------------ #
    # Password reset                                                     #
    # ------------------------------------------------------------------ #

    async def request_password_reset(self, email: str) -> str | None:
        """Mint + store a reset token. Returns ``None`` for unknown email."""
        user = await self._users.find_by_email(email)
        if user is None:
            return None
        token = secrets.token_urlsafe(32)
        ttl = get_password_reset_ttl_seconds()
        store = build_password_reset_token_store()
        await store.put(token, str(user.id), ttl)
        return token

    async def reset_password(self, token: str, new_password: str) -> None:
        store = build_password_reset_token_store()
        user_id_str = await store.take(token)
        if user_id_str is None:
            raise InvalidVerificationTokenError("token_invalid")
        try:
            user_uuid = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise InvalidVerificationTokenError("token_invalid") from exc
        user = await self._users.find_by_id(user_uuid)
        if user is None:
            raise InvalidVerificationTokenError("token_invalid")

        password_hash = hash_password(new_password)
        await self._users.update_password_hash(user_uuid, password_hash)
        await self._refresh.revoke_all_for_user(user_uuid)

    # ------------------------------------------------------------------ #
    # Invites                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _invite_summary(row: InviteRow) -> InviteSummary:
        return InviteSummary(
            id=str(row.id),
            tenant_id=str(row.tenant_id),
            email=row.email,
            role=row.role,
            status=row.status.value
            if hasattr(row.status, "value")
            else str(row.status),
            expires_at=row.expires_at,
            created_at=row.created_at,
            accepted_at=row.accepted_at,
            revoked_at=row.revoked_at,
            invited_by_user_id=str(row.invited_by_user_id),
        )

    @staticmethod
    def _hash_invite_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def create_invite(
        self,
        *,
        tenant_id: uuid.UUID,
        invited_by_user_id: uuid.UUID,
        body: CreateInviteRequest,
    ) -> tuple[InviteSummary, str]:
        existing = await self._invites.find_pending_for_email(
            tenant_id, body.email
        )
        if existing is not None:
            raise InviteAlreadyExistsError("invite_already_exists")
        plain = secrets.token_urlsafe(32)
        token_hash = self._hash_invite_token(plain)
        try:
            row = await self._invites.create(
                tenant_id=tenant_id,
                invited_by_user_id=invited_by_user_id,
                email=body.email,
                role=body.role,
                token_hash=token_hash,
            )
        except EmailAlreadyRegisteredError as exc:
            raise InviteAlreadyExistsError("invite_already_exists") from exc
        return self._invite_summary(row), plain

    async def list_invites(
        self,
        tenant_id: uuid.UUID,
        *,
        status: InviteStatusEnum | None = None,
    ) -> list[InviteSummary]:
        rows = await self._invites.list_for_tenant(tenant_id, status=status)
        return [self._invite_summary(r) for r in rows]

    async def revoke_invite(
        self, tenant_id: uuid.UUID, invite_id: uuid.UUID
    ) -> InviteSummary:
        row = await self._invites.find_by_id(invite_id)
        if row is None or row.tenant_id != tenant_id:
            raise InviteNotFoundError("invite_not_found")
        if row.status != InviteStatusEnum.PENDING:
            raise InviteInvalidStateError("invite_not_pending")
        await self._invites.revoke(invite_id)
        updated = await self._invites.find_by_id(invite_id)
        assert updated is not None
        return self._invite_summary(updated)

    async def lookup_invite(self, token: str) -> dict[str, object]:
        token_hash = self._hash_invite_token(token)
        row = await self._invites.find_by_token_hash(token_hash)
        if row is None:
            raise InviteNotFoundError("invite_not_found")
        if row.status != InviteStatusEnum.PENDING:
            raise InviteInvalidStateError("invite_not_pending")
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise InviteInvalidStateError("invite_expired")
        tenant = await self._users.find_tenant(row.tenant_id)
        inviter = await self._users.find_by_id(row.invited_by_user_id)
        if tenant is None or inviter is None:
            raise InviteNotFoundError("invite_not_found")
        return {
            "email": row.email,
            "role": row.role,
            "tenant_name": tenant.display_name,
            "inviter_email": inviter.email,
            "expires_at": row.expires_at,
        }

    async def accept_invite(self, req: AcceptInviteRequest) -> AuthResponse:
        token_hash = self._hash_invite_token(req.token)
        row = await self._invites.find_by_token_hash(token_hash)
        if row is None:
            raise InviteNotFoundError("invite_not_found")
        if row.status != InviteStatusEnum.PENDING:
            raise InviteInvalidStateError("invite_not_pending")
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise InviteInvalidStateError("invite_expired")

        if await self._users.find_by_email(row.email) is not None:
            raise EmailAlreadyRegisteredError("email_already_registered")

        password_hash = hash_password(req.password)
        try:
            user = await self._users.create_user_in_existing_tenant(
                tenant_id=row.tenant_id,
                email=row.email,
                full_name=req.full_name,
                password_hash=password_hash,
                role=row.role,
            )
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError(
                "email_already_registered"
            ) from exc

        await self._invites.mark_accepted(row.id)

        tenant = await self._users.find_tenant(row.tenant_id)
        if tenant is None:
            raise InvalidTokenError("tenant_not_found")

        access, refresh, ttl = await self._issue_pair_for_user(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            role=user.role.value
            if hasattr(user.role, "value")
            else str(user.role),
        )
        return AuthResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=ttl,
            user=self._public_user(user, tenant),
        )


# --------------------------------------------------------------------------- #
# Auth hardening pack — coordination TODOs                                    #
# --------------------------------------------------------------------------- #
#
# TODO(auth-hardening): ``AuthService.sign_in`` currently issues tokens
# regardless of ``users.totp_enabled``. The spec says it should return
# 401 ``totp_required`` for users with 2FA on, so the client retries
# via the new ``POST /auth/sign-in-totp`` endpoint (implemented in
# routes.py). Because ``service.py::sign_in`` is owned by the parallel
# team-onboarding agent, this hardening pack does NOT modify it —
# merge-review will insert a single early-return check right after the
# ``email_verified`` block, roughly:
#
#     if bool(getattr(user, "totp_enabled", False)):
#         raise TotpRequiredError()
#
# The ``TotpRequiredError`` and ``sign_in_with_totp`` helper both live
# in ``auth_inhouse/totp.py``; the ``/auth/sign-in-totp`` route already
# wires the second-step flow end-to-end.
#
# TODO(auth-hardening): ``reset_password`` should call
# ``validate_password_strength(new_password)`` before hashing the new
# password. Same coordination reason — not modified here.


__all__ = [
    "AuthService",
    "InviteAlreadyExistsError",
    "InviteInvalidStateError",
    "InviteNotFoundError",
]
