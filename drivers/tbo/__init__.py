"""Voyagent TBO driver — Travel Boutique Online hotel aggregator.

Implements :class:`HotelSearchDriver` and :class:`HotelBookingDriver`
against the TBO Hotels REST API. v0 is a scaffold: search and
check_rate have real HTTP wiring, book/cancel/read are declared
``not_supported`` in the manifest until credentials and live docs are
available — see :mod:`drivers.tbo.manifest`.
"""

from __future__ import annotations

from .config import TBOConfig
from .driver import TBODriver

__all__ = ["TBOConfig", "TBODriver"]
