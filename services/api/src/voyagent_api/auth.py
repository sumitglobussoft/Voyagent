"""Compatibility shim for the in-house auth subsystem.

The real implementation now lives in :mod:`voyagent_api.auth_inhouse`.
This module re-exports the names other modules used to import from
the old Clerk-backed file so chat/tenancy/audit don't have to change.
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
