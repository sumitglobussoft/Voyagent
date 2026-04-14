"""Configuration for the BSP India driver.

Values are loaded from environment variables prefixed ``VOYAGENT_BSP_INDIA_``.
Secrets (BSPlink password) are held in :class:`SecretStr` to reduce
accidental logging exposure.

Two file-acquisition modes are supported:

* ``file_source_dir`` — the tenant drops HAF files into a shared
  directory. This is the v0 preferred path; SFTP and web-form portals
  are real integration projects and out of scope for v0.
* HTTP fetch against ``bsplink_base_url`` — scaffolded only; the client
  raises :class:`PermanentError` explaining the feature gap.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BSPIndiaConfig(BaseSettings):
    """Runtime configuration for :class:`BSPIndiaDriver`.

    Read from the process environment on construction. Intended to be
    constructed once per tenant registration and passed into the driver.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_BSP_INDIA_",
        case_sensitive=False,
        extra="ignore",
    )

    bsplink_base_url: str = Field(
        default="https://www.bsplink.iata.org",
        description=(
            "IATA BSPlink portal base URL. BSPlink is the official settlement "
            "portal — v0 scaffolds against its shape even though production "
            "integration is SFTP + HTML form posts."
        ),
    )
    agent_iata_code: str = Field(
        default="",
        description=(
            "Tenant's IATA agency code (a.k.a. IATA numeric code). "
            "Required; used to filter HAF records and form the file-name prefix."
        ),
    )
    username: str = Field(
        default="",
        description="BSPlink username for this tenant.",
    )
    password: SecretStr = Field(
        default=SecretStr(""),
        description="BSPlink password. Held in SecretStr.",
    )
    file_source_dir: str | None = Field(
        default=None,
        description=(
            "Optional local directory where HAF files are dropped by upstream "
            "automation. When set, the driver reads from disk instead of "
            "attempting a network fetch."
        ),
    )
    timeout_seconds: int = Field(
        default=60,
        gt=0,
        description="Per-request HTTP timeout in seconds (scaffolded HTTP path).",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum retries for retriable errors.",
    )


__all__ = ["BSPIndiaConfig"]
