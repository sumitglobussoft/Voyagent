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
async def test_storage_credential_resolver_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed a TenantCredential row via the repository and verify the
    runtime-side :class:`StorageCredentialResolver` returns the
    decrypted fields."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    import schemas.storage as storage
    from schemas.storage import Base
    from schemas.storage.credentials import (
        CredentialPayload,
        TenantCredentialRepository,
        set_repository_for_test,
    )
    from schemas.storage.crypto import FernetEnvKMS

    from voyagent_agent_runtime.tenant_registry import StorageCredentialResolver

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed the tenant FK row.
    from schemas.storage import Tenant

    tenant_uuid = uuid.UUID("01900000-0000-7000-8000-000000000123")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                Tenant.__table__.insert().values(
                    id=str(tenant_uuid),
                    display_name="Acme",
                    default_currency="USD",
                    is_active=True,
                )
            )
        )

    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    repo = TenantCredentialRepository(engine, kms)
    set_repository_for_test(repo)
    try:
        await repo.put(
            tenant_uuid,
            "amadeus",
            CredentialPayload(
                provider="amadeus",
                fields={
                    "client_id": "cid-roundtrip",
                    "client_secret": "sec-roundtrip",
                },
                meta={"api_base": "https://test.api.amadeus.com"},
            ),
        )

        # Confirm the hook exists and the resolver goes through it.
        assert hasattr(storage, "resolve_tenant_credentials")

        resolver = StorageCredentialResolver()
        creds = await resolver(str(tenant_uuid), "amadeus")
        assert creds is not None
        assert creds["client_id"] == "cid-roundtrip"
        assert creds["client_secret"] == "sec-roundtrip"
        assert creds["api_base"] == "https://test.api.amadeus.com"

        # Repository.get round-trips with AAD verification.
        fetched = await repo.get(tenant_uuid, "amadeus")
        assert fetched is not None
        assert fetched.fields["client_id"] == "cid-roundtrip"
    finally:
        set_repository_for_test(None)
        await engine.dispose()


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


# --------------------------------------------------------------------------- #
# Additional coverage — tbo, per-tenant isolation, missing creds              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_env_credential_resolver_tbo_with_creds_returns_dict() -> None:
    env = {
        "VOYAGENT_TBO_USERNAME": "u",
        "VOYAGENT_TBO_PASSWORD": "p",
    }
    resolver = EnvCredentialResolver(env=env)
    creds = await resolver(_uuid7(), "tbo")
    assert creds is not None
    assert creds["username"] == "u"
    assert creds["password"] == "p"
    assert creds["api_base"].startswith("https://")


@pytest.mark.asyncio
async def test_env_credential_resolver_tbo_without_creds_returns_none() -> None:
    """Missing TBO creds must map to ``None`` so the registry skips the
    hotel-driver slot for that tenant."""
    env: dict[str, str] = {}  # no TBO vars at all
    resolver = EnvCredentialResolver(env=env)
    assert await resolver(_uuid7(), "tbo") is None


@pytest.mark.asyncio
async def test_registry_cache_is_per_tenant_and_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Building tenant A's registry must not populate tenant B's cache,
    and resolver calls per tenant stay scoped."""
    _install_fake_builder(monkeypatch)

    seen: list[str] = []

    async def _resolver(tenant_id: str, provider: str) -> dict[str, Any] | None:
        seen.append(f"{tenant_id}:{provider}")
        if provider == "amadeus":
            return {"client_id": f"cid-{tenant_id}", "client_secret": "x"}
        return None

    registry = TenantRegistry(_resolver)
    t_a, t_b = _uuid7(), _uuid7()

    reg_a = await registry.get(t_a)
    # After building A, only A is cached.
    assert registry.cached_tenants() == [t_a]
    # The resolver was asked for A's creds only.
    assert all(entry.startswith(f"{t_a}:") for entry in seen)

    reg_b = await registry.get(t_b)
    assert reg_b is not reg_a
    cached = registry.cached_tenants()
    assert t_a in cached and t_b in cached
    # Calls split cleanly between the two tenants.
    by_tenant: dict[str, int] = {}
    for entry in seen:
        by_tenant[entry.split(":", 1)[0]] = by_tenant.get(entry.split(":", 1)[0], 0) + 1
    assert set(by_tenant) == {t_a, t_b}


@pytest.mark.asyncio
async def test_build_for_with_missing_amadeus_driver_wheel_still_returns_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``_build_amadeus_driver`` returns ``None`` (driver not installed)
    the tenant gets a registry with no driver — NOT an exception that
    breaks the whole bundle."""
    monkeypatch.setattr(tr, "_build_amadeus_driver", lambda creds: None)
    monkeypatch.setattr(tr, "_build_tbo_driver", lambda creds: None)

    async def _resolver(tenant_id: str, provider: str) -> dict[str, Any]:
        return {"client_id": "a", "client_secret": "b"}

    registry = TenantRegistry(_resolver)
    reg = await registry.get(_uuid7())

    assert isinstance(reg, DriverRegistry)
    assert reg.drivers() == []
