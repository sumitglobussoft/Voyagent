"""Tests for :class:`TenantRegistry`.

These tests stub the driver construction path so we don't need real
Amadeus credentials — the invariants we care about are:

* Two distinct tenants get two distinct :class:`DriverRegistry` objects.
* The credential resolver is asked once per tenant per provider.
* :meth:`TenantRegistry.aclose_all` closes every cached registry.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from voyagent_agent_runtime import tenant_registry as tr
from voyagent_agent_runtime.drivers import DriverRegistry
from voyagent_agent_runtime.tenant_registry import (
    EnvCredentialResolver,
    TenantRegistry,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _uuid7() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


class _FakeDriver:
    """Minimal driver-shaped object — tracks aclose() calls."""

    def __init__(self, creds: dict[str, Any]) -> None:
        self.creds = dict(creds)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _install_fake_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_FakeDriver]:
    """Replace :func:`_build_amadeus_driver` with a tracking stub.

    Returns the mutable list each call appends to, so tests can inspect
    every driver instance that was constructed.
    """
    built: list[_FakeDriver] = []

    def _factory(creds: dict[str, Any]) -> _FakeDriver:
        drv = _FakeDriver(creds)
        built.append(drv)
        return drv

    monkeypatch.setattr(tr, "_build_amadeus_driver", _factory)
    return built


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_two_tenants_get_distinct_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _install_fake_builder(monkeypatch)

    async def _resolver(tenant_id: str, provider: str) -> dict[str, Any] | None:
        assert provider == "amadeus"
        return {
            "client_id": f"cid-for-{tenant_id}",
            "client_secret": f"sec-for-{tenant_id}",
            "api_base": "https://test.api.amadeus.com",
        }

    registry = TenantRegistry(_resolver)
    t1, t2 = _uuid7(), _uuid7()

    reg1 = await registry.get(t1)
    reg2 = await registry.get(t2)

    assert isinstance(reg1, DriverRegistry)
    assert isinstance(reg2, DriverRegistry)
    assert reg1 is not reg2, "Distinct tenants must not share a registry"

    # Per-tenant credentials flowed into the per-tenant driver instance.
    assert len(built) == 2
    assert built[0].creds["client_id"] == f"cid-for-{t1}"
    assert built[1].creds["client_id"] == f"cid-for-{t2}"

    # Repeated fetch for the same tenant is cached.
    reg1_again = await registry.get(t1)
    assert reg1_again is reg1
    assert len(built) == 2  # no rebuild


@pytest.mark.asyncio
async def test_aclose_all_closes_every_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _install_fake_builder(monkeypatch)

    async def _resolver(tenant_id: str, provider: str) -> dict[str, Any]:
        return {"client_id": "x", "client_secret": "y"}

    registry = TenantRegistry(_resolver)
    t1, t2 = _uuid7(), _uuid7()
    await registry.get(t1)
    await registry.get(t2)
    assert len(built) == 2

    await registry.aclose_all()

    assert all(d.closed for d in built), "every driver should be closed"
    assert registry.cached_tenants() == []


@pytest.mark.asyncio
async def test_resolver_none_skips_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the resolver returns ``None`` for a provider, no driver is bound."""
    built = _install_fake_builder(monkeypatch)

    async def _resolver(tenant_id: str, provider: str) -> dict[str, Any] | None:
        return None  # tenant has no Amadeus credentials

    registry = TenantRegistry(_resolver)
    reg = await registry.get(_uuid7())

    assert isinstance(reg, DriverRegistry)
    assert reg.drivers() == []
    assert built == []


@pytest.mark.asyncio
async def test_lru_evicts_least_recently_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _install_fake_builder(monkeypatch)

    async def _resolver(tenant_id: str, provider: str) -> dict[str, Any]:
        return {"client_id": tenant_id, "client_secret": "s"}

    registry = TenantRegistry(_resolver, max_entries=2)
    t1, t2, t3 = _uuid7(), _uuid7(), _uuid7()

    await registry.get(t1)
    await registry.get(t2)
    # Insert a third → t1 is evicted (LRU).
    await registry.get(t3)

    cached = registry.cached_tenants()
    assert t1 not in cached
    assert t2 in cached and t3 in cached

    # The driver built for t1 must have been closed on eviction.
    t1_driver = next(d for d in built if d.creds["client_id"] == t1)
    assert t1_driver.closed is True


@pytest.mark.asyncio
async def test_env_credential_resolver_returns_env_values() -> None:
    env = {
        "VOYAGENT_AMADEUS_CLIENT_ID": "cid-env",
        "VOYAGENT_AMADEUS_CLIENT_SECRET": "sec-env",
    }
    resolver = EnvCredentialResolver(env=env)

    creds = await resolver(_uuid7(), "amadeus")
    assert creds is not None
    assert creds["client_id"] == "cid-env"
    assert creds["client_secret"] == "sec-env"
    assert creds["api_base"].startswith("https://")

    # Unknown provider → None.
    assert await resolver(_uuid7(), "sabre") is None
