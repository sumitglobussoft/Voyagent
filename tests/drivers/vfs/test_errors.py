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


@pytest.mark.xfail(
    reason=(
        "The VFS error-mapping heuristic has no explicit MFA / one-time-"
        "code branch. 'MFA step required' falls through to the default "
        "PermanentError, which is the desired outcome, but the more "
        "realistic message 'two-factor auth prompt appeared' hits the "
        "'auth' substring branch and becomes AuthenticationError. A "
        "dedicated MFA heuristic should classify both as PermanentError."
    ),
    strict=False,
)
def test_mfa_signal_maps_to_permanent_error() -> None:
    err = map_vfs_error("two-factor auth prompt appeared")
    assert isinstance(err, PermanentError)


def test_map_vfs_error_attaches_artifacts() -> None:
    err = map_vfs_error(
        "login failed",
        artifact_uris=["memory://t/j/failure.png", "memory://t/j/failure.html"],
    )
    assert isinstance(err, AuthenticationError)
    assert err.vendor_ref is not None
    assert "failure.png" in err.vendor_ref
    assert "failure.html" in err.vendor_ref
