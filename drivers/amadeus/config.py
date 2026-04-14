"""Configuration for the Amadeus driver.

Values are loaded from environment variables prefixed `VOYAGENT_AMADEUS_`.
Secrets are held in `SecretStr` to reduce accidental logging exposure.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AmadeusConfig(BaseSettings):
    """Runtime configuration for :class:`AmadeusDriver`.

    Read from the process environment on construction. Intended to be
    constructed once per tenant registration and passed into the driver.
    All fields default to safe sandbox values so tests never hit prod.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_AMADEUS_",
        case_sensitive=False,
        extra="ignore",
    )

    api_base: str = Field(
        default="https://test.api.amadeus.com",
        description="Amadeus Self-Service base URL. Use test.* for sandbox, api.* for prod.",
    )
    client_id: str = Field(
        default="",
        description="OAuth2 client_id from developers.amadeus.com. Required for live calls.",
    )
    client_secret: SecretStr = Field(
        default=SecretStr(""),
        description="OAuth2 client_secret from developers.amadeus.com.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Per-request HTTP timeout in seconds.",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum retries for retriable errors (TransientError, RateLimitError).",
    )


__all__ = ["AmadeusConfig"]
