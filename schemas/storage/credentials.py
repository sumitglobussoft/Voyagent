"""Encrypted credential storage for :class:`TenantCredential`.

Call sites speak :class:`CredentialPayload` (plaintext Pydantic model)
and let :class:`TenantCredentialRepository` handle the envelope
encryption round-trip. The repository never logs the decrypted payload;
``repr`` on :class:`CredentialPayload` is overridden to redact the
``fields`` dict so a careless ``print`` during debugging does not leak
client secrets.

The resolver hook :func:`resolve_tenant_credentials` is the module-level
coroutine that :mod:`voyagent_agent_runtime.tenant_registry` imports.
It uses a process-cached :class:`TenantCredentialRepository` bound to
the ``VOYAGENT_DB_URL`` engine + the KMS provider built from env.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .crypto import (
    CredentialDecryptionError,
    KMSProvider,
    SecurityError,
    build_kms_provider,
)
from .tenant import TenantCredential

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Plaintext payload                                                           #
# --------------------------------------------------------------------------- #


class CredentialPayload(BaseModel):
    """Decrypted shape of a :class:`TenantCredential`.

    ``fields`` holds the actual secret material (client id / secret,
    API key, refresh token, ...). ``meta`` carries non-secret
    accompaniment that the driver also needs — typically the API base
    URL or an account id. ``rotated_at`` is stamped by
    :meth:`TenantCredentialRepository.rotate`.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    fields: dict[str, str] = Field(default_factory=dict)
    meta: dict[str, str] = Field(default_factory=dict)
    rotated_at: datetime | None = None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        keys = ",".join(sorted(self.fields.keys()))
        return (
            f"CredentialPayload(provider={self.provider!r}, "
            f"fields=<redacted:{keys}>, meta={self.meta!r}, "
            f"rotated_at={self.rotated_at!r})"
        )

    __str__ = __repr__


# --------------------------------------------------------------------------- #
# Serialisation helpers                                                       #
# --------------------------------------------------------------------------- #


def _payload_to_bytes(payload: CredentialPayload) -> bytes:
    raw: dict[str, Any] = {
        "provider": payload.provider,
        "fields": dict(payload.fields),
        "meta": dict(payload.meta),
        "rotated_at": (
            payload.rotated_at.astimezone(timezone.utc).isoformat()
            if payload.rotated_at is not None
            else None
        ),
    }
    return json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _payload_from_bytes(blob: bytes) -> CredentialPayload:
    try:
        obj = json.loads(blob.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CredentialDecryptionError(
            f"decrypted credential blob is not valid JSON: {exc}"
        ) from exc
    rotated_raw = obj.get("rotated_at")
    rotated_at: datetime | None = None
    if rotated_raw:
        try:
            rotated_at = datetime.fromisoformat(rotated_raw)
        except Exception as exc:  # noqa: BLE001
            raise CredentialDecryptionError(
                f"rotated_at is not ISO8601: {rotated_raw!r}"
            ) from exc
    try:
        return CredentialPayload(
            provider=str(obj.get("provider") or ""),
            fields={str(k): str(v) for k, v in (obj.get("fields") or {}).items()},
            meta={str(k): str(v) for k, v in (obj.get("meta") or {}).items()},
            rotated_at=rotated_at,
        )
    except Exception as exc:  # noqa: BLE001
        raise CredentialDecryptionError(
            f"decrypted credential payload failed validation: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# Id helpers                                                                  #
# --------------------------------------------------------------------------- #


def _to_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _context_for(tenant_id: uuid.UUID, provider: str) -> dict[str, str]:
    return {"tenant_id": str(tenant_id), "provider": str(provider)}


# --------------------------------------------------------------------------- #
# Repository                                                                  #
# --------------------------------------------------------------------------- #


class TenantCredentialRepository:
    """Envelope-encrypted CRUD on :class:`TenantCredential`.

    The repository owns the :class:`KMSProvider` — tests inject a
    :class:`FernetEnvKMS` with an ephemeral key; production wires the
    factory-built provider. Every encryption call passes
    ``context={"tenant_id": ..., "provider": ...}`` as AAD so a
    ciphertext row is cryptographically bound to its row key.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        kms: KMSProvider,
    ) -> None:
        self._engine = engine
        self._kms = kms
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

    # ------------------------------------------------------------------ #
    # Read                                                               #
    # ------------------------------------------------------------------ #

    async def get(
        self, tenant_id: uuid.UUID | str, provider: str
    ) -> CredentialPayload | None:
        """Return the decrypted payload or ``None`` if the row is absent."""
        tid = _to_uuid(tenant_id)
        async with self._sessionmaker() as db:
            stmt = (
                select(TenantCredential)
                .where(TenantCredential.tenant_id == tid)
                .where(TenantCredential.provider == provider)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        try:
            plaintext = await self._kms.decrypt(
                bytes(row.encrypted_blob),
                bytes(row.nonce or b""),
                context=_context_for(tid, provider),
            )
        except CredentialDecryptionError:
            raise
        except SecurityError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CredentialDecryptionError(
                f"unexpected failure during KMS decrypt: {exc}"
            ) from exc
        return _payload_from_bytes(plaintext)

    # ------------------------------------------------------------------ #
    # Write                                                              #
    # ------------------------------------------------------------------ #

    async def put(
        self,
        tenant_id: uuid.UUID | str,
        provider: str,
        payload: CredentialPayload,
    ) -> None:
        """Upsert the encrypted row. No-op on unchanged content."""
        if payload.provider != provider:
            raise ValueError(
                f"payload.provider={payload.provider!r} does not match "
                f"provider={provider!r}"
            )
        tid = _to_uuid(tenant_id)
        ciphertext, nonce = await self._kms.encrypt(
            _payload_to_bytes(payload),
            context=_context_for(tid, provider),
        )
        now = datetime.now(timezone.utc)

        async with self._sessionmaker() as db:
            async with db.begin():
                dialect = db.bind.dialect.name if db.bind else ""
                if dialect == "postgresql":
                    stmt = pg_insert(TenantCredential).values(
                        id=uuid.uuid4(),
                        tenant_id=tid,
                        provider=provider,
                        encrypted_blob=ciphertext,
                        nonce=nonce,
                        meta=dict(payload.meta),
                        rotated_at=payload.rotated_at,
                        created_at=now,
                        updated_at=now,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[
                            TenantCredential.tenant_id,
                            TenantCredential.provider,
                        ],
                        set_={
                            "encrypted_blob": stmt.excluded.encrypted_blob,
                            "nonce": stmt.excluded.nonce,
                            "meta": stmt.excluded.meta,
                            "rotated_at": stmt.excluded.rotated_at,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await db.execute(stmt)
                else:
                    # Portable upsert for SQLite-backed unit tests.
                    stmt = (
                        select(TenantCredential)
                        .where(TenantCredential.tenant_id == tid)
                        .where(TenantCredential.provider == provider)
                    )
                    existing = (await db.execute(stmt)).scalar_one_or_none()
                    if existing is None:
                        db.add(
                            TenantCredential(
                                id=uuid.uuid4(),
                                tenant_id=tid,
                                provider=provider,
                                encrypted_blob=ciphertext,
                                nonce=nonce,
                                meta=dict(payload.meta),
                                rotated_at=payload.rotated_at,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                    else:
                        existing.encrypted_blob = ciphertext
                        existing.nonce = nonce
                        existing.meta = dict(payload.meta)
                        existing.rotated_at = payload.rotated_at
                        existing.updated_at = now

    async def rotate(
        self,
        tenant_id: uuid.UUID | str,
        provider: str,
        new_payload: CredentialPayload,
    ) -> None:
        """Re-encrypt under the current KMS key and stamp ``rotated_at``."""
        stamped = new_payload.model_copy(
            update={"rotated_at": datetime.now(timezone.utc)}
        )
        await self.put(tenant_id, provider, stamped)

    async def delete(
        self, tenant_id: uuid.UUID | str, provider: str
    ) -> None:
        """Delete the row. No-op if absent."""
        tid = _to_uuid(tenant_id)
        async with self._sessionmaker() as db:
            async with db.begin():
                stmt = (
                    select(TenantCredential)
                    .where(TenantCredential.tenant_id == tid)
                    .where(TenantCredential.provider == provider)
                )
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing is not None:
                    await db.delete(existing)


# --------------------------------------------------------------------------- #
# Module-level resolver hook                                                  #
# --------------------------------------------------------------------------- #


_repo_singleton: TenantCredentialRepository | None = None


def set_repository_for_test(repo: TenantCredentialRepository | None) -> None:
    """Install a process-wide :class:`TenantCredentialRepository`.

    Used by tests and by the API service on startup when it already
    owns the :class:`AsyncEngine`. Passing ``None`` clears the singleton
    so the next call to :func:`resolve_tenant_credentials` re-builds it
    from env.
    """
    global _repo_singleton
    _repo_singleton = repo


def _get_repo() -> TenantCredentialRepository | None:
    """Return the process-wide repository or ``None`` if nothing is wired."""
    global _repo_singleton
    if _repo_singleton is not None:
        return _repo_singleton
    url = os.environ.get("VOYAGENT_DB_URL", "").strip()
    if not url:
        return None
    try:
        engine = create_async_engine(url, future=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TenantCredentialRepository engine build failed: %s", exc)
        return None
    kms = build_kms_provider()
    _repo_singleton = TenantCredentialRepository(engine, kms)
    return _repo_singleton


async def resolve_tenant_credentials(
    tenant_id: Any, provider: str
) -> dict[str, Any] | None:
    """Return the driver-shaped credentials dict for a ``(tenant, provider)``.

    Signature matches the hook
    :class:`voyagent_agent_runtime.tenant_registry.StorageCredentialResolver`
    looks up via ``getattr(storage, "resolve_tenant_credentials", None)``.
    Returns ``None`` on missing rows, the decrypted
    ``{**fields, **meta}`` dict otherwise.
    """
    repo = _get_repo()
    if repo is None:
        return None
    try:
        tid = _to_uuid(tenant_id)
    except Exception:  # noqa: BLE001
        # Deterministic fallback ids from the API's in-memory tenancy path
        # are not real UUIDs — the resolver should simply miss.
        return None

    try:
        payload = await repo.get(tid, provider)
    except CredentialDecryptionError:
        logger.exception(
            "credential decrypt failed for tenant=%s provider=%s", tid, provider
        )
        return None
    if payload is None:
        return None
    merged: dict[str, Any] = {}
    # meta comes first — fields override if they share keys, because
    # secret overrides metadata-as-default.
    merged.update(payload.meta)
    merged.update(payload.fields)
    return merged


__all__ = [
    "CredentialPayload",
    "TenantCredentialRepository",
    "resolve_tenant_credentials",
    "set_repository_for_test",
]
