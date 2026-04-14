"""Default runtime bundle — the composition root for v0.

``build_default_runtime`` wires together everything a host process (API, CLI,
worker) needs: tenant-scoped driver registry, audit sink, session store,
and the :class:`Orchestrator` with its domain-agent resolver.

Hosts should depend on the bundle rather than reaching into individual
sub-packages — that keeps the composition centralised as v0 grows into v1.

Multi-tenancy
-------------
The v0 bundle used a single process-wide :class:`DriverRegistry`. That
field is retained for backward compatibility, but it's now a *process-wide
fallback* and its use is logged as a deprecation. New code should resolve
drivers through :class:`TenantRegistry`, which lazily materialises a
per-tenant registry from credentials resolved via the configured
:class:`CredentialResolver`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from drivers._contracts.cache import OfferCache
from schemas.canonical import EntityId

from .anthropic_client import AnthropicClient, Settings
from .domain_agents import DomainAgent
from .domain_agents.accounting import AccountingAgent
from .domain_agents.ticketing_visa import TicketingVisaAgent
from .drivers import DriverRegistry, build_default_registry
from .offer_cache import InMemoryOfferCache, build_offer_cache
from .orchestrator import Orchestrator
from .session import InMemorySessionStore, SessionStore
from .tenant_registry import (
    EnvCredentialResolver,
    StorageCredentialResolver,
    TenantRegistry,
    _maybe_import_storage,
)
from .tools import AuditSink, InMemoryAuditSink

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# EntityId helpers                                                            #
# --------------------------------------------------------------------------- #


def new_session_id() -> EntityId:
    """Mint a UUIDv7-shaped identifier suitable for canonical ``EntityId``.

    UUIDv7 packs a millisecond-precision timestamp into the high bits, which
    gives us monotonically-sortable ids without extra coordination. The low
    bits are cryptographically random.
    """
    ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    # Layout: 48-bit ms | version=7 | 12-bit rand_a | variant=10 | 62-bit rand_b
    high = (ms << 16) | (0x7 << 12) | rand_a
    low = (0b10 << 62) | rand_b
    value = (high << 64) | low
    hex_str = f"{value:032x}"
    return f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"


def coerce_entity_id(raw: str, *, namespace: str = "voyagent") -> EntityId:
    """Return ``raw`` if it already looks like a UUIDv7; otherwise derive one.

    For v0 demo flows the API surface accepts human-readable tenant / actor
    labels (``"demo-tenant"``, ``"demo-actor"``). Canonical ``EntityId``
    requires a UUIDv7 shape, so we hash the label into deterministic bytes
    and reshape them. Two calls with the same ``raw`` + ``namespace``
    always produce the same id — good enough until real auth lands.
    """
    import re

    _UUIDV7_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    if _UUIDV7_RE.match(raw):
        return raw

    digest = hashlib.sha256(f"{namespace}:{raw}".encode("utf-8")).hexdigest()
    # Force version nibble to 7 and variant nibble to 8–b.
    parts = (digest[0:8], digest[8:12], "7" + digest[13:16], "8" + digest[17:20], digest[20:32])
    return "-".join(parts)


# --------------------------------------------------------------------------- #
# Bundle                                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class DefaultRuntime:
    """A fully wired runtime ready to drive one or more chat sessions.

    All members are process-local and non-persistent in v0. Hosts should
    treat the bundle as a singleton and call :meth:`aclose` on shutdown.

    ``driver_registry`` is **deprecated** — it is kept as a process-wide
    fallback for legacy callers (tests pre-dating multi-tenancy). New
    code should resolve drivers via ``tenant_registry.get(tenant_id)``.
    """

    anthropic_client: AnthropicClient
    audit_sink: AuditSink
    tenant_registry: TenantRegistry
    session_store: SessionStore
    orchestrator: Orchestrator
    domain_agents: dict[str, DomainAgent]
    driver_registry: DriverRegistry | None = field(default=None)
    engine: "AsyncEngine | None" = field(default=None)
    offer_cache: OfferCache | None = field(default=None)

    def __post_init__(self) -> None:
        # Track whether anyone reached for ``driver_registry`` so we can log
        # a deprecation the first time it happens, without spamming every
        # access. A lightweight sentinel attribute achieves this without a
        # property descriptor that fights dataclass init.
        object.__setattr__(self, "_driver_registry_warned", False)

    def use_driver_registry(self) -> DriverRegistry | None:
        """Return the deprecated process-wide registry with a one-shot warning.

        Callers that still need the old single-tenant registry (tests) use
        this accessor so the deprecation is visible. Production code should
        never call it.
        """
        if self.driver_registry is None:
            return None
        if not getattr(self, "_driver_registry_warned", False):
            object.__setattr__(self, "_driver_registry_warned", True)
            warnings.warn(
                "DefaultRuntime.driver_registry is deprecated; resolve drivers "
                "through tenant_registry.get(tenant_id) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            logger.warning(
                "DefaultRuntime.driver_registry accessed — this is a "
                "process-wide fallback and is not multi-tenant safe."
            )
        return self.driver_registry

    async def aclose(self) -> None:
        """Release drivers, offer cache, and SQLAlchemy engine.

        Anthropic client is closed by its own lifecycle.
        """
        await self.tenant_registry.aclose_all()
        if self.driver_registry is not None:
            await self.driver_registry.aclose()
        if self.offer_cache is not None:
            closer = getattr(self.offer_cache, "aclose", None)
            if callable(closer):
                try:
                    await closer()
                except Exception:  # noqa: BLE001
                    logger.exception("offer cache aclose failed")
        if self.engine is not None:
            try:
                await self.engine.dispose()
            except Exception:  # noqa: BLE001
                logger.exception("engine dispose failed")


_bundle_singleton: DefaultRuntime | None = None


def _maybe_build_engine(db_url: str | None):  # type: ignore[no-untyped-def]
    """Return an ``AsyncEngine`` if ``db_url`` is set, else ``None``.

    The import is localised so an environment without SQLAlchemy
    installed (or no DB configured) still loads this module.
    """
    if not db_url:
        return None
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(db_url, future=True, pool_pre_ping=True)


def build_default_runtime(
    *,
    available_domains: list[str] | None = None,
    db_url: str | None = None,
    redis_url: str | None = None,
) -> DefaultRuntime:
    """Construct the default runtime for local dev, CLI, and the HTTP API.

    Env dependencies:
      * ``ANTHROPIC_API_KEY`` — the Anthropic SDK.
      * ``VOYAGENT_AGENT_MODEL`` — optional, defaults to ``claude-sonnet-4-5``.
      * ``VOYAGENT_AMADEUS_CLIENT_ID`` / ``VOYAGENT_AMADEUS_CLIENT_SECRET`` —
        the :class:`EnvCredentialResolver` reads these for every tenant
        when storage-backed credentials aren't available.
      * ``VOYAGENT_DB_URL`` — optional Postgres URL. When present the
        session store and audit sink use :mod:`.stores_pg`.
      * ``VOYAGENT_REDIS_URL`` — optional Redis URL for the offer cache.

    The runtime falls back to in-memory implementations for both the
    session store/audit sink and the offer cache when their respective
    URLs are absent, so tests and bare-metal dev loops don't need
    infrastructure.

    Call :func:`get_default_runtime` from long-lived processes so the bundle
    is constructed once; this function always builds a fresh bundle.
    """
    resolved_db_url = (
        db_url if db_url is not None else os.environ.get("VOYAGENT_DB_URL")
    )
    resolved_redis_url = (
        redis_url if redis_url is not None else os.environ.get("VOYAGENT_REDIS_URL")
    )

    anthropic_client = AnthropicClient(Settings())

    # ---- Persistence stores ------------------------------------------ #
    engine = _maybe_build_engine(resolved_db_url)
    if engine is not None:
        # Localised import: SQLAlchemy is only needed on the Postgres path.
        from .stores_pg import PostgresAuditSink, PostgresSessionStore

        session_store: SessionStore = PostgresSessionStore(engine)
        audit_sink: AuditSink = PostgresAuditSink(engine)
        logger.info("runtime: Postgres persistence enabled")
    else:
        session_store = InMemorySessionStore()
        audit_sink = InMemoryAuditSink()
        logger.info("runtime: in-memory persistence (no VOYAGENT_DB_URL)")

    # ---- Offer cache ------------------------------------------------- #
    offer_cache: OfferCache
    if resolved_redis_url:
        offer_cache = build_offer_cache(resolved_redis_url)
        logger.info("runtime: Redis offer cache enabled")
    else:
        offer_cache = InMemoryOfferCache()
        logger.info("runtime: in-memory offer cache (no VOYAGENT_REDIS_URL)")

    # Pick the credential resolver based on what's importable. When the
    # storage + encryption work lands, StorageCredentialResolver becomes
    # the live path; until then we degrade gracefully to env.
    if _maybe_import_storage() is not None:
        resolver = StorageCredentialResolver()
    else:
        resolver = EnvCredentialResolver()
    tenant_registry = TenantRegistry(resolver)

    # Keep a best-effort process-wide fallback so legacy tests that read
    # ``bundle.driver_registry`` keep working during the migration. This
    # is intentionally tolerant: if the driver wheel isn't present or
    # env vars aren't set, we leave ``driver_registry=None``.
    driver_registry: DriverRegistry | None
    try:
        driver_registry = build_default_registry()
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "build_default_registry skipped (expected during multi-tenant migration): %s",
            exc,
        )
        driver_registry = None

    # Wire the offer cache into any driver that accepts one (Amadeus). Use
    # duck typing — drivers that don't carry a ``_offer_cache`` attribute
    # remain unaffected.
    if driver_registry is not None:
        for driver in driver_registry.drivers():
            if getattr(driver, "name", None) == "amadeus":
                setattr(driver, "_offer_cache", offer_cache)

    ticketing = TicketingVisaAgent(client=anthropic_client, audit_sink=audit_sink)
    accounting = AccountingAgent(client=anthropic_client, audit_sink=audit_sink)
    domain_agents: dict[str, DomainAgent] = {
        "ticketing_visa": ticketing,
        "accounting": accounting,
    }

    domains = available_domains or list(domain_agents.keys())

    def _resolver(domain: str) -> DomainAgent:
        try:
            return domain_agents[domain]
        except KeyError as exc:
            raise KeyError(f"No domain agent registered for {domain!r}.") from exc

    orchestrator = Orchestrator(
        anthropic_client=anthropic_client,
        audit_sink=audit_sink,
        available_domains=domains,
        handoff_resolver=_resolver,
        tenant_registry=tenant_registry,
        driver_registry=driver_registry,
    )

    logger.info(
        "default runtime built: model=%s domains=%s resolver=%s persistence=%s offer_cache=%s",
        anthropic_client.model,
        domains,
        type(resolver).__name__,
        "postgres" if engine is not None else "in-memory",
        "redis" if resolved_redis_url else "in-memory",
    )

    return DefaultRuntime(
        anthropic_client=anthropic_client,
        audit_sink=audit_sink,
        tenant_registry=tenant_registry,
        session_store=session_store,
        orchestrator=orchestrator,
        domain_agents=domain_agents,
        driver_registry=driver_registry,
        engine=engine,
        offer_cache=offer_cache,
    )


def get_default_runtime() -> DefaultRuntime:
    """Return a cached :class:`DefaultRuntime`, constructing it on first call."""
    global _bundle_singleton
    if _bundle_singleton is None:
        _bundle_singleton = build_default_runtime()
    return _bundle_singleton


__all__ = [
    "DefaultRuntime",
    "build_default_runtime",
    "coerce_entity_id",
    "get_default_runtime",
    "new_session_id",
]
