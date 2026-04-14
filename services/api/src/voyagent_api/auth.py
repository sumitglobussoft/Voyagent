"""Compatibility shim re-exporting the in-house auth public surface.

The real implementation lives in :mod:`voyagent_api.auth_inhouse`. This
module re-exports :class:`AuthenticatedPrincipal` and the principal
dependencies under their canonical names so chat / tenancy / audit can
keep importing ``voyagent_api.auth`` unchanged.
"""

from __future__ import annotations

from .auth_inhouse.deps import (
    AuthenticatedPrincipal,
    get_current_principal as get_principal,
    get_current_principal_optional as get_principal_optional,
)

__all__ = [
    "AuthenticatedPrincipal",
    "get_principal",
    "get_principal_optional",
]
