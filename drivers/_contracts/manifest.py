"""Capability manifest — every driver must publish one.

The orchestrator reads manifests at startup (and on hot-reload) to decide:
  - which driver to route a canonical tool call to,
  - whether to offer graceful degradation when a capability is partial,
  - whether a feature is disabled for a tenant's plan or deployment shape,
  - what tenant configuration a driver requires before it can run.

See docs/ARCHITECTURE.md, Layer 2, for the example that drove this shape.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _manifest_config() -> ConfigDict:
    """Shared Pydantic config mirroring canonical-model strictness."""
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CapabilityManifest(BaseModel):
    """What a driver can and cannot do, declared up-front.

    Support levels in `capabilities` are free-form strings so drivers can
    express nuance beyond binary supported/unsupported. Canonical values:
      - `"full"`          — fully supported, behaves like a first-class API.
      - `"partial"`       — supported with caveats; driver docstrings explain.
      - `"not_supported"` — raises CapabilityNotSupportedError if invoked.
    Anything else (e.g. `"supported_via_xml_import"`) is a driver-defined tag
    the orchestrator can branch on.
    """

    model_config = _manifest_config()

    driver: str = Field(
        description="Stable driver identifier. Matches the value written to canonical `source` fields.",
    )
    version: str = Field(
        description="Driver package version (SemVer). Bumped when the driver's behavior changes.",
    )
    implements: list[str] = Field(
        description="Capability interface names this driver satisfies, e.g. ['PNRDriver', 'FareSearchDriver'].",
    )
    capabilities: dict[str, str] = Field(
        default_factory=dict,
        description="Capability key → support level. Keys are dotted names like 'journal_entry.post'.",
    )
    transport: list[str] = Field(
        default_factory=list,
        description="How the driver talks to the vendor: 'rest', 'soap', 'xml_over_http', 'odbc', 'browser', ...",
    )
    requires: list[str] = Field(
        default_factory=list,
        description="Runtime prerequisites: 'desktop_host', 'browser_runner', 'tenant_credentials', ...",
    )
    tenant_config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema (draft 2020-12) describing per-tenant configuration the driver needs.",
    )


__all__ = ["CapabilityManifest"]
