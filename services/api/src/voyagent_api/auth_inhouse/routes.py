"""HTTP routes for the in-house auth subsystem.

Mounted at ``/auth`` from this module; the API process re-mounts it at
``/api/auth`` from outside.
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
    SignInRequest,
    SignOutRequest,
    SignUpRequest,
    TokenPairResponse,
)
from .service import AuthService
from .tokens import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
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


__all__ = ["router"]
