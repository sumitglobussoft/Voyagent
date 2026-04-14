"""Driver error hierarchy.

Every driver implementation raises these types — never vendor-native
exceptions. The orchestrator and tool runtime classify retries, approval
escalation, and user-visible messaging off this hierarchy.

`retry_after_seconds` and `vendor_ref` are optional diagnostic fields that
stay at the driver boundary; they do not propagate into canonical records.
"""

from __future__ import annotations


class DriverError(Exception):
    """Base class for every exception raised across the driver boundary.

    Attributes:
        driver: Driver identifier (matches `CapabilityManifest.driver`).
        message: Human-readable description.
        vendor_ref: Vendor's native error id or message, for debugging.
        retry_after_seconds: Hint for retryable errors. None when unknown.
    """

    def __init__(
        self,
        driver: str,
        message: str,
        *,
        vendor_ref: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(f"[{driver}] {message}")
        self.driver = driver
        self.message = message
        self.vendor_ref = vendor_ref
        self.retry_after_seconds = retry_after_seconds


class CapabilityNotSupportedError(DriverError):
    """The driver is registered but cannot perform the requested capability.

    Raised when the manifest declares `not_supported` or the vendor has
    revoked the feature. The orchestrator may fall back to graceful
    degradation (e.g. generating a file for manual import).
    """


class AuthenticationError(DriverError):
    """Credentials are missing, malformed, or rejected by the vendor."""


class AuthorizationError(DriverError):
    """Credentials authenticated but lack permission for this operation."""


class RateLimitError(DriverError):
    """Vendor is rate-limiting the tenant. Retry after `retry_after_seconds`."""


class TransientError(DriverError):
    """A retryable failure — network blip, 5xx, transient vendor fault.

    The runtime is allowed to retry with backoff up to the tool's policy.
    """


class PermanentError(DriverError):
    """A non-retryable failure. Retrying will not change the outcome."""


class ValidationFailedError(DriverError):
    """Input violates vendor-side validation (bad format, missing required field).

    Distinct from Pydantic validation at the canonical boundary — this is the
    vendor rejecting semantically-valid canonical input.
    """


class NotFoundError(DriverError):
    """The referenced vendor entity does not exist or is not visible."""


class ConflictError(DriverError):
    """The vendor rejected the operation due to state conflict.

    Examples: PNR already cancelled, ticket already voided, invoice already
    paid, booking outside modifiable window.
    """


class UpstreamTimeoutError(DriverError):
    """The vendor did not respond within the driver's timeout budget.

    Treat as transient unless the operation is known non-idempotent — see
    each capability's docstring for idempotency guidance.
    """


__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "CapabilityNotSupportedError",
    "ConflictError",
    "DriverError",
    "NotFoundError",
    "PermanentError",
    "RateLimitError",
    "TransientError",
    "UpstreamTimeoutError",
    "ValidationFailedError",
]
