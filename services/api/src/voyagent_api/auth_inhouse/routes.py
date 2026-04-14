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

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
)
from .models import (
    AuthResponse,
    PublicUser,
    RefreshRequest,
    SendVerificationEmailResponse,
    SignInRequest,
    SignOutRequest,
    SignUpRequest,
    TokenPairResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from .service import AuthService
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


__all__ = ["router"]
