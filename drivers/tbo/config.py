"""Configuration for the TBO hotel driver.

Loaded from ``VOYAGENT_TBO_*`` environment variables. Secrets wrapped in
``SecretStr`` so they do not leak into logs. Defaults point at the
documented TBO staging base URL; production deployments override via
``VOYAGENT_TBO_API_BASE``.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TBOConfig(BaseSettings):
    """Runtime configuration for :class:`TBODriver`."""

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_TBO_",
        case_sensitive=False,
        extra="ignore",
    )

    # TBO publishes their Hotels REST API under a few base URLs; the one
    # below is the public staging host referenced in TBO partner docs.
    # Production tenants override via VOYAGENT_TBO_API_BASE.
    api_base: str = Field(
        default="https://api.tbotechnology.in/TBOHolidays_HotelAPI",
        description="TBO Hotels API base URL. Overridable per tenant.",
    )
    username: str = Field(
        default="",
        description="TBO partner username. Required for live calls.",
    )
    password: SecretStr = Field(
        default=SecretStr(""),
        description="TBO partner password.",
    )
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0)


__all__ = ["TBOConfig"]
