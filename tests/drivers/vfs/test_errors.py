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


def test_map_vfs_error_attaches_artifacts() -> None:
    err = map_vfs_error(
        "login failed",
        artifact_uris=["memory://t/j/failure.png", "memory://t/j/failure.html"],
    )
    assert isinstance(err, AuthenticationError)
    assert err.vendor_ref is not None
    assert "failure.png" in err.vendor_ref
    assert "failure.html" in err.vendor_ref
