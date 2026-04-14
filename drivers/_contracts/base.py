"""Base `Driver` protocol.

Every capability interface in this package extends `Driver`. Concrete drivers
do not subclass anything; they simply expose `name`, `version`, and a
`manifest()` method, and Python's structural typing recognizes them.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .manifest import CapabilityManifest


@runtime_checkable
class Driver(Protocol):
    """Minimum surface every driver exposes.

    The registry uses `manifest()` to decide routing and degradation. `name`
    and `version` mirror the manifest for cheap identification without a
    full parse.

    Side effects: `manifest()` is pure and must be safe to call at any time.
    """

    name: str
    version: str

    def manifest(self) -> CapabilityManifest:
        """Return the driver's capability manifest.

        Must be deterministic within a process lifetime. May read immutable
        tenant config at construction time; must not perform I/O here.
        """
        ...


__all__ = ["Driver"]
