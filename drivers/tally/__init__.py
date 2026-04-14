"""Voyagent Tally driver — reference implementation.

Implements :class:`AccountingDriver` against Tally Prime's Gateway Server
(XML over HTTP, ``localhost:9000`` by default). This is Voyagent's second
reference driver and the canonical template for desktop-bound accounting
backends (Busy, Marg, etc.).
"""

from __future__ import annotations

from .config import TallyConfig
from .driver import TallyDriver

__all__ = ["TallyConfig", "TallyDriver"]
