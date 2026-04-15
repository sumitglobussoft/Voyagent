"""Per-tenant runtime settings.

One row per tenant overrides runtime defaults: agent model, prompt
suffix, rate limits, locale. Absence of a row means "use env defaults"
— the runtime falls back gracefully without requiring eager seeding.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDType


class TenantSettingsRow(Base, Timestamps):
    """One row per tenant with agent-runtime overrides."""

    __tablename__ = "tenant_settings"

    # tenant_id is both the PK and FK into tenants.id — one row per tenant.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        primary_key=True,
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_prompt_suffix: Mapped[str | None] = mapped_column(Text, nullable=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="60", default=60
    )
    rate_limit_per_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1000", default=1000
    )
    daily_token_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locale: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="en", default="en"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="UTC", default="UTC"
    )
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="INR", default="INR"
    )

    __table_args__ = (
        CheckConstraint(
            "length(default_currency) = 3",
            name="ck_tenant_settings_currency_len",
        ),
        CheckConstraint(
            "rate_limit_per_minute > 0",
            name="ck_tenant_settings_rpm_pos",
        ),
        CheckConstraint(
            "rate_limit_per_hour > 0",
            name="ck_tenant_settings_rph_pos",
        ),
    )


__all__ = ["TenantSettingsRow"]
