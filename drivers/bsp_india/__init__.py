"""Voyagent BSP India driver — reference implementation.

Implements :class:`BSPDriver` for the Indian instance of IATA's Billing and
Settlement Plan. BSP India runs a fortnightly settlement cycle; agents
download HAF (Host-to-Agent File) statements from BSPlink and reconcile
them against their internal ticket records.

BSP operates per country — the country-scoped :attr:`BSPIndiaDriver.name`
(``"bsp_india"``) makes room for sibling drivers such as ``bsp_uae`` and
``bsp_uk``. Those siblings will mirror this package's shape but share no
code at the driver level — file formats, submission cycles, and ADM/ACM
workflows differ per country.
"""

from __future__ import annotations

from .config import BSPIndiaConfig
from .driver import BSPIndiaDriver

__all__ = ["BSPIndiaConfig", "BSPIndiaDriver"]
