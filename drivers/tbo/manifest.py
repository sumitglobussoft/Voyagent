"""Static capability manifest for the TBO driver."""

from __future__ import annotations

from drivers._contracts.manifest import CapabilityManifest


def build_manifest(version: str) -> CapabilityManifest:
    """Return a :class:`CapabilityManifest` describing the TBO driver's surface.

    v0 honest declaration: search and check_rate have real HTTP wiring
    but no verified mapping against a live credentialed endpoint, so
    they ship as ``partial``. Booking verbs are ``not_supported`` until
    credentials land and we can confirm the full request/response
    shape end-to-end.
    """
    return CapabilityManifest(
        driver="tbo",
        version=version,
        implements=["HotelSearchDriver", "HotelBookingDriver"],
        capabilities={
            "search": "partial",
            "check_rate": "partial",
            "book": "not_supported",
            "cancel": "not_supported",
            "read": "not_supported",
        },
        transport=["rest"],
        requires=["tenant_credentials"],
        tenant_config_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["username", "password"],
            "properties": {
                "username": {"type": "string", "minLength": 1},
                "password": {"type": "string", "minLength": 1},
                "api_base": {"type": "string", "format": "uri"},
            },
            "additionalProperties": False,
        },
    )


__all__ = ["build_manifest"]
