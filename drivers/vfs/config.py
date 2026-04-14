"""Configuration for the VFS driver.

Real deployments source credentials from the tenant credential store
and pass a reference (``tenant_credentials_ref``) through the runner —
the driver itself never transports the raw password. The env-var
fields below are a *dev-only* convenience for local runs.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from schemas.canonical import CountryCode  # noqa: F401 — re-export-adjacent use


class VFSConfig(BaseSettings):
    """Runtime configuration for :class:`VFSDriver`.

    Credentials are expected to arrive via the tenant credential store
    in production. Environment variables are supported so a developer
    can exercise the driver locally without plumbing the secrets flow.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_VFS_",
        case_sensitive=False,
        extra="ignore",
    )

    destination_country: str | None = Field(
        default=None,
        description=(
            "Default destination country (ISO-3166-1 alpha-2). May be "
            "overridden per-call. When None, each driver call must "
            "supply destination itself."
        ),
    )
    username: str | None = Field(
        default=None,
        description="Dev-only username. Real tenants plumb credentials via tenant_credentials_ref.",
    )
    password: SecretStr | None = Field(
        default=None,
        description="Dev-only password. Never logged.",
    )
    credentials_ref: str = Field(
        default="secrets://vfs/default",
        description=(
            "Opaque reference passed on every job. The worker's credential "
            "resolver maps this to real credentials at dispatch time."
        ),
    )
    job_timeout_seconds: float = Field(
        default=180.0,
        gt=0,
        description="Default timeout for each browser-runner job.",
    )


__all__ = ["VFSConfig"]
