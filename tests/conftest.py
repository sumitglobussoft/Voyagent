"""Shared fixtures for Voyagent canonical model tests.

These helpers exist so individual tests stay focused on the invariant under
test rather than boilerplate. They are intentionally small — each test file
imports what it needs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

import pytest

from schemas.canonical import Money


# --------------------------------------------------------------------------- #
# Entity IDs                                                                  #
# --------------------------------------------------------------------------- #

# A set of hand-crafted, valid UUIDv7-shaped strings. The canonical spec only
# enforces shape (pattern match), not strict UUIDv7 semantics, so these are
# fine to reuse across tests. Ten should be more than enough for any single
# test module.
_VALID_UUIDV7_POOL: list[str] = [
    "018f1a2b-3c4d-7e5f-8abc-0123456789ab",
    "018f1a2b-3c4d-7e5f-8abc-0123456789ac",
    "018f1a2b-3c4d-7e5f-8abc-0123456789ad",
    "018f1a2b-3c4d-7e5f-8abc-0123456789ae",
    "018f1a2b-3c4d-7e5f-8abc-0123456789af",
    "01900000-0000-7000-8000-000000000001",
    "01900000-0000-7000-8000-000000000002",
    "01900000-0000-7000-8000-000000000003",
    "01900000-0000-7000-9000-000000000004",
    "01900000-0000-7000-a000-000000000005",
]


@pytest.fixture
def make_entity_id() -> Callable[[], str]:
    """Return a callable that yields fresh valid EntityId strings.

    Each call returns a distinct value so tests can mint tenant_id, id,
    passenger_id, etc. without collisions.
    """

    counter = {"i": 0}

    def _factory() -> str:
        i = counter["i"]
        counter["i"] = i + 1
        if i < len(_VALID_UUIDV7_POOL):
            return _VALID_UUIDV7_POOL[i]
        # Synthesize additional ids if a test needs many.
        return f"01900000-0000-7000-8000-{i:012x}"

    return _factory


# --------------------------------------------------------------------------- #
# Money                                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def make_money() -> Callable[..., Money]:
    """Return a Money factory. `amount` may be a str/int/Decimal."""

    def _factory(amount: str | int | Decimal, currency: str = "INR") -> Money:
        return Money(amount=Decimal(str(amount)) if not isinstance(amount, Decimal) else amount, currency=currency)

    return _factory


# --------------------------------------------------------------------------- #
# Time                                                                        #
# --------------------------------------------------------------------------- #


@pytest.fixture
def utc_now() -> Callable[[], datetime]:
    """Return a callable that yields a fixed UTC datetime.

    Tests that assert "strictly after X" can add timedeltas; tests that just
    need *some* aware datetime should call this.
    """

    # A fixed instant keeps tests deterministic even if the suite is re-ordered.
    fixed = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)

    def _factory() -> datetime:
        return fixed

    return _factory


@pytest.fixture
def utc() -> Callable[..., datetime]:
    """Return a helper that builds tz-aware UTC datetimes.

    Signature mirrors ``datetime(year, month, day, ...)`` but always injects
    ``tzinfo=timezone.utc``.
    """

    def _factory(
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
    ) -> datetime:
        return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)

    return _factory
