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

from pydantic import BaseModel, EmailStr, Field, field_validator


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


__all__ = [
    "AuthResponse",
    "PublicUser",
    "RefreshRequest",
    "SignInRequest",
    "SignOutRequest",
    "SignUpRequest",
    "TokenPairResponse",
]
