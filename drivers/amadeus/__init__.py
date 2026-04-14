"""Voyagent Amadeus driver — reference implementation.

Implements `FareSearchDriver` and `PNRDriver` against the Amadeus
Self-Service REST APIs (https://test.api.amadeus.com). This is the
first concrete driver in Voyagent and doubles as the template other
drivers (Sabre, TBO, airline-direct NDC) should mirror.
"""

from __future__ import annotations

from .config import AmadeusConfig
from .driver import AmadeusDriver

__all__ = ["AmadeusConfig", "AmadeusDriver"]
