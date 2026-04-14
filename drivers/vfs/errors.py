"""Runner-side error codes -> canonical :class:`DriverError` types.

The browser-runner returns free-form ``error`` strings on a failed
:class:`JobResult`. Rather than parse them structurally everywhere,
the driver funnels every non-success result through
:func:`map_vfs_error`, which emits the canonical
:class:`DriverError` subclass.
"""

from __future__ import annotations

from drivers._contracts.errors import (
    AuthenticationError,
    ConflictError,
    DriverError,
    NotFoundError,
    PermanentError,
    TransientError,
    UpstreamTimeoutError,
    ValidationFailedError,
)

DRIVER_NAME = "vfs"


# Signals that unambiguously mean "the portal wants a human to type a
# one-time code". These must be classified BEFORE the generic "auth"
# substring check, because "two-factor auth" would otherwise be swept
# into AuthenticationError and the orchestrator would retry with the
# same dead-end credentials. Keep these lowercase; the classifier
# lowercases the input before comparing.
_MFA_SIGNALS: tuple[str, ...] = (
    "two-factor",
    "two factor",
    "2fa",
    "mfa",
    "multi-factor",
    "multi factor",
    "otp",
    "one-time password",
    "one time password",
    "verification code",
)


def _lower(s: str | None) -> str:
    return (s or "").lower()


def _is_mfa_signal(low: str) -> bool:
    return any(sig in low for sig in _MFA_SIGNALS)


def map_vfs_error(
    error: str | None,
    *,
    artifact_uris: list[str] | None = None,
) -> DriverError:
    """Translate a runner ``error`` string into a canonical driver error.

    Heuristics only — the runner does not expose structured error
    codes yet. ``artifact_uris`` are stitched into ``vendor_ref`` so
    the failure artifacts travel with the exception.

    Ordering matters:

    1. timeouts — structurally distinct, never overlap with auth;
    2. MFA / 2FA / OTP signals — always :class:`PermanentError`, even
       when the string also contains the word ``auth``. Checked
       before CAPTCHA and before the generic auth substring so that
       "two-factor auth prompt" can't leak into
       :class:`AuthenticationError`;
    3. CAPTCHA — :class:`PermanentError`, likewise human-only;
    4. generic auth / login / password — :class:`AuthenticationError`
       (retry with refreshed credentials is legitimate here);
    5. the rest of the heuristics follow.
    """
    msg = error or "unknown VFS failure"
    artifacts = ", ".join(artifact_uris or [])
    vendor_ref = artifacts or None

    low = _lower(error)

    if "client_timeout" in low or "job_timeout" in low or "timeout" in low:
        return UpstreamTimeoutError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if "deadline_exceeded" in low:
        return UpstreamTimeoutError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if _is_mfa_signal(low):
        return PermanentError(
            DRIVER_NAME,
            f"VFS portal requires MFA/2FA human intervention: {msg}",
            vendor_ref=vendor_ref,
        )
    if "captcha" in low:
        return PermanentError(DRIVER_NAME, "CAPTCHA challenge encountered.", vendor_ref=vendor_ref)
    if "login" in low or "auth" in low or "unauthorized" in low or "password" in low:
        return AuthenticationError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if "no_handler" in low:
        return PermanentError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if "no_slot" in low or "no appointment" in low or "unavailable" in low:
        return ConflictError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if "not found" in low or "404" in low:
        return NotFoundError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if "validation" in low or "invalid" in low or "required" in low:
        return ValidationFailedError(DRIVER_NAME, msg, vendor_ref=vendor_ref)
    if "transient_retry" in low or "network" in low or "temporar" in low:
        return TransientError(DRIVER_NAME, msg, vendor_ref=vendor_ref)

    return PermanentError(DRIVER_NAME, msg, vendor_ref=vendor_ref)


__all__ = ["DRIVER_NAME", "map_vfs_error"]
