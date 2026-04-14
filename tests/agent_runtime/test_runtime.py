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
