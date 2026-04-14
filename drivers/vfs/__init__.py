"""Voyagent VFS driver — reference :class:`VisaPortalDriver`.

This driver is the archetype for every portal-based driver: the actual
browser automation lives in the runner service, and the driver is a
thin adapter that submits :class:`Job` objects to a
:class:`BrowserRunnerClient` and maps :class:`JobResult` back into
canonical Voyagent types.

Future portal drivers (BLS, embassy-direct, airline extranets) should
mirror the structure here.
"""

from __future__ import annotations

from .config import VFSConfig
from .driver import VFSDriver

__all__ = ["VFSConfig", "VFSDriver"]
