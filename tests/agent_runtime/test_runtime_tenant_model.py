"""Tests for per-tenant model + prompt selection on :class:`DefaultRuntime`.

These tests exercise the tenant-settings resolver and the runtime
helpers that read from it. They do not spin up the full orchestrator
loop — the per-turn wiring is exercised by the orchestrator tests.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from schemas.storage import Base, Tenant, TenantSettingsRow, uuid7
from voyagent_agent_runtime.runtime import DefaultRuntime, build_default_runtime
from voyagent_agent_runtime.tenant_registry import (
    TenantSettings,
    TenantSettingsResolver,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed_tenant(engine, tenant_id, *, model=None, suffix=None) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as db:
        async with db.begin():
            db.add(
                Tenant(
                    id=tenant_id,
                    display_name="T",
                    default_currency="INR",
                )
            )
            if model is not None or suffix is not None:
                db.add(
                    TenantSettingsRow(
                        tenant_id=tenant_id,
                        model=model,
                        system_prompt_suffix=suffix,
                    )
                )


async def test_tenant_settings_resolver_returns_row(sqlite_engine) -> None:
    tid = uuid7()
    await _seed_tenant(
        sqlite_engine, tid, model="claude-haiku-4-5-20251001", suffix="Quote in INR"
    )
    resolver = TenantSettingsResolver(engine=sqlite_engine)
    settings = await resolver.get(str(tid))
    assert settings.model == "claude-haiku-4-5-20251001"
    assert settings.system_prompt_suffix == "Quote in INR"
    # Defaults come from the row's server_default values.
    assert settings.rate_limit_per_minute == 60
    assert settings.rate_limit_per_hour == 1000


async def test_tenant_settings_resolver_defaults_when_no_row(sqlite_engine) -> None:
    tid = uuid7()
    await _seed_tenant(sqlite_engine, tid)  # tenant but no settings row
    resolver = TenantSettingsResolver(engine=sqlite_engine)
    settings = await resolver.get(str(tid))
    assert settings.model is None
    assert settings.system_prompt_suffix is None
    assert settings.rate_limit_per_minute == 60


async def test_tenant_settings_invalid_model_falls_back_with_warning(
    caplog,
) -> None:
    with caplog.at_level(logging.WARNING):
        settings = TenantSettings(
            tenant_id="tenant-a",
            model="some-hallucinated-model",
        )
    assert settings.model is None
    assert any(
        "unsupported model" in r.message for r in caplog.records
    )


async def test_resolver_cache_invalidate(sqlite_engine) -> None:
    tid = uuid7()
    await _seed_tenant(sqlite_engine, tid, model="claude-sonnet-4-5")
    resolver = TenantSettingsResolver(engine=sqlite_engine)
    s1 = await resolver.get(str(tid))
    assert s1.model == "claude-sonnet-4-5"

    # Update the row out of band, then prove the cache still holds old.
    sm = async_sessionmaker(sqlite_engine, expire_on_commit=False)
    async with sm() as db:
        async with db.begin():
            row = await db.get(TenantSettingsRow, tid)
            row.model = "claude-opus-4-6"
    s2 = await resolver.get(str(tid))
    assert s2.model == "claude-sonnet-4-5"  # stale (cached)

    resolver.invalidate(str(tid))
    s3 = await resolver.get(str(tid))
    assert s3.model == "claude-opus-4-6"


async def test_default_runtime_resolve_tenant_model_uses_override(
    sqlite_engine, monkeypatch
) -> None:
    monkeypatch.setenv("VOYAGENT_AGENT_MODEL", "claude-sonnet-4-5")
    tid = uuid7()
    await _seed_tenant(
        sqlite_engine, tid, model="claude-haiku-4-5-20251001", suffix="Quote in INR."
    )

    resolver = TenantSettingsResolver(engine=sqlite_engine)
    # Build a minimal DefaultRuntime shell around the resolver — we only
    # care about the resolver plumbing here, not the full bundle.
    runtime = DefaultRuntime.__new__(DefaultRuntime)
    # __post_init__ sets a sentinel on the instance.
    object.__setattr__(runtime, "_driver_registry_warned", False)
    runtime.tenant_settings_resolver = resolver
    runtime.driver_registry = None
    runtime.offer_cache = None
    runtime.engine = None

    resolved = await runtime.resolve_tenant_model(str(tid))
    assert resolved == "claude-haiku-4-5-20251001"

    suffix = await runtime.resolve_tenant_prompt_suffix(str(tid))
    assert suffix == "Quote in INR."


async def test_default_runtime_resolve_tenant_model_falls_back_to_env(
    sqlite_engine, monkeypatch
) -> None:
    monkeypatch.setenv("VOYAGENT_AGENT_MODEL", "claude-sonnet-4-5")
    tid = uuid7()
    await _seed_tenant(sqlite_engine, tid)  # no settings row

    resolver = TenantSettingsResolver(engine=sqlite_engine)
    runtime = DefaultRuntime.__new__(DefaultRuntime)
    object.__setattr__(runtime, "_driver_registry_warned", False)
    runtime.tenant_settings_resolver = resolver
    runtime.driver_registry = None
    runtime.offer_cache = None
    runtime.engine = None

    resolved = await runtime.resolve_tenant_model(str(tid))
    assert resolved == "claude-sonnet-4-5"
    assert await runtime.resolve_tenant_prompt_suffix(str(tid)) is None


async def test_build_default_runtime_wires_resolver(monkeypatch) -> None:
    # Build the full bundle in memory-only mode — confirms every new
    # field is attached without blowing up.
    monkeypatch.setenv("VOYAGENT_STORES", "memory")
    monkeypatch.delenv("VOYAGENT_DB_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    bundle = build_default_runtime()
    try:
        assert bundle.tenant_settings_resolver is not None
        assert bundle.rate_limiter is not None
        assert bundle.cost_tracker is not None
        assert bundle.tool_cache is not None
        # resolve without a row → env default / Anthropic default
        model = await bundle.resolve_tenant_model("some-tenant-id")
        assert model  # non-empty
    finally:
        await bundle.aclose()
