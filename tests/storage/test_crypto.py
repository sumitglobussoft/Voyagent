"""Envelope-encryption round-trip tests for :mod:`schemas.storage.crypto`.

These tests exercise the AAD contract the repository relies on — a
ciphertext encrypted under one ``(tenant, provider)`` context cannot be
decrypted under another, even with the same key.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from schemas.storage import Tenant
from schemas.storage.credentials import (
    CredentialPayload,
    TenantCredentialRepository,
)
from schemas.storage.crypto import (
    CredentialDecryptionError,
    FernetEnvKMS,
    NullKMS,
    build_kms_provider,
)


pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# Fernet env KMS                                                              #
# --------------------------------------------------------------------------- #


async def test_fernet_roundtrip_with_matching_aad() -> None:
    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    ct, nonce = await kms.encrypt(b"hello", context={"tenant_id": "t1"})
    pt = await kms.decrypt(ct, nonce, context={"tenant_id": "t1"})
    assert pt == b"hello"


async def test_fernet_rejects_aad_mismatch() -> None:
    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    ct, nonce = await kms.encrypt(b"hello", context={"tenant_id": "t1"})
    with pytest.raises(CredentialDecryptionError):
        await kms.decrypt(ct, nonce, context={"tenant_id": "OTHER"})


async def test_fernet_rejects_wrong_key() -> None:
    k1 = FernetEnvKMS(FernetEnvKMS.generate_key())
    k2 = FernetEnvKMS(FernetEnvKMS.generate_key())
    ct, nonce = await k1.encrypt(b"hello", context={"x": "y"})
    with pytest.raises(CredentialDecryptionError):
        await k2.decrypt(ct, nonce, context={"x": "y"})


async def test_null_kms_roundtrips_but_warns(caplog: pytest.LogCaptureFixture) -> None:
    kms = NullKMS()
    with caplog.at_level("WARNING"):
        ct, nonce = await kms.encrypt(b"plain", context={"a": "b"})
        pt = await kms.decrypt(ct, nonce, context={"a": "b"})
    assert pt == b"plain"
    assert any("NullKMS" in rec.message for rec in caplog.records)


async def test_build_kms_provider_without_key_returns_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VOYAGENT_KMS_KEY", raising=False)
    monkeypatch.delenv("VOYAGENT_KMS_PROVIDER", raising=False)
    provider = build_kms_provider(env={})
    assert provider.provider_name == "null"


async def test_build_kms_provider_with_key_returns_fernet() -> None:
    key = FernetEnvKMS.generate_key()
    provider = build_kms_provider(env={"VOYAGENT_KMS_KEY": key})
    assert provider.provider_name == "fernet_env"


# --------------------------------------------------------------------------- #
# Repository                                                                  #
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def seeded_tenant(engine: AsyncEngine) -> uuid.UUID:
    tid = uuid.UUID("01900000-0000-7000-8000-00000000abcd")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: c.execute(
                Tenant.__table__.insert().values(
                    id=str(tid),
                    display_name="Repo Test",
                    default_currency="INR",
                    is_active=True,
                )
            )
        )
    return tid


async def test_repository_put_then_get(
    engine: AsyncEngine, seeded_tenant: uuid.UUID
) -> None:
    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    repo = TenantCredentialRepository(engine, kms)
    payload = CredentialPayload(
        provider="amadeus",
        fields={"client_id": "cid", "client_secret": "sec"},
        meta={"api_base": "https://test.api.amadeus.com"},
    )
    await repo.put(seeded_tenant, "amadeus", payload)
    fetched = await repo.get(seeded_tenant, "amadeus")
    assert fetched is not None
    assert fetched.fields["client_id"] == "cid"
    assert fetched.fields["client_secret"] == "sec"
    assert fetched.meta["api_base"] == "https://test.api.amadeus.com"


async def test_repository_rotate_stamps_rotated_at(
    engine: AsyncEngine, seeded_tenant: uuid.UUID
) -> None:
    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    repo = TenantCredentialRepository(engine, kms)
    await repo.put(
        seeded_tenant,
        "amadeus",
        CredentialPayload(provider="amadeus", fields={"k": "v"}, meta={}),
    )
    await repo.rotate(
        seeded_tenant,
        "amadeus",
        CredentialPayload(provider="amadeus", fields={"k": "v2"}, meta={}),
    )
    fetched = await repo.get(seeded_tenant, "amadeus")
    assert fetched is not None
    assert fetched.fields["k"] == "v2"
    assert fetched.rotated_at is not None


async def test_repository_corruption_raises(
    engine: AsyncEngine, seeded_tenant: uuid.UUID
) -> None:
    """Flipping the stored ciphertext must raise CredentialDecryptionError."""
    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    repo = TenantCredentialRepository(engine, kms)
    await repo.put(
        seeded_tenant,
        "amadeus",
        CredentialPayload(provider="amadeus", fields={"k": "v"}, meta={}),
    )
    # Corrupt the row directly.
    from sqlalchemy import update

    from schemas.storage import TenantCredential
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        async with db.begin():
            await db.execute(
                update(TenantCredential)
                .where(TenantCredential.tenant_id == seeded_tenant)
                .values(encrypted_blob=b"not-a-fernet-token")
            )

    with pytest.raises(CredentialDecryptionError):
        await repo.get(seeded_tenant, "amadeus")


async def test_repository_delete(
    engine: AsyncEngine, seeded_tenant: uuid.UUID
) -> None:
    kms = FernetEnvKMS(FernetEnvKMS.generate_key())
    repo = TenantCredentialRepository(engine, kms)
    await repo.put(
        seeded_tenant,
        "amadeus",
        CredentialPayload(provider="amadeus", fields={"k": "v"}, meta={}),
    )
    await repo.delete(seeded_tenant, "amadeus")
    assert await repo.get(seeded_tenant, "amadeus") is None
