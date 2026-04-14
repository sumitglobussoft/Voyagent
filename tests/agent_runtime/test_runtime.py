"""Tests for :func:`build_default_runtime` wiring.

Focus: the :class:`PassengerResolver` is populated on the bundle and is
available to drivers + tool contexts.
"""

from __future__ import annotations

import pytest

from voyagent_agent_runtime import (
    DefaultRuntime,
    InMemoryPassengerResolver,
    PASSENGER_RESOLVER_KEY,
    build_default_runtime,
)


@pytest.mark.asyncio
async def test_build_default_runtime_populates_passenger_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bundle returned by ``build_default_runtime`` carries a resolver."""
    # Ensure env-dependent branches don't attempt real I/O.
    monkeypatch.delenv("VOYAGENT_DB_URL", raising=False)
    monkeypatch.delenv("VOYAGENT_REDIS_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    bundle: DefaultRuntime = build_default_runtime()
    try:
        assert bundle.passenger_resolver is not None
        assert isinstance(bundle.passenger_resolver, InMemoryPassengerResolver)
        # Well-known extension key is exported for tool context wiring.
        assert PASSENGER_RESOLVER_KEY == "passenger_resolver"
    finally:
        await bundle.aclose()


# --------------------------------------------------------------------------- #
# Selection rules for persistence stores                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_db_url_falls_back_to_in_memory_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With neither ``VOYAGENT_DB_URL`` nor ``VOYAGENT_STORES`` set, the
    bundle uses in-memory session store + audit sink."""
    from voyagent_agent_runtime.session import InMemorySessionStore
    from voyagent_agent_runtime.tools import InMemoryAuditSink

    monkeypatch.delenv("VOYAGENT_DB_URL", raising=False)
    monkeypatch.delenv("VOYAGENT_REDIS_URL", raising=False)
    monkeypatch.delenv("VOYAGENT_STORES", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")

    bundle = build_default_runtime()
    try:
        assert isinstance(bundle.session_store, InMemorySessionStore)
        assert isinstance(bundle.audit_sink, InMemoryAuditSink)
        assert bundle.engine is None
    finally:
        await bundle.aclose()


@pytest.mark.asyncio
async def test_voyagent_stores_memory_forces_memory_even_with_db_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``VOYAGENT_STORES=memory`` must defeat a configured DB URL."""
    from voyagent_agent_runtime.session import InMemorySessionStore
    from voyagent_agent_runtime.tools import InMemoryAuditSink

    monkeypatch.setenv("VOYAGENT_DB_URL", "postgresql+asyncpg://ghost:5432/x")
    monkeypatch.setenv("VOYAGENT_STORES", "memory")
    monkeypatch.delenv("VOYAGENT_REDIS_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")

    bundle = build_default_runtime()
    try:
        assert isinstance(bundle.session_store, InMemorySessionStore)
        assert isinstance(bundle.audit_sink, InMemoryAuditSink)
        assert bundle.engine is None
    finally:
        await bundle.aclose()


@pytest.mark.asyncio
async def test_db_url_without_stores_override_builds_postgres_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``VOYAGENT_DB_URL`` set and ``VOYAGENT_STORES`` unset, the
    bundle uses Postgres-backed stores (via an in-memory aiosqlite URL we
    can safely construct and dispose)."""
    from voyagent_agent_runtime.session import InMemorySessionStore

    monkeypatch.setenv("VOYAGENT_DB_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.delenv("VOYAGENT_STORES", raising=False)
    monkeypatch.delenv("VOYAGENT_REDIS_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")

    bundle = build_default_runtime()
    try:
        # We don't care which concrete class, just that we did NOT fall
        # back to InMemorySessionStore (which happens on no DB URL).
        assert not isinstance(bundle.session_store, InMemorySessionStore), (
            "DB URL must route to the Postgres-backed session store."
        )
        assert bundle.engine is not None
    finally:
        await bundle.aclose()


def test_anthropic_client_reads_voyagent_agent_model_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Anthropic client model is sourced from VOYAGENT_AGENT_MODEL."""
    from voyagent_agent_runtime.anthropic_client import AnthropicClient, Settings

    monkeypatch.setenv("VOYAGENT_AGENT_MODEL", "claude-test-model-xyz")

    client = AnthropicClient(Settings())
    assert client.model == "claude-test-model-xyz"
