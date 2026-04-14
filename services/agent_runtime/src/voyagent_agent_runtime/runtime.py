"""Default runtime bundle — the composition root for v0.

``build_default_runtime`` wires together everything a host process (API, CLI,
worker) needs: driver registry, audit sink, session store, and the
:class:`Orchestrator` with its domain-agent resolver.

Hosts should depend on the bundle rather than reaching into individual
sub-packages — that keeps the composition centralised as v0 grows into v1.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass

from schemas.canonical import EntityId

from .anthropic_client import AnthropicClient, Settings
from .domain_agents import DomainAgent
from .domain_agents.ticketing_visa import TicketingVisaAgent
from .drivers import DriverRegistry, build_default_registry
from .orchestrator import Orchestrator
from .session import InMemorySessionStore
from .tools import AuditSink, InMemoryAuditSink

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
    """

    anthropic_client: AnthropicClient
    audit_sink: AuditSink
    driver_registry: DriverRegistry
    session_store: InMemorySessionStore
    orchestrator: Orchestrator
    domain_agents: dict[str, DomainAgent]

    async def aclose(self) -> None:
        """Release drivers. Anthropic client is closed by its own lifecycle."""
        await self.driver_registry.aclose()


_bundle_singleton: DefaultRuntime | None = None


def build_default_runtime(
    *,
    available_domains: list[str] | None = None,
) -> DefaultRuntime:
    """Construct the default runtime for local dev, CLI, and the HTTP API.

    Env dependencies:
      * ``ANTHROPIC_API_KEY`` — the Anthropic SDK.
      * ``VOYAGENT_AGENT_MODEL`` — optional, defaults to ``claude-sonnet-4-5``.
      * ``VOYAGENT_AMADEUS_CLIENT_ID`` / ``VOYAGENT_AMADEUS_CLIENT_SECRET`` —
        required by the Amadeus driver inside :func:`build_default_registry`.

    Call :func:`get_default_runtime` from long-lived processes so the bundle
    is constructed once; this function always builds a fresh bundle.
    """
    anthropic_client = AnthropicClient(Settings())
    audit_sink: AuditSink = InMemoryAuditSink()
    driver_registry = build_default_registry()
    session_store = InMemorySessionStore()

    ticketing = TicketingVisaAgent(client=anthropic_client, audit_sink=audit_sink)
    domain_agents: dict[str, DomainAgent] = {"ticketing_visa": ticketing}

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
        driver_registry=driver_registry,
    )

    logger.info(
        "default runtime built: model=%s domains=%s drivers=%d",
        anthropic_client.model,
        domains,
        len(driver_registry.drivers()),
    )

    return DefaultRuntime(
        anthropic_client=anthropic_client,
        audit_sink=audit_sink,
        driver_registry=driver_registry,
        session_store=session_store,
        orchestrator=orchestrator,
        domain_agents=domain_agents,
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
