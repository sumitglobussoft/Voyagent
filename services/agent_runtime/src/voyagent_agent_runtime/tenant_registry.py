"""Per-tenant driver registry.

Today the runtime keeps a single, process-wide :class:`DriverRegistry`
constructed from env vars. That's fine for solo-dev but incompatible with
multi-tenancy: every tenant would share the same Amadeus / Tally
credentials.

:class:`TenantRegistry` replaces that with a lazy, per-tenant cache. The
first call to :meth:`TenantRegistry.get` for a tenant resolves the
tenant's credentials via a pluggable :class:`CredentialResolver`,
instantiates fresh driver instances bound to those credentials, and
returns a :class:`DriverRegistry` exactly like the old code path. The
registry is cached with an LRU cap so long-running processes don't leak
memory for tenants seen once.

The :class:`CredentialResolver` protocol is deliberately narrow:
``(tenant_id, provider) -> credentials dict | None``. The two
implementations shipped here are:

* :class:`EnvCredentialResolver` — reads ``VOYAGENT_AMADEUS_*`` env vars
  just like the old :func:`build_default_registry`. Every tenant gets the
  same credentials. Useful for solo-dev before a proper credential vault
  is wired up.
* :class:`StorageCredentialResolver` — reads decrypted
  :class:`TenantCredential` rows when :mod:`schemas.storage` is
  available. Falls back to :class:`EnvCredentialResolver` otherwise, so
  the auth layer keeps working while the persistence / KMS agents are
  in flight.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Protocol

from schemas.canonical import EntityId

from .drivers import DriverRegistry

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Credential resolver protocol                                                #
# --------------------------------------------------------------------------- #


CredentialResolver = Callable[
    [EntityId, str], Awaitable[dict[str, Any] | None]
]
"""Async callable: ``(tenant_id, provider) -> credentials`` or ``None``.

Implementations return a plain dict shaped for the target driver's
config (e.g. ``{"client_id": "...", "client_secret": "..."}``). Returning
``None`` indicates the tenant has no credentials for that provider; the
registry treats that as "don't instantiate a driver of this kind".
"""


class _ResolverLike(Protocol):
    async def __call__(
        self, tenant_id: EntityId, provider: str
    ) -> dict[str, Any] | None: ...


# --------------------------------------------------------------------------- #
# Env-based resolver — solo-dev fallback                                      #
# --------------------------------------------------------------------------- #


class EnvCredentialResolver:
    """Resolve every tenant's credentials from process environment variables.

    Returns the same credential dict for every ``tenant_id`` — this is
    explicitly single-tenant behaviour and exists only so the auth +
    runtime plumbing can be exercised without a credential vault.

    Supported providers:
      * ``amadeus`` — ``VOYAGENT_AMADEUS_CLIENT_ID``,
        ``VOYAGENT_AMADEUS_CLIENT_SECRET``, ``VOYAGENT_AMADEUS_API_BASE``.
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    async def __call__(
        self, tenant_id: EntityId, provider: str
    ) -> dict[str, Any] | None:
        if provider == "amadeus":
            client_id = self._env.get("VOYAGENT_AMADEUS_CLIENT_ID", "")
            client_secret = self._env.get("VOYAGENT_AMADEUS_CLIENT_SECRET", "")
            api_base = self._env.get(
                "VOYAGENT_AMADEUS_API_BASE", "https://test.api.amadeus.com"
            )
            # Return credentials even when the client pair is empty — the
            # driver itself will surface an auth error on first call, which
            # is the correct failure mode for a mis-configured tenant.
            return {
                "client_id": client_id,
                "client_secret": client_secret,
                "api_base": api_base,
            }
        if provider == "tbo":
            username = self._env.get("VOYAGENT_TBO_USERNAME", "")
            password = self._env.get("VOYAGENT_TBO_PASSWORD", "")
            api_base = self._env.get(
                "VOYAGENT_TBO_API_BASE",
                "https://api.tbotechnology.in/TBOHolidays_HotelAPI",
            )
            if not username or not password:
                # Returning None marks the provider unconfigured so the
                # registry simply skips driver construction — the hotels
                # domain then raises "no hotel driver configured".
                return None
            return {
                "username": username,
                "password": password,
                "api_base": api_base,
            }
        return None


# --------------------------------------------------------------------------- #
# Storage-backed resolver                                                     #
# --------------------------------------------------------------------------- #


class StorageCredentialResolver:
    """Resolve credentials from per-tenant :class:`TenantCredential` rows.

    If :mod:`schemas.storage` cannot be imported, or the storage module
    does not yet expose the helpers needed to decrypt blobs, we fall back
    to an internal :class:`EnvCredentialResolver` and log a single
    WARNING so the deployment is visibly in degraded mode.

    TODO(voyagent-credentials): integrate with the KMS-backed decryption
    helper the credentials agent will ship. The current body calls a
    best-effort ``storage.resolve_tenant_credentials`` hook if it exists,
    otherwise falls back.
    """

    def __init__(self, fallback: _ResolverLike | None = None) -> None:
        self._fallback: _ResolverLike = fallback or EnvCredentialResolver()
        self._warned: bool = False

    async def __call__(
        self, tenant_id: EntityId, provider: str
    ) -> dict[str, Any] | None:
        storage = _maybe_import_storage()
        if storage is None:
            self._warn_fallback_once("schemas.storage not importable")
            return await self._fallback(tenant_id, provider)

        hook = getattr(storage, "resolve_tenant_credentials", None)
        if hook is None:
            self._warn_fallback_once(
                "schemas.storage missing resolve_tenant_credentials() helper"
            )
            return await self._fallback(tenant_id, provider)

        try:
            result = hook(tenant_id, provider)
            # Hook may be sync or async.
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "StorageCredentialResolver hook failed for tenant=%s provider=%s: %s",
                tenant_id,
                provider,
                exc,
            )
            return await self._fallback(tenant_id, provider)

        if result is None:
            # Row genuinely absent — let the registry skip the driver.
            return None
        if not isinstance(result, dict):
            logger.warning(
                "StorageCredentialResolver hook returned non-dict for tenant=%s provider=%s",
                tenant_id,
                provider,
            )
            return await self._fallback(tenant_id, provider)
        return result

    def _warn_fallback_once(self, reason: str) -> None:
        if self._warned:
            return
        self._warned = True
        logger.warning(
            "StorageCredentialResolver degraded → EnvCredentialResolver (%s)",
            reason,
        )


def _maybe_import_storage() -> Any | None:
    """Return :mod:`schemas.storage` or ``None`` if not importable."""
    try:
        import schemas.storage as storage  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    return storage


# --------------------------------------------------------------------------- #
# TenantRegistry                                                              #
# --------------------------------------------------------------------------- #


_DEFAULT_LRU_CAP = 128


class TenantRegistry:
    """LRU cache mapping ``tenant_id`` → :class:`DriverRegistry`.

    Each entry is built lazily on first :meth:`get`. When the cache is
    full the least-recently-used entry is evicted and closed. Closed
    entries release any HTTP clients the drivers opened.
    """

    def __init__(
        self,
        credential_resolver: _ResolverLike,
        *,
        max_entries: int = _DEFAULT_LRU_CAP,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._resolver = credential_resolver
        self._max = max_entries
        self._entries: OrderedDict[EntityId, DriverRegistry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, tenant_id: EntityId) -> DriverRegistry:
        """Return a :class:`DriverRegistry` bound to ``tenant_id``'s credentials.

        Concurrent callers for the same ``tenant_id`` share one
        construction — the async lock prevents a thundering-herd where
        every request builds its own driver.
        """
        async with self._lock:
            if tenant_id in self._entries:
                self._entries.move_to_end(tenant_id)
                return self._entries[tenant_id]
            registry = await self._build_for(tenant_id)
            self._entries[tenant_id] = registry
            while len(self._entries) > self._max:
                _, victim = self._entries.popitem(last=False)
                await _aclose_safely(victim)
            return registry

    async def _build_for(self, tenant_id: EntityId) -> DriverRegistry:
        """Assemble a fresh :class:`DriverRegistry` for ``tenant_id``.

        v0 only wires the Amadeus driver. Additional providers (Tally,
        hotels aggregators, ...) slot in here as their drivers land.
        """
        registry = DriverRegistry()

        amadeus_creds = await self._resolver(tenant_id, "amadeus")
        if amadeus_creds is not None:
            driver = _build_amadeus_driver(amadeus_creds)
            if driver is not None:
                registry.register("FareSearchDriver", driver)
                registry.register("PNRDriver", driver)

        tbo_creds = await self._resolver(tenant_id, "tbo")
        if tbo_creds is not None:
            tbo_driver = _build_tbo_driver(tbo_creds)
            if tbo_driver is not None:
                registry.register("HotelSearchDriver", tbo_driver)
                registry.register("HotelBookingDriver", tbo_driver)

        logger.info(
            "tenant_registry.built tenant=%s drivers=%d",
            tenant_id,
            len(registry.drivers()),
        )
        return registry

    async def aclose_all(self) -> None:
        """Close every cached registry's drivers. Idempotent."""
        async with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            await _aclose_safely(entry)

    def cached_tenants(self) -> list[EntityId]:
        """Return the currently-cached tenant ids. For tests / diagnostics."""
        return list(self._entries.keys())


async def _aclose_safely(registry: DriverRegistry) -> None:
    """Close ``registry`` while swallowing driver-side errors."""
    try:
        await registry.aclose()
    except Exception:  # noqa: BLE001
        logger.exception("tenant registry aclose failed")


# --------------------------------------------------------------------------- #
# Driver builders                                                             #
# --------------------------------------------------------------------------- #


def _build_amadeus_driver(creds: dict[str, Any]) -> Any | None:
    """Construct an :class:`AmadeusDriver` from a credentials dict.

    Returns ``None`` if the driver wheel isn't installed (tests) or if
    the credentials dict is malformed — a missing driver should not
    take down the whole tenant registry.
    """
    try:
        from drivers.amadeus import AmadeusConfig, AmadeusDriver
    except Exception as exc:  # noqa: BLE001
        logger.warning("amadeus driver not installed: %s", exc)
        return None

    try:
        config = AmadeusConfig(
            api_base=creds.get("api_base", "https://test.api.amadeus.com"),
            client_id=creds.get("client_id", ""),
            client_secret=creds.get("client_secret", ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AmadeusConfig build failed: %s", exc)
        return None
    return AmadeusDriver(config)


def _build_tbo_driver(creds: dict[str, Any]) -> Any | None:
    """Construct a :class:`TBODriver` from a credentials dict.

    Mirrors :func:`_build_amadeus_driver`: missing driver wheel or
    malformed credentials produce ``None`` rather than taking down the
    whole tenant registry. A tenant configured without TBO credentials
    simply gets no ``HotelSearchDriver`` registered, and the hotels
    tool layer surfaces "no hotel driver configured for this tenant".
    """
    try:
        from drivers.tbo import TBOConfig, TBODriver
    except Exception as exc:  # noqa: BLE001
        logger.warning("tbo driver not installed: %s", exc)
        return None

    try:
        from pydantic import SecretStr

        config = TBOConfig(
            api_base=creds.get(
                "api_base", "https://api.tbotechnology.in/TBOHolidays_HotelAPI"
            ),
            username=creds.get("username", ""),
            password=SecretStr(creds.get("password", "")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("TBOConfig build failed: %s", exc)
        return None

    try:
        return TBODriver(config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TBODriver construction failed: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Default resolver factory                                                    #
# --------------------------------------------------------------------------- #


def default_credential_resolver() -> _ResolverLike:
    """Pick the best available resolver for the current environment.

    If :mod:`schemas.storage` is importable we return a
    :class:`StorageCredentialResolver` (which itself falls back to env
    when decryption hooks aren't wired). Otherwise a bare
    :class:`EnvCredentialResolver`.
    """
    if _maybe_import_storage() is not None:
        return StorageCredentialResolver()
    return EnvCredentialResolver()


TENANT_REGISTRY_KEY = "tenant_registry"
"""ToolContext.extensions key for the :class:`TenantRegistry`."""


# --------------------------------------------------------------------------- #
# Tenant runtime settings (model, prompt suffix, limits)                      #
# --------------------------------------------------------------------------- #


_SUPPORTED_MODELS: frozenset[str] = frozenset(
    {
        "claude-sonnet-4-5",
        "claude-opus-4-6",
        "claude-haiku-4-5-20251001",
    }
)


class TenantSettings:
    """Plain container for per-tenant runtime overrides.

    Intentionally not a Pydantic model — it's constructed from either a
    SQL row or a defaults dict and passed around the orchestrator. The
    API layer has its own Pydantic shapes.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        model: str | None = None,
        system_prompt_suffix: str | None = None,
        rate_limit_per_minute: int = 60,
        rate_limit_per_hour: int = 1000,
        daily_token_budget: int | None = None,
        locale: str = "en",
        timezone: str = "UTC",
        default_currency: str = "INR",
    ) -> None:
        self.tenant_id = tenant_id
        # Guard against corrupted rows: unknown model falls back to env.
        if model is not None and model not in _SUPPORTED_MODELS:
            logger.warning(
                "tenant_settings: tenant=%s has unsupported model=%s — "
                "ignoring override",
                tenant_id,
                model,
            )
            model = None
        self.model = model
        self.system_prompt_suffix = system_prompt_suffix
        self.rate_limit_per_minute = int(rate_limit_per_minute)
        self.rate_limit_per_hour = int(rate_limit_per_hour)
        self.daily_token_budget = daily_token_budget
        self.locale = locale
        self.timezone = timezone
        self.default_currency = default_currency

    @classmethod
    def defaults(cls, tenant_id: str) -> "TenantSettings":
        return cls(tenant_id=tenant_id)


class TenantSettingsResolver:
    """Loads :class:`TenantSettings` from storage, caches in-process.

    On miss — no row — returns :meth:`TenantSettings.defaults`. The
    cache is intentionally small and best-effort; callers that mutate
    settings must call :meth:`invalidate` (or the API layer will).
    """

    def __init__(self, *, engine: Any | None = None) -> None:
        self._engine = engine
        self._cache: dict[str, TenantSettings] = {}
        self._lock = asyncio.Lock()

    async def get(self, tenant_id: str) -> TenantSettings:
        async with self._lock:
            hit = self._cache.get(tenant_id)
            if hit is not None:
                return hit
        loaded = await self._load(tenant_id)
        async with self._lock:
            self._cache[tenant_id] = loaded
        return loaded

    def invalidate(self, tenant_id: str | None = None) -> None:
        if tenant_id is None:
            self._cache.clear()
        else:
            self._cache.pop(tenant_id, None)

    def prime(self, settings: TenantSettings) -> None:
        """Test / API helper — insert a row into the cache directly."""
        self._cache[settings.tenant_id] = settings

    async def _load(self, tenant_id: str) -> TenantSettings:
        if self._engine is None:
            return TenantSettings.defaults(tenant_id)
        try:
            import uuid as _uuid

            from sqlalchemy import select
            from sqlalchemy.ext.asyncio import async_sessionmaker

            from schemas.storage import TenantSettingsRow  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            logger.warning("tenant_settings_resolver: storage unavailable: %s", exc)
            return TenantSettings.defaults(tenant_id)
        try:
            tid_uuid = _uuid.UUID(tenant_id)
        except ValueError:
            return TenantSettings.defaults(tenant_id)
        sm = async_sessionmaker(self._engine, expire_on_commit=False)
        async with sm() as db:
            row = (
                await db.execute(
                    select(TenantSettingsRow).where(
                        TenantSettingsRow.tenant_id == tid_uuid
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return TenantSettings.defaults(tenant_id)
        return TenantSettings(
            tenant_id=tenant_id,
            model=row.model,
            system_prompt_suffix=row.system_prompt_suffix,
            rate_limit_per_minute=row.rate_limit_per_minute,
            rate_limit_per_hour=row.rate_limit_per_hour,
            daily_token_budget=row.daily_token_budget,
            locale=row.locale,
            timezone=row.timezone,
            default_currency=row.default_currency,
        )


TENANT_SETTINGS_KEY = "tenant_settings"
"""ToolContext.extensions key for the active :class:`TenantSettings`."""


__all__ = [
    "CredentialResolver",
    "EnvCredentialResolver",
    "StorageCredentialResolver",
    "TENANT_REGISTRY_KEY",
    "TENANT_SETTINGS_KEY",
    "TenantRegistry",
    "TenantSettings",
    "TenantSettingsResolver",
    "default_credential_resolver",
]
