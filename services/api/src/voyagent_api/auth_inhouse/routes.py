"""HTTP routes for the in-house auth subsystem.

Mounted at ``/auth`` from this module; the API process re-mounts it at
``/api/auth`` from outside.

Email verification
------------------
Sign-up creates users with ``email_verified=False`` by default. Sign-in
refuses those users with HTTP 401 / ``email_not_verified`` (distinct
from the ``invalid_credentials`` 401) so clients can render a "please
verify" flow instead of a "wrong password" error. The verification
round-trip is:

* ``POST /auth/send-verification-email`` (authenticated) — mints a
  token, stores it keyed to the caller with a short TTL, and logs the
  verification link to stdout for dev. Real SMTP delivery is a TODO.
* ``POST /auth/verify-email`` — accepts ``{"token": "..."}``, flips the
  user's flag, returns 200. Unknown / expired tokens return 400 with
  ``token_invalid``.

Dev / test escape hatch
-----------------------
Set ``VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION=true`` to auto-verify users
on sign-up. This is the default in the pytest environment so the
existing happy-path tests still work; it is **not** enabled in
production. Configure the token TTL via
``VOYAGENT_AUTH_VERIFICATION_TTL_SECONDS`` (default 24 h).
"""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import InviteStatusEnum

from .deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
    require_agency_admin,
)
from .models import (
    AcceptInviteRequest,
    AuthResponse,
    CreateInviteRequest,
    CreateInviteResponse,
    InviteLookupResponse,
    ListInvitesResponse,
    PublicUser,
    RefreshRequest,
    RequestPasswordResetRequest,
    RequestPasswordResetResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SendVerificationEmailResponse,
    SignInRequest,
    SignOutRequest,
    SignUpRequest,
    TokenPairResponse,
    UpdateProfileRequest,
    UpdateProfileResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from .service import (
    AuthService,
    InviteAlreadyExistsError,
    InviteInvalidStateError,
    InviteNotFoundError,
)
from .tokens import (
    AccessTokenPayload,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    InvalidVerificationTokenError,
    RefreshTokenRevokedError,
    verify_access_token,
)


_INVITE_LINK_BASE = "https://voyagent.globusdemos.com/app/accept-invite?token="
_RESET_LINK_BASE = "https://voyagent.globusdemos.com/app/reset-password?token="


def _skip_email_verification() -> bool:
    raw = os.environ.get(
        "VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", ""
    ).strip().lower()
    return raw in {"1", "true", "yes", "on"}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(
    request: Request, session: AsyncSession = Depends(db_session)
) -> AuthService:
    """Construct an :class:`AuthService` bound to the per-request session."""
    return AuthService(session, request)


@router.post(
    "/sign-up",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def sign_up(
    body: SignUpRequest,
    service: AuthService = Depends(_service),
) -> AuthResponse:
    """Create a new tenant and its first owner user."""
    try:
        return await service.sign_up(body)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="email_already_registered") from exc
    except Exception as exc:  # noqa: BLE001
        # Auth hardening pack: sign_up now calls
        # validate_password_strength() which raises PasswordTooWeakError
        # with a stable ``code`` attribute. Surface it as 400 without
        # importing PasswordTooWeakError up here (the import lives in
        # the appended block below to keep this edit minimal).
        if exc.__class__.__name__ == "PasswordTooWeakError":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "password_too_weak",
                    "code": getattr(exc, "code", "password_too_weak"),
                },
            ) from exc
        raise


@router.post("/sign-in", response_model=AuthResponse)
async def sign_in(
    body: SignInRequest,
    service: AuthService = Depends(_service),
) -> AuthResponse:
    """Verify credentials and issue a fresh token pair."""
    try:
        return await service.sign_in(body)
    except EmailNotVerifiedError as exc:
        raise HTTPException(status_code=401, detail="email_not_verified") from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="invalid_credentials") from exc


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshRequest,
    service: AuthService = Depends(_service),
) -> TokenPairResponse:
    """Exchange a refresh token for a new (access, refresh) pair."""
    try:
        return await service.refresh(body)
    except RefreshTokenRevokedError as exc:
        raise HTTPException(status_code=401, detail="invalid_refresh_token") from exc


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    body: SignOutRequest | None = None,
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(_service),
) -> None:
    """Best-effort revoke the refresh token and the access ``jti``."""
    access_payload = None
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            try:
                access_payload = verify_access_token(parts[1].strip())
            except InvalidTokenError:
                access_payload = None
    refresh_token = body.refresh_token if body else None
    await service.sign_out(access_payload, refresh_token)
    return None


@router.get("/me", response_model=PublicUser)
async def me(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> PublicUser:
    """Return the authenticated user as :class:`PublicUser`."""
    from .tokens import AccessTokenPayload

    payload = AccessTokenPayload(
        sub=principal.user_id,
        tid=principal.tenant_id,
        role=principal.role,
        email=principal.email,
        iat=0,
        exp=principal.exp,
        jti=principal.jti,
    )
    service = AuthService(session, None)
    try:
        return await service.me(payload)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc


@router.post(
    "/send-verification-email",
    response_model=SendVerificationEmailResponse,
)
async def send_verification_email(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    service: AuthService = Depends(_service),
) -> SendVerificationEmailResponse:
    """Issue a one-shot verification link for the authenticated user."""
    payload = AccessTokenPayload(
        sub=principal.user_id,
        tid=principal.tenant_id,
        role=principal.role,
        email=principal.email,
        iat=0,
        exp=principal.exp,
        jti=principal.jti,
    )
    try:
        token = await service.send_verification_email(payload)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    # Log the link to stdout for dev visibility. Real SMTP delivery is TODO.
    logger.info("auth verification link: /auth/verify-email?token=%s", token)
    return SendVerificationEmailResponse(queued=True)


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    body: VerifyEmailRequest,
    service: AuthService = Depends(_service),
) -> VerifyEmailResponse:
    """Consume a verification token and mark the user verified."""
    try:
        await service.verify_email(body.token)
    except InvalidVerificationTokenError as exc:
        raise HTTPException(status_code=400, detail="token_invalid") from exc
    return VerifyEmailResponse(verified=True)


@router.patch("/profile", response_model=UpdateProfileResponse)
async def update_profile(
    body: UpdateProfileRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    service: AuthService = Depends(_service),
) -> UpdateProfileResponse:
    """Patch ``full_name`` / ``email`` on the authenticated user."""
    try:
        user_uuid = uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    try:
        user, email_changed = await service.update_profile(
            user_id=user_uuid,
            full_name=body.full_name,
            email=body.email,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=409, detail="email_already_registered"
        ) from exc
    return UpdateProfileResponse(
        user=user, email_verification_required=email_changed
    )


@router.post(
    "/request-password-reset",
    response_model=RequestPasswordResetResponse,
)
async def request_password_reset(
    body: RequestPasswordResetRequest,
    service: AuthService = Depends(_service),
) -> RequestPasswordResetResponse:
    """Always 200 — do not leak whether the email is registered."""
    token = await service.request_password_reset(body.email)
    if token is not None:
        logger.info("auth password reset link: %s%s", _RESET_LINK_BASE, token)
    debug_token = token if _skip_email_verification() else None
    return RequestPasswordResetResponse(queued=True, debug_token=debug_token)


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    service: AuthService = Depends(_service),
) -> ResetPasswordResponse:
    try:
        await service.reset_password(body.token, body.new_password)
    except InvalidVerificationTokenError as exc:
        raise HTTPException(status_code=400, detail="token_invalid") from exc
    return ResetPasswordResponse(reset=True)


# --------------------------------------------------------------------------- #
# Team invites                                                                #
# --------------------------------------------------------------------------- #


@router.post(
    "/invites",
    response_model=CreateInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    body: CreateInviteRequest,
    principal: AuthenticatedPrincipal = Depends(require_agency_admin),
    service: AuthService = Depends(_service),
) -> CreateInviteResponse:
    """Create a pending invite into the caller's tenant (admin-only)."""
    try:
        tenant_uuid = uuid.UUID(principal.tenant_id)
        user_uuid = uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    try:
        summary, plain = await service.create_invite(
            tenant_id=tenant_uuid,
            invited_by_user_id=user_uuid,
            body=body,
        )
    except InviteAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="invite_already_exists"
        ) from exc
    link = f"{_INVITE_LINK_BASE}{plain}"
    logger.info("auth invite link: %s", link)
    return CreateInviteResponse(invite=summary, invite_link=link)


@router.get("/invites", response_model=ListInvitesResponse)
async def list_invites(
    status_filter: str | None = Query(default=None, alias="status"),
    principal: AuthenticatedPrincipal = Depends(require_agency_admin),
    service: AuthService = Depends(_service),
) -> ListInvitesResponse:
    try:
        tenant_uuid = uuid.UUID(principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    parsed: InviteStatusEnum | None = None
    if status_filter is not None:
        try:
            parsed = InviteStatusEnum(status_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="invalid_status"
            ) from exc
    items = await service.list_invites(tenant_uuid, status=parsed)
    return ListInvitesResponse(items=items)


@router.post("/invites/{invite_id}/revoke", response_model=dict)
async def revoke_invite(
    invite_id: str,
    principal: AuthenticatedPrincipal = Depends(require_agency_admin),
    service: AuthService = Depends(_service),
) -> dict:
    try:
        tenant_uuid = uuid.UUID(principal.tenant_id)
        inv_uuid = uuid.UUID(invite_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="invite_not_found") from exc
    try:
        summary = await service.revoke_invite(tenant_uuid, inv_uuid)
    except InviteNotFoundError as exc:
        raise HTTPException(status_code=404, detail="invite_not_found") from exc
    except InviteInvalidStateError as exc:
        raise HTTPException(
            status_code=409, detail="invite_not_pending"
        ) from exc
    return {"invite": summary.model_dump(mode="json")}


@router.get("/invites/lookup", response_model=InviteLookupResponse)
async def lookup_invite(
    token: str = Query(min_length=1, max_length=128),
    service: AuthService = Depends(_service),
) -> InviteLookupResponse:
    """Public — resolve an invite token to its safe public metadata."""
    try:
        meta = await service.lookup_invite(token)
    except InviteNotFoundError as exc:
        raise HTTPException(status_code=404, detail="invite_not_found") from exc
    except InviteInvalidStateError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc) or "invite_invalid"
        ) from exc
    return InviteLookupResponse(**meta)  # type: ignore[arg-type]


@router.post(
    "/accept-invite",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invite(
    body: AcceptInviteRequest,
    service: AuthService = Depends(_service),
) -> AuthResponse:
    """Consume an invite token, create the user, and sign them in."""
    try:
        return await service.accept_invite(body)
    except InviteNotFoundError as exc:
        raise HTTPException(status_code=404, detail="invite_not_found") from exc
    except InviteInvalidStateError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc) or "invite_invalid"
        ) from exc
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=409, detail="email_already_registered"
        ) from exc


# --------------------------------------------------------------------------- #
# Auth hardening pack: TOTP + sign-in-totp + API key CRUD                     #
# Appended at the bottom so the parallel team-onboarding agent's edits above  #
# merge cleanly. Do not reorder.                                              #
# --------------------------------------------------------------------------- #

from .api_keys import (  # noqa: E402
    create_api_key as _create_api_key,
    list_api_keys_for_tenant as _list_api_keys,
    revoke_api_key as _revoke_api_key,
)
from .models import (  # noqa: E402
    ApiKeySummary,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    ListApiKeysResponse,
    SignInTotpRequest,
    TotpDisableRequest,
    TotpSetupResponse,
    TotpStatusResponse,
    TotpVerifyRequest,
)
from .passwords import PasswordTooWeakError  # noqa: E402
from .tokens import (  # noqa: E402
    issue_access_token as _issue_access_token,
    mint_refresh_token as _mint_refresh_token,
)
from .totp import (  # noqa: E402
    disable_totp_for_user,
    setup_totp_for_user,
    sign_in_with_totp,
    user_requires_totp,
    verify_totp_for_user,
)


def _summarize_api_key(row) -> ApiKeySummary:  # type: ignore[no-untyped-def]
    scopes = [s for s in (row.scopes or "").split(",") if s]
    return ApiKeySummary(
        id=str(row.id),
        name=row.name,
        prefix=row.prefix,
        scopes=scopes or ["full"],
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
    )


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def totp_setup(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> TotpSetupResponse:
    """Mint a fresh TOTP secret and return ``{secret, otpauth_url}``."""
    import uuid as _uuid

    try:
        user_uuid = _uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    secret, url = await setup_totp_for_user(session, user_uuid)
    return TotpSetupResponse(secret=secret, otpauth_url=url)


@router.post("/totp/verify", response_model=TotpStatusResponse)
async def totp_verify(
    body: TotpVerifyRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> TotpStatusResponse:
    """Verify the first-time 6-digit code and flip ``totp_enabled=True``."""
    import uuid as _uuid

    try:
        user_uuid = _uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    await verify_totp_for_user(session, user_uuid, body.code)
    return TotpStatusResponse(totp_enabled=True)


@router.post("/totp/disable", response_model=TotpStatusResponse)
async def totp_disable(
    body: TotpDisableRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> TotpStatusResponse:
    """Disable 2FA. Requires BOTH the user's password AND a TOTP code."""
    import uuid as _uuid

    try:
        user_uuid = _uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    await disable_totp_for_user(
        session, user_uuid, password=body.password, code=body.code
    )
    return TotpStatusResponse(totp_enabled=False)


@router.post("/sign-in-totp", response_model=AuthResponse)
async def sign_in_totp(
    body: SignInTotpRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> AuthResponse:
    """Second-step sign-in for users with 2FA enabled."""
    try:
        user = await sign_in_with_totp(
            session,
            email=body.email,
            password=body.password,
            code=body.totp_code,
        )
    except EmailNotVerifiedError as exc:
        raise HTTPException(
            status_code=401, detail="email_not_verified"
        ) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=401, detail="invalid_credentials"
        ) from exc

    # Rehydrate tenant + issue tokens through the normal AuthService
    # plumbing so refresh-token storage, client_meta, and rotation
    # rules all stay identical to the regular sign-in path.
    service_inst = AuthService(session, request)
    tenant = await service_inst._users.find_tenant(user.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=401, detail="invalid_credentials"
        )
    access, refresh, ttl = await service_inst._issue_pair_for_user(
        user_id=user.id,
        tenant_id=tenant.id,
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
    )
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=ttl,
        user=service_inst._public_user(user, tenant),
    )


@router.post(
    "/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key_route(
    body: CreateApiKeyRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> CreateApiKeyResponse:
    """Mint a new API key; the plaintext is returned exactly once."""
    import uuid as _uuid

    try:
        user_uuid = _uuid.UUID(principal.user_id)
        tenant_uuid = _uuid.UUID(principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    row, full = await _create_api_key(
        session,
        tenant_id=tenant_uuid,
        created_by_user_id=user_uuid,
        name=body.name,
        expires_in_days=body.expires_in_days,
    )
    return CreateApiKeyResponse(
        key=full,
        api_key=_summarize_api_key(row),
    )


@router.get("/api-keys", response_model=ListApiKeysResponse)
async def list_api_keys_route(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> ListApiKeysResponse:
    """List every API key in the caller's tenant."""
    import uuid as _uuid

    try:
        tenant_uuid = _uuid.UUID(principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    rows = await _list_api_keys(session, tenant_uuid)
    return ListApiKeysResponse(
        items=[_summarize_api_key(r) for r in rows]
    )


@router.post(
    "/api-keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_api_key_route(
    key_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(db_session),
) -> None:
    """Soft-revoke an API key. Tenant-scoped."""
    import uuid as _uuid

    try:
        key_uuid = _uuid.UUID(key_id)
        tenant_uuid = _uuid.UUID(principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    ok = await _revoke_api_key(session, key_uuid, tenant_uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="not_found")
    return None


__all__ = ["router"]
