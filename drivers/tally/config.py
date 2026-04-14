"""Configuration for the Tally driver.

Values are loaded from environment variables prefixed ``VOYAGENT_TALLY_``.
Secrets (basic-auth password) are held in :class:`SecretStr` to reduce
accidental logging exposure.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TallyConfig(BaseSettings):
    """Runtime configuration for :class:`TallyDriver`.

    Read from the process environment on construction. Intended to be
    constructed once per tenant registration and passed into the driver.
    Tally Prime ~3.x supports optional HTTP basic auth on the gateway;
    older versions ignore the credentials silently.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_TALLY_",
        case_sensitive=False,
        extra="ignore",
    )

    gateway_url: str = Field(
        default="http://localhost:9000",
        description="Tally Gateway Server base URL. Usually http://localhost:9000 on the desktop host.",
    )
    company_name: str = Field(
        default="",
        description=(
            "Tally company name, exactly as shown in Tally's 'List of Companies'. "
            "Required for every request (Tally binds commands to the active company)."
        ),
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Per-request HTTP timeout in seconds.",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum retries for retriable errors (TransientError, network blips).",
    )
    basic_auth_user: str | None = Field(
        default=None,
        description="Optional HTTP basic auth user. Tally Prime ~3.x supports this; earlier versions do not.",
    )
    basic_auth_password: SecretStr | None = Field(
        default=None,
        description="Optional HTTP basic auth password. Paired with basic_auth_user.",
    )


__all__ = ["TallyConfig"]
