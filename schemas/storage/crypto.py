"""Envelope encryption for tenant secrets.

Voyagent's :class:`TenantCredential` rows store opaque ciphertext. The
plaintext is produced / consumed through a :class:`KMSProvider` — a
narrow Protocol that the rest of the codebase depends on, so the
underlying KMS can be swapped (Fernet-env v0 today; AWS KMS / GCP KMS
tomorrow) without touching call sites.

The v0 provider is :class:`FernetEnvKMS`: a ``cryptography.fernet.Fernet``
bound to a base64-url key in the ``VOYAGENT_KMS_KEY`` env var. Fernet
does not natively accept additional authenticated data (AAD); we
emulate AAD by appending a SHA-256 hash of the sorted ``context`` dict
to the plaintext before encryption and verifying it on decrypt. Callers
pass ``context={"tenant_id": ..., "provider": ...}`` so a ciphertext
pulled out from under one tenant cannot silently be decrypted under
another.

:class:`NullKMS` is the local-dev fallback used **only** when
``VOYAGENT_KMS_KEY`` is absent. Every call logs a loud WARNING.
Production must configure a real key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class SecurityError(Exception):
    """Base class for errors raised by the storage security primitives."""


class KMSConfigurationError(SecurityError):
    """Raised when the KMS provider cannot be constructed from env."""


class CredentialDecryptionError(SecurityError):
    """Raised when a stored credential blob cannot be decrypted.

    The ciphertext is corrupt, the KMS key has rotated without a
    re-encryption migration, or the ``context`` AAD does not match what
    was stamped into the blob at encryption time.
    """


# --------------------------------------------------------------------------- #
# Protocol                                                                    #
# --------------------------------------------------------------------------- #


@runtime_checkable
class KMSProvider(Protocol):
    """Minimal KMS surface used by :mod:`schemas.storage.credentials`.

    Two coroutines + a human-readable ``provider_name`` tag. Future
    providers (AWS KMS, GCP KMS) implement the same shape; callers
    never depend on provider-specific state.
    """

    provider_name: str

    async def encrypt(
        self,
        plaintext: bytes,
        *,
        context: dict[str, str] | None = None,
    ) -> tuple[bytes, bytes]:
        """Encrypt ``plaintext``. Returns ``(ciphertext, nonce)``.

        When the provider embeds the nonce / IV inside the ciphertext
        token (Fernet does), ``nonce`` may be ``b""``.
        """
        ...

    async def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        *,
        context: dict[str, str] | None = None,
    ) -> bytes:
        """Inverse of :meth:`encrypt`.

        Raises :class:`CredentialDecryptionError` on any failure —
        corrupt ciphertext, wrong key, AAD mismatch.
        """
        ...


# --------------------------------------------------------------------------- #
# AAD helper                                                                  #
# --------------------------------------------------------------------------- #


_AAD_MARKER = b"\x00VYG-AAD\x00"
_AAD_HASH_LEN = 32  # sha256 digest length


def _aad_digest(context: dict[str, str] | None) -> bytes:
    """Return a stable SHA-256 digest of ``context`` for emulated AAD.

    Sorted-key JSON keeps the digest deterministic across processes.
    An empty / ``None`` context yields the digest of ``{}`` so every
    ciphertext carries some AAD marker — callers that pass ``None`` on
    one side and ``{}`` on the other still verify correctly.
    """
    norm = dict(context or {})
    canonical = json.dumps(norm, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def _wrap_with_aad(plaintext: bytes, context: dict[str, str] | None) -> bytes:
    return _AAD_MARKER + _aad_digest(context) + plaintext


def _strip_and_verify_aad(
    framed: bytes, context: dict[str, str] | None
) -> bytes:
    head = _AAD_MARKER
    if not framed.startswith(head):
        raise CredentialDecryptionError(
            "decrypted blob is missing the Voyagent AAD marker"
        )
    digest = framed[len(head) : len(head) + _AAD_HASH_LEN]
    body = framed[len(head) + _AAD_HASH_LEN :]
    expected = _aad_digest(context)
    if digest != expected:
        raise CredentialDecryptionError(
            "context (AAD) mismatch on credential decrypt"
        )
    return body


# --------------------------------------------------------------------------- #
# Fernet-env provider                                                         #
# --------------------------------------------------------------------------- #


class FernetEnvKMS:
    """Envelope encryption via ``cryptography.fernet.Fernet``.

    The Fernet token already carries its own IV + HMAC. We store the
    whole token as ``ciphertext`` and leave ``nonce`` empty. Context
    AAD is enforced by the helpers above.
    """

    provider_name = "fernet_env"

    def __init__(self, key: str | bytes) -> None:
        try:
            from cryptography.fernet import Fernet
        except Exception as exc:  # pragma: no cover - import-time signal
            raise KMSConfigurationError(
                f"cryptography package unavailable: {exc}"
            ) from exc

        if isinstance(key, str):
            key_bytes = key.encode("ascii")
        else:
            key_bytes = bytes(key)
        try:
            self._fernet = Fernet(key_bytes)
        except Exception as exc:
            raise KMSConfigurationError(
                "VOYAGENT_KMS_KEY is not a valid base64-url Fernet key"
            ) from exc

    async def encrypt(
        self,
        plaintext: bytes,
        *,
        context: dict[str, str] | None = None,
    ) -> tuple[bytes, bytes]:
        framed = _wrap_with_aad(plaintext, context)
        token = self._fernet.encrypt(framed)
        return token, b""

    async def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        *,
        context: dict[str, str] | None = None,
    ) -> bytes:
        del nonce  # Fernet token is self-contained
        try:
            from cryptography.fernet import InvalidToken
        except Exception as exc:  # pragma: no cover
            raise CredentialDecryptionError(str(exc)) from exc

        try:
            framed = self._fernet.decrypt(bytes(ciphertext))
        except InvalidToken as exc:
            raise CredentialDecryptionError(
                "Fernet token is invalid, expired, or signed with a different key"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise CredentialDecryptionError(str(exc)) from exc
        return _strip_and_verify_aad(framed, context)

    @staticmethod
    def generate_key() -> str:
        """Mint a fresh base64-url Fernet key. Test-only helper."""
        try:
            from cryptography.fernet import Fernet
        except Exception as exc:  # pragma: no cover
            raise KMSConfigurationError(str(exc)) from exc
        return Fernet.generate_key().decode("ascii")


# --------------------------------------------------------------------------- #
# Null provider — dev-only                                                    #
# --------------------------------------------------------------------------- #


class NullKMS:
    """Pass-through "encryption" — local-dev fallback only.

    Logs a WARNING on every call. The :func:`build_kms_provider` factory
    only ever instantiates this when ``VOYAGENT_KMS_KEY`` is absent. It
    must never be used in production; tests should always inject a real
    :class:`FernetEnvKMS` with a test key.
    """

    provider_name = "null"

    async def encrypt(
        self,
        plaintext: bytes,
        *,
        context: dict[str, str] | None = None,
    ) -> tuple[bytes, bytes]:
        logger.warning(
            "NullKMS.encrypt called — credentials are NOT actually encrypted. "
            "Set VOYAGENT_KMS_KEY to a real Fernet key for production use."
        )
        return _wrap_with_aad(bytes(plaintext), context), b""

    async def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        *,
        context: dict[str, str] | None = None,
    ) -> bytes:
        del nonce
        logger.warning(
            "NullKMS.decrypt called — credentials were NOT actually encrypted. "
            "Set VOYAGENT_KMS_KEY to a real Fernet key for production use."
        )
        return _strip_and_verify_aad(bytes(ciphertext), context)


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


_VALID_PROVIDERS: tuple[str, ...] = ("fernet_env", "null")


def build_kms_provider(
    *,
    env: dict[str, str] | None = None,
) -> KMSProvider:
    """Return the configured :class:`KMSProvider`.

    Reads ``VOYAGENT_KMS_PROVIDER`` (default ``"fernet_env"``) and
    ``VOYAGENT_KMS_KEY``. If the Fernet provider is selected without a
    key configured, emits a WARNING and returns a :class:`NullKMS` so
    local-dev keeps working. Future providers (``aws_kms``, ``gcp_kms``)
    register their constructor in the ``if`` chain below.
    """
    source = env if env is not None else os.environ
    provider = (source.get("VOYAGENT_KMS_PROVIDER") or "fernet_env").strip().lower()

    if provider not in _VALID_PROVIDERS:
        raise KMSConfigurationError(
            f"VOYAGENT_KMS_PROVIDER={provider!r} is not one of {_VALID_PROVIDERS}"
        )

    if provider == "null":
        logger.warning(
            "VOYAGENT_KMS_PROVIDER=null — credentials will NOT be encrypted. "
            "Dev-only; production must use fernet_env (or a cloud KMS)."
        )
        return NullKMS()

    # fernet_env
    key = source.get("VOYAGENT_KMS_KEY", "").strip()
    if not key:
        logger.warning(
            "VOYAGENT_KMS_KEY is not set — falling back to NullKMS. "
            "Credentials will NOT be encrypted. Generate a key with "
            "FernetEnvKMS.generate_key() and set VOYAGENT_KMS_KEY."
        )
        return NullKMS()
    return FernetEnvKMS(key)


# --------------------------------------------------------------------------- #
# Small utility re-exports                                                    #
# --------------------------------------------------------------------------- #


def b64url(data: bytes) -> str:
    """Encode ``data`` as base64-url without padding (convenience helper)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


__all__ = [
    "CredentialDecryptionError",
    "FernetEnvKMS",
    "KMSConfigurationError",
    "KMSProvider",
    "NullKMS",
    "SecurityError",
    "b64url",
    "build_kms_provider",
]
