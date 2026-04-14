"""Configuration for the in-house auth subsystem.

All values are read from the environment under the ``VOYAGENT_AUTH_``
prefix. The settings object is constructed once per process via
:func:`get_auth_settings` and cached with :func:`functools.lru_cache`
so tests can override the secret by clearing the cache.

The single mandatory value is ``VOYAGENT_AUTH_SECRET``. Booting without
it is a configuration bug and we refuse to come up rather than fall
back to a development default.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """In-house auth configuration loaded from ``VOYAGENT_AUTH_*`` env vars.

    Attributes:
      * ``secret`` — HS256 signing secret. Must be at least 32 bytes long.
      * ``access_ttl_seconds`` — JWT lifetime in seconds (default 1 h).
      * ``refresh_ttl_seconds`` — refresh-token lifetime (default 30 days).
      * ``issuer`` / ``audience`` — JWT iss/aud claim values.
      * ``argon2_*`` — argon2id cost parameters.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_AUTH_",
        case_sensitive=False,
        extra="ignore",
    )

    secret: SecretStr = Field(...)
    access_ttl_seconds: int = Field(default=3600, ge=60)
    refresh_ttl_seconds: int = Field(default=30 * 24 * 3600, ge=3600)
    issuer: str = Field(default="voyagent")
    audience: str = Field(default="voyagent-api")
    argon2_time_cost: int = Field(default=2, ge=1)
    argon2_memory_cost: int = Field(default=102_400, ge=8_192)
    argon2_parallelism: int = Field(default=8, ge=1)

    @field_validator("secret")
    @classmethod
    def _validate_secret_length(cls, value: SecretStr) -> SecretStr:
        """Refuse boot on a too-short signing secret."""
        raw = value.get_secret_value()
        if len(raw.encode("utf-8")) < 32:
            raise ValueError(
                "VOYAGENT_AUTH_SECRET must be at least 32 bytes long"
            )
        return value


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    """Return the process-wide :class:`AuthSettings` instance.

    Cached so settings are constructed exactly once. Tests should call
    ``get_auth_settings.cache_clear()`` after mutating env vars.
    """
    return AuthSettings()  # type: ignore[call-arg]


__all__ = ["AuthSettings", "get_auth_settings"]
