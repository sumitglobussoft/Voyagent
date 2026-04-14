"""Driver contracts — the adapter-layer boundary of Voyagent.

Every external-system integration implements one or more of the Protocols
re-exported here, and publishes a `CapabilityManifest`. Agents and tools
never import from concrete driver packages; they import only canonical
types (from `schemas.canonical`) and these contracts.

See `drivers/_contracts/README.md` for implementer guidance.
"""

from __future__ import annotations

from .accounting import AccountingDriver
from .bank import BankDriver, BankTransaction
from .base import Driver
from .bsp import BSPDriver
from .card import CardDriver, CardTransaction, CardUtilization
from .document import DocumentDriver
from .errors import (
    AuthenticationError,
    AuthorizationError,
    CapabilityNotSupportedError,
    ConflictError,
    DriverError,
    NotFoundError,
    PermanentError,
    RateLimitError,
    TransientError,
    UpstreamTimeoutError,
    ValidationFailedError,
)
from .fare_search import FareSearchCriteria, FareSearchDriver
from .hotel_booking import HotelBookingDriver
from .hotel_search import HotelOffer, HotelSearchCriteria, HotelSearchDriver
from .manifest import CapabilityManifest
from .messaging import MessagingDriver
from .payment import PaymentDriver
from .pnr import PNRDriver
from .statutory import StatutoryDriver
from .visa_portal import VisaPortalDriver

__all__ = [
    # base + manifest
    "CapabilityManifest",
    "Driver",
    # capability interfaces
    "AccountingDriver",
    "BSPDriver",
    "BankDriver",
    "CardDriver",
    "DocumentDriver",
    "FareSearchDriver",
    "HotelBookingDriver",
    "HotelSearchDriver",
    "MessagingDriver",
    "PNRDriver",
    "PaymentDriver",
    "StatutoryDriver",
    "VisaPortalDriver",
    # driver-layer helper types
    "BankTransaction",
    "CardTransaction",
    "CardUtilization",
    "FareSearchCriteria",
    "HotelOffer",
    "HotelSearchCriteria",
    # errors
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
