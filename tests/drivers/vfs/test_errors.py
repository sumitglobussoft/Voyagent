"""Unit tests for the runner-error-string to DriverError map."""

from __future__ import annotations

import pytest

from drivers._contracts.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermanentError,
    TransientError,
    UpstreamTimeoutError,
    ValidationFailedError,
)
from drivers.vfs.errors import map_vfs_error


@pytest.mark.parametrize(
    "error, expected",
    [
        ("client_timeout", UpstreamTimeoutError),
        ("job_timeout_exceeded", UpstreamTimeoutError),
        ("deadline_exceeded", UpstreamTimeoutError),
        ("CAPTCHA challenge encountered.", PermanentError),
        ("login failed — bad password", AuthenticationError),
        ("Unauthorized: session expired", AuthenticationError),
        ("no_slot_in_window", ConflictError),
        ("no appointment available", ConflictError),
        ("Resource not found (404)", NotFoundError),
        ("validation error: required field missing", ValidationFailedError),
        ("Invalid field value", ValidationFailedError),
        ("transient_retry: network blip", TransientError),
        ("temporary failure", TransientError),
        ("Unknown weird failure", PermanentError),
        (None, PermanentError),
    ],
)
def test_map_vfs_error(error: str | None, expected: type) -> None:
    err = map_vfs_error(error)
    assert isinstance(err, expected)
    assert err.driver == "vfs"


@pytest.mark.parametrize(
    "error_text",
    [
        "CAPTCHA challenge encountered on page 2",
        "captcha solve timeout",
    ],
)
def test_captcha_signals_are_permanent_errors(error_text: str) -> None:
    """A CAPTCHA signal is not retryable — the driver must raise a
    :class:`PermanentError`, never a :class:`TransientError`."""
    err = map_vfs_error(error_text)
    assert isinstance(err, PermanentError)
    assert not isinstance(err, TransientError)


@pytest.mark.parametrize(
    "signal",
    [
        "two-factor auth prompt appeared",
        "2FA challenge required on step 3",
        "Please enter the OTP sent to your phone",
        "one-time password required",
        "MFA verification required",
        "multi-factor authentication required",
        "verification code requested",
    ],
)
def test_mfa_signal_maps_to_permanent_error(signal: str) -> None:
    """MFA signals must never be classified as ``AuthenticationError`` —
    retrying auth with the same credentials won't solve a human-in-the-loop
    challenge. :class:`PermanentError` kicks it up to human escalation."""
    err = map_vfs_error(signal)
    # Exact class, not a subclass that happens to be AuthenticationError.
    assert isinstance(err, PermanentError)
    assert not isinstance(err, AuthenticationError)
    assert err.driver == "vfs"
    # Message must identify this as MFA so humans reading logs know why.
    assert "MFA" in str(err) or "2FA" in str(err)


def test_plain_wrong_password_still_maps_to_authentication_error() -> None:
    """Regression guard: the MFA heuristic must not swallow plain auth failures.

    A wrong-password error (no MFA keywords) is legitimate
    :class:`AuthenticationError` territory — the orchestrator can
    refresh creds and retry. This test pins that behaviour so the MFA
    branch stays narrow.
    """
    err = map_vfs_error("login failed: invalid password")
    assert isinstance(err, AuthenticationError)
    assert not isinstance(err, PermanentError)


def test_map_vfs_error_attaches_artifacts() -> None:
    err = map_vfs_error(
        "login failed",
        artifact_uris=["memory://t/j/failure.png", "memory://t/j/failure.html"],
    )
    assert isinstance(err, AuthenticationError)
    assert err.vendor_ref is not None
    assert "failure.png" in err.vendor_ref
    assert "failure.html" in err.vendor_ref
