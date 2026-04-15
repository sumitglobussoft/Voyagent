"""Tenant runtime settings — GET / PATCH surface.

One row per tenant. GET auto-creates a default row on first fetch so
the UI never has to care about "row absent" as a special case; PATCH
is admin-only and partial (unset fields are left alone).

The supported model list is hardcoded here (mirroring the orchestrator's
enforcement) so an invalid override cannot be persisted in the first
place — the orchestrator's fallback path only covers corrupted rows
from older deployments.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import TenantSettingsRow

from .auth_inhouse.deps import (
    AuthenticatedPrincipal,
    db_session,
    get_current_principal,
    require_agency_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenant-settings", tags=["tenant-settings"])


SUPPORTED_MODELS = frozenset(
    {
        "claude-sonnet-4-5",
        "claude-opus-4-6",
        "claude-haiku-4-5-20251001",
    }
)

SUPPORTED_LOCALES = frozenset({"en", "hi"})


SupportedModel = Literal[
    "claude-sonnet-4-5",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
]


class TenantSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    model: str | None = None
    system_prompt_suffix: str | None = None
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    daily_token_budget: int | None = None
    locale: str
    timezone: str
    default_currency: str


class TenantSettingsPatchRequest(BaseModel):
    """PATCH body. Omitted fields = leave alone; explicit nulls clear."""

    model_config = ConfigDict(extra="forbid")

    model: SupportedModel | None = None
    system_prompt_suffix: str | None = Field(default=None, max_length=10_000)
    rate_limit_per_minute: int | None = Field(default=None, gt=0, le=10_000)
    rate_limit_per_hour: int | None = Field(default=None, gt=0, le=1_000_000)
    daily_token_budget: int | None = Field(default=None, gt=0)
    locale: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    default_currency: str | None = None

    @field_validator("locale")
    @classmethod
    def _check_locale(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in SUPPORTED_LOCALES:
            raise ValueError(
                f"locale must be one of {sorted(SUPPORTED_LOCALES)}"
            )
        return v

    @field_validator("default_currency")
    @classmethod
    def _check_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if (
            len(v) != 3
            or not v.isascii()
            or not v.isalpha()
            or not v.isupper()
        ):
            raise ValueError("default_currency must be a 3-letter ISO code")
        return v


def _tenant_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        ) from exc


def _row_to_response(row: TenantSettingsRow) -> TenantSettingsResponse:
    return TenantSettingsResponse(
        tenant_id=str(row.tenant_id),
        model=row.model,
        system_prompt_suffix=row.system_prompt_suffix,
        rate_limit_per_minute=row.rate_limit_per_minute,
        rate_limit_per_hour=row.rate_limit_per_hour,
        daily_token_budget=row.daily_token_budget,
        locale=row.locale,
        timezone=row.timezone,
        default_currency=row.default_currency,
    )


async def _load_or_create(
    db: AsyncSession, tenant_uuid: uuid.UUID
) -> TenantSettingsRow:
    row = (
        await db.execute(
            select(TenantSettingsRow).where(
                TenantSettingsRow.tenant_id == tenant_uuid
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = TenantSettingsRow(tenant_id=tenant_uuid)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> TenantSettingsResponse:
    """Return the current tenant's settings, creating defaults if absent."""
    tenant_uuid = _tenant_uuid(principal)
    row = await _load_or_create(db, tenant_uuid)
    return _row_to_response(row)


@router.patch("", response_model=TenantSettingsResponse)
async def patch_tenant_settings(
    body: TenantSettingsPatchRequest,
    principal: AuthenticatedPrincipal = Depends(require_agency_admin),
    db: AsyncSession = Depends(db_session),
) -> TenantSettingsResponse:
    """Admin-only partial update. Omitted fields are left alone."""
    tenant_uuid = _tenant_uuid(principal)
    row = await _load_or_create(db, tenant_uuid)

    patch = body.model_dump(exclude_unset=True)
    for field_name, value in patch.items():
        setattr(row, field_name, value)

    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


__all__ = ["router", "SUPPORTED_MODELS"]
