"""Password hashing using argon2id.

Uses the ``argon2-cffi`` library configured from :class:`AuthSettings`.
Hashes are PHC-format strings (``$argon2id$...``) so the cost
parameters travel with the hash and we can rotate them without a data
migration: :func:`needs_rehash` reports whether an existing hash uses
the current cost.
"""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

from .settings import get_auth_settings


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    """Build a single :class:`PasswordHasher` from settings.

    Cached because argon2 setup is mildly expensive and the cost
    parameters are process-wide.
    """
    settings = get_auth_settings()
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(plain: str) -> str:
    """Return an argon2id PHC string for ``plain``."""
    return _hasher().hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    """Return ``True`` iff ``plain`` matches ``hashed``.

    Returns ``False`` on a mismatch or on a malformed hash. Constant-
    time against an argon2 verify call so callers should always run
    this — including against a dummy hash on missing-user paths — to
    avoid a timing oracle.
    """
    try:
        return _hasher().verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except InvalidHash:
        return False


def needs_rehash(hashed: str) -> bool:
    """Return ``True`` if ``hashed`` was minted under different cost params."""
    return _hasher().check_needs_rehash(hashed)


# A process-cached dummy hash used by the sign-in path on missing-user
# lookups so the failure path takes the same wall-clock time as a real
# password verify and we do not leak email-existence via a timing side
# channel. Generated lazily because the cost parameters depend on
# settings.
@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Return a cached argon2id hash of a fixed throwaway plaintext."""
    return _hasher().hash("voyagent-dummy-password")


def burn_dummy_verify() -> None:
    """Verify a fixed wrong password against the cached dummy hash.

    Called by the sign-in service when no user row matches the supplied
    email so the failure path takes the same wall-clock time as a real
    password mismatch. The return value is intentionally discarded.
    """
    try:
        _hasher().verify(_dummy_hash(), "not-the-password")
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "burn_dummy_verify",
    "hash_password",
    "needs_rehash",
    "verify_password",
]
