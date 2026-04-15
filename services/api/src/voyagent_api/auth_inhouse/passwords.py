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


# --------------------------------------------------------------------------- #
# Password strength                                                           #
# --------------------------------------------------------------------------- #


class PasswordTooWeakError(ValueError):
    """Raised by :func:`validate_password_strength` on a weak password.

    The ``code`` attribute carries a stable machine-readable error code
    (e.g. ``password_too_short``) so routes can surface it as a detail
    string without string-matching the English message.
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


# Small hand-rolled blocklist of the most obvious bad passwords. Kept
# deliberately short — this is NOT a "top N leaked passwords" list, just
# a guardrail against the passwords users actually try first. Compared
# case-insensitively after whitespace stripping.
_COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "password1234",
        "passw0rd",
        "passw0rd1",
        "passw0rd123",
        "qwerty",
        "qwerty123",
        "qwertyuiop",
        "qwerty1234",
        "letmein",
        "letmein1",
        "letmein123",
        "welcome",
        "welcome1",
        "welcome123",
        "admin",
        "admin1",
        "admin123",
        "administrator",
        "root",
        "root123",
        "toor",
        "iloveyou",
        "iloveyou1",
        "monkey",
        "monkey123",
        "dragon",
        "dragon123",
        "master",
        "master123",
        "abc123",
        "abc12345",
        "abcd1234",
        "123abc",
        "123456",
        "1234567",
        "12345678",
        "123456789",
        "1234567890",
        "111111",
        "000000",
        "696969",
        "trustno1",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "superman",
        "batman123",
        "voyagent",
        "voyagent1",
        "voyagent123",
        "travel123",
        "changeme",
        "changeme1",
        "changeme123",
    }
)


_MIN_PASSWORD_LENGTH = 10
_MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password: str) -> None:
    """Raise :class:`PasswordTooWeakError` if ``password`` is too weak.

    Deterministic rule-based checker — no zxcvbn. Rules applied, in
    order:

    1. Not exclusively whitespace.
    2. Length >= 10.
    3. Length <= 128 (defensive upper bound).
    4. Contains at least one letter.
    5. Contains at least one digit.
    6. Not in the :data:`_COMMON_PASSWORDS` blocklist.
    """
    if password is None or not password.strip():
        raise PasswordTooWeakError("password_blank")
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise PasswordTooWeakError("password_too_short")
    if len(password) > _MAX_PASSWORD_LENGTH:
        raise PasswordTooWeakError("password_too_long")
    if not any(c.isalpha() for c in password):
        raise PasswordTooWeakError("password_no_letter")
    if not any(c.isdigit() for c in password):
        raise PasswordTooWeakError("password_no_digit")
    if password.strip().lower() in _COMMON_PASSWORDS:
        raise PasswordTooWeakError("password_common")


__all__ = [
    "PasswordTooWeakError",
    "burn_dummy_verify",
    "hash_password",
    "needs_rehash",
    "validate_password_strength",
    "verify_password",
]
