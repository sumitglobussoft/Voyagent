"""Pydantic request and response models for the in-house auth routes.

Validation rules:

* Passwords are 12–128 chars and must contain at least one letter and
  one digit. No specific symbol requirement.
* Email is validated via :class:`pydantic.EmailStr`
  (requires ``email-validator``).
* ``full_name`` and ``agency_name`` are stripped and length-bounded.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _strip_and_check(value: str, *, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name}_required")
    return stripped


class _PasswordRule:
    """Mixin-style validator for password fields."""

    @staticmethod
    def validate(value: str) -> str:
        if len(value) < 12:
            raise ValueError("password_too_short")
        if len(value) > 128:
            raise ValueError("password_too_long")
        has_letter = any(c.isalpha() for c in value)
        has_digit = any(c.isdigit() for c in value)
        if not (has_letter and has_digit):
            raise ValueError("password_must_contain_letter_and_digit")
        return value


class SignUpRequest(BaseModel):
    """Body for ``POST /auth/sign-up``."""

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    agency_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _PasswordRule.validate(value)

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, value: str) -> str:
        return _strip_and_check(value, name="full_name")

    @field_validator("agency_name")
    @classmethod
    def _check_agency_name(cls, value: str) -> str:
        return _strip_and_check(value, name="agency_name")


class SignInRequest(BaseModel):
    """Body for ``POST /auth/sign-in``."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    """Body for ``POST /auth/refresh``."""

    refresh_token: str = Field(min_length=1)


class SignOutRequest(BaseModel):
    """Body for ``POST /auth/sign-out``. Refresh token is optional."""

    refresh_token: str | None = None


class PublicUser(BaseModel):
    """User shape returned by ``/auth/me`` and the auth responses."""

    id: str
    email: str
    full_name: str | None
    role: str
    tenant_id: str
    tenant_name: str
    created_at: datetime
    email_verified: bool = False


class VerifyEmailRequest(BaseModel):
    """Body for ``POST /auth/verify-email``."""

    token: str = Field(min_length=1, max_length=128)


class SendVerificationEmailResponse(BaseModel):
    """Body returned by ``POST /auth/send-verification-email``."""

    queued: bool


class VerifyEmailResponse(BaseModel):
    """Body returned by ``POST /auth/verify-email``."""

    verified: bool


class AuthResponse(BaseModel):
    """Standard auth-success response carrying both tokens + user."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: PublicUser


class TokenPairResponse(BaseModel):
    """Refresh response — no user payload."""

    access_token: str
    refresh_token: str
    expires_in: int


_VALID_ROLES = frozenset(
    {"agency_admin", "ticketing_lead", "accounting_lead", "agent", "viewer"}
)


class UpdateProfileRequest(BaseModel):
    """Body for ``PATCH /auth/profile``. All fields optional."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_and_check(value, name="full_name")


class UpdateProfileResponse(BaseModel):
    """Body returned by ``PATCH /auth/profile``."""

    model_config = ConfigDict(extra="forbid")

    user: PublicUser
    email_verification_required: bool = False


class CreateInviteRequest(BaseModel):
    """Body for ``POST /auth/invites``."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: str = Field(default="agent", max_length=32)

    @field_validator("role")
    @classmethod
    def _check_role(cls, value: str) -> str:
        if value not in _VALID_ROLES:
            raise ValueError("invalid_role")
        return value


class InviteSummary(BaseModel):
    """Public representation of one invite row."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    invited_by_user_id: str


class CreateInviteResponse(BaseModel):
    """Body returned by ``POST /auth/invites``."""

    model_config = ConfigDict(extra="forbid")

    invite: InviteSummary
    invite_link: str


class ListInvitesResponse(BaseModel):
    """Body returned by ``GET /auth/invites``."""

    model_config = ConfigDict(extra="forbid")

    items: list[InviteSummary]


class InviteLookupResponse(BaseModel):
    """Public metadata for an invite, looked up by token."""

    model_config = ConfigDict(extra="forbid")

    email: str
    role: str
    tenant_name: str
    inviter_email: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    """Body for ``POST /auth/accept-invite``."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _PasswordRule.validate(value)

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, value: str) -> str:
        return _strip_and_check(value, name="full_name")


class RequestPasswordResetRequest(BaseModel):
    """Body for ``POST /auth/request-password-reset``."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class RequestPasswordResetResponse(BaseModel):
    """Body returned by ``POST /auth/request-password-reset``."""

    model_config = ConfigDict(extra="forbid")

    queued: bool
    # Only populated when the dev / test bypass flag is on. In prod this
    # is always ``None`` so the endpoint does not leak account existence.
    debug_token: str | None = None


class ResetPasswordRequest(BaseModel):
    """Body for ``POST /auth/reset-password``."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _PasswordRule.validate(value)


class ResetPasswordResponse(BaseModel):
    """Body returned by ``POST /auth/reset-password``."""

    model_config = ConfigDict(extra="forbid")

    reset: bool


# --------------------------------------------------------------------------- #
# Auth hardening pack: TOTP + API keys + sign-in-totp                         #
# Append-only — do not reorder the rest of this file.                         #
# --------------------------------------------------------------------------- #


class TotpSetupResponse(BaseModel):
    """Body returned by ``POST /auth/totp/setup``."""

    model_config = ConfigDict(extra="forbid")

    secret: str
    otpauth_url: str


class TotpVerifyRequest(BaseModel):
    """Body for ``POST /auth/totp/verify``."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)


class TotpDisableRequest(BaseModel):
    """Body for ``POST /auth/totp/disable``."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=8)


class TotpStatusResponse(BaseModel):
    """Body returned by the verify / disable endpoints."""

    model_config = ConfigDict(extra="forbid")

    totp_enabled: bool


class SignInTotpRequest(BaseModel):
    """Body for ``POST /auth/sign-in-totp``.

    Used as the second step when the user has 2FA enabled. The regular
    ``/auth/sign-in`` endpoint returns 401 ``totp_required`` in that
    case and the client replays the credentials plus the 6-digit code
    here.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    totp_code: str = Field(min_length=6, max_length=8)


class CreateApiKeyRequest(BaseModel):
    """Body for ``POST /auth/api-keys``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return _strip_and_check(value, name="name")


class ApiKeySummary(BaseModel):
    """Metadata for one API key — never carries the plaintext."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class CreateApiKeyResponse(BaseModel):
    """Body returned by ``POST /auth/api-keys``.

    ``key`` is the full ``vy_<prefix>_<body>`` string — displayed to
    the user exactly ONCE. After this response we only ever return
    :class:`ApiKeySummary`.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    warning: str = (
        "Save this key now — it will never be shown again."
    )
    api_key: ApiKeySummary


class ListApiKeysResponse(BaseModel):
    """Body returned by ``GET /auth/api-keys``."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApiKeySummary]


__all__ = [
    "AcceptInviteRequest",
    "ApiKeySummary",
    "AuthResponse",
    "CreateApiKeyRequest",
    "CreateApiKeyResponse",
    "CreateInviteRequest",
    "CreateInviteResponse",
    "InviteLookupResponse",
    "InviteSummary",
    "ListApiKeysResponse",
    "ListInvitesResponse",
    "PublicUser",
    "RefreshRequest",
    "RequestPasswordResetRequest",
    "RequestPasswordResetResponse",
    "ResetPasswordRequest",
    "ResetPasswordResponse",
    "SendVerificationEmailResponse",
    "SignInRequest",
    "SignInTotpRequest",
    "TotpDisableRequest",
    "TotpSetupResponse",
    "TotpStatusResponse",
    "TotpVerifyRequest",
    "SignOutRequest",
    "SignUpRequest",
    "TokenPairResponse",
    "UpdateProfileRequest",
    "UpdateProfileResponse",
    "VerifyEmailRequest",
    "VerifyEmailResponse",
]
