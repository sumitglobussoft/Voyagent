"""VFS Global (India outbound) handlers.

SCOPE
=====

These handlers implement a *plausible* VFS Global visa-applicant flow —
checklist scrape, form fill, document upload, appointment pick, status
read. They are scaffolding, not a production integration.

PLACEHOLDERS
============

Every URL and CSS selector in this module is a placeholder marked
``# PLACEHOLDER:``. Real VFS deployments vary per destination country
and per visa category — selectors and even page structure differ
between (e.g.) ``UK-from-India`` and ``Schengen-from-India`` flows.

A tenant operating on real VFS pages must:

1. Supply a per-destination override via :data:`SELECTOR_OVERRIDES`.
2. Negotiate an automation agreement with VFS — unattended automation
   against VFS portals without explicit tenant authorization may
   violate terms of service and is not Voyagent's intent. The runner
   is designed for supervised tenant-initiated flows only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from schemas.canonical import VisaStatus

from .. import steps
from . import HandlerContext

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Placeholder selector/URL packs                                              #
# --------------------------------------------------------------------------- #


# PLACEHOLDER: these are illustrative only. Real VFS pages are distinct per
# destination; the production rollout ships a per-country selector pack.
_DEFAULT_SELECTORS: dict[str, str] = {
    "login_url": "https://portal.example.invalid/vfs/login",
    "login_email": "#email",
    "login_password": "#password",
    "login_submit": "button[data-voyagent-login]",
    "checklist_url": "https://portal.example.invalid/vfs/checklist",
    "checklist_item": ".checklist-row",
    "checklist_item_label": ".checklist-row .label",
    "checklist_item_required": ".checklist-row .required",
    "form_url": "https://portal.example.invalid/vfs/application/form",
    "form_submit": "button[data-voyagent-submit]",
    "form_confirmation_ref": "[data-voyagent-application-ref]",
    "upload_selector": "input[type=file][data-voyagent-upload]",
    "appointment_url": "https://portal.example.invalid/vfs/appointment",
    "appointment_slot": ".slot-available",
    "appointment_slot_time": ".slot-available [data-time]",
    "appointment_confirm": "button[data-voyagent-confirm-slot]",
    "status_url": "https://portal.example.invalid/vfs/status",
    "status_text": "[data-voyagent-status]",
}


#: Per-destination selector/URL overrides, keyed by ISO 3166-1 alpha-2.
#:
#: The VFS driver passes ``inputs['destination_country']`` when known;
#: handlers merge that country's overrides on top of the defaults. In
#: v0 this mapping is empty — tenants populate it via a future config
#: mechanism (likely a JSON blob from the tenant-credentials store).
SELECTOR_OVERRIDES: dict[str, dict[str, str]] = {}


def _resolve(country: str | None) -> dict[str, str]:
    """Merge placeholders with the country-specific override pack."""
    resolved = dict(_DEFAULT_SELECTORS)
    if country and country in SELECTOR_OVERRIDES:
        resolved.update(SELECTOR_OVERRIDES[country])
    return resolved


# --------------------------------------------------------------------------- #
# Login helper                                                                #
# --------------------------------------------------------------------------- #


async def _ensure_logged_in(ctx: HandlerContext, selectors: dict[str, str]) -> None:
    """Log in using the resolved credentials.

    Skips if already authenticated. v0 always re-navigates to the login
    page and submits; a future optimisation is to detect an existing
    authenticated session via a session-detection selector.
    """
    if ctx.credentials is None:
        raise RuntimeError(
            "vfs handler requires credentials; tenant_credentials_ref did not resolve."
        )
    await steps.goto(ctx.page, selectors["login_url"])
    await steps.fill(
        ctx.page,
        selectors["login_email"],
        ctx.credentials.username,
        mask=False,
    )
    await steps.fill(
        ctx.page,
        selectors["login_password"],
        ctx.credentials.password,
        mask=True,  # NEVER emit password text to logs or artifact filenames.
    )
    await steps.click(ctx.page, selectors["login_submit"])
    # PLACEHOLDER: real VFS flows surface "wrong password" or a CAPTCHA
    # gate here; tenant-specific selectors will check for those.


# --------------------------------------------------------------------------- #
# Handlers                                                                    #
# --------------------------------------------------------------------------- #


async def handle_vfs_checklist_prepare(ctx: HandlerContext) -> dict[str, Any]:
    """Scrape a document checklist for the destination + category.

    Inputs:
      * ``destination_country`` (CountryCode)
      * ``visa_category`` (str)
      * ``passenger_id`` (EntityId; echoed back unchanged)

    Output shape matches :class:`VisaChecklistItem` fields:

    .. code-block:: python

        {"items": [
            {"label": {"default": "Passport"}, "required": True, "collected": False},
            ...
        ]}
    """
    country = ctx.job.inputs.get("destination_country")
    selectors = _resolve(country)
    await _ensure_logged_in(ctx, selectors)
    await steps.goto(ctx.page, selectors["checklist_url"])

    # PLACEHOLDER: VFS renders checklists as a list of rows; we iterate
    # with page.query_selector_all. The FakePage used in tests implements
    # the same surface.
    rows = await ctx.page.query_selector_all(selectors["checklist_item"])
    items: list[dict[str, Any]] = []
    for row in rows:
        label_el = await row.query_selector(".label")
        required_el = await row.query_selector(".required")
        label_text = (await label_el.text_content()) if label_el else ""
        required_text = (await required_el.text_content()) if required_el else "true"
        items.append(
            {
                "label": {"default": (label_text or "").strip()},
                "required": (required_text or "true").strip().lower() != "false",
                "collected": False,
                "document_id": None,
                "notes": None,
            }
        )

    return {
        "items": items,
        "destination_country": country,
        "visa_category": ctx.job.inputs.get("visa_category"),
    }


async def handle_vfs_fill_form(ctx: HandlerContext) -> dict[str, Any]:
    """Fill + submit the application form, return the resulting application ref.

    Inputs:
      * ``destination_country`` (CountryCode, optional)
      * ``visa_file_id`` (EntityId)
      * ``field_values`` (dict[str, Any]) — keys are form field selectors,
        values are strings to type. Values are NOT masked by default;
        pass ``{"__mask__": ["#national_id"]}`` to redact specific
        selectors from logs.
    """
    country = ctx.job.inputs.get("destination_country")
    selectors = _resolve(country)
    field_values: dict[str, Any] = dict(ctx.job.inputs.get("field_values") or {})
    mask_set = set(field_values.pop("__mask__", []) or [])

    await _ensure_logged_in(ctx, selectors)
    await steps.goto(ctx.page, selectors["form_url"])

    for sel, value in field_values.items():
        await steps.fill(
            ctx.page,
            sel,
            str(value),
            mask=sel in mask_set,
        )

    await steps.click(ctx.page, selectors["form_submit"])
    application_ref = await steps.extract_text(
        ctx.page, selectors["form_confirmation_ref"]
    )

    return {
        "visa_file_id": ctx.job.inputs.get("visa_file_id"),
        "application_ref": application_ref,
    }


async def handle_vfs_upload_document(ctx: HandlerContext) -> dict[str, Any]:
    """Attach a document file to the VFS draft.

    Inputs:
      * ``visa_file_id`` (EntityId)
      * ``document_id`` (EntityId)
      * ``local_path`` (str) — filesystem path on the worker. The worker
        is expected to have fetched the blob from storage before
        enqueuing; the handler does not reach into storage itself.
    """
    country = ctx.job.inputs.get("destination_country")
    selectors = _resolve(country)
    local_path = str(ctx.job.inputs["local_path"])

    await _ensure_logged_in(ctx, selectors)
    await steps.upload_file(
        ctx.page,
        selectors["upload_selector"],
        local_path,
    )

    return {
        "visa_file_id": ctx.job.inputs.get("visa_file_id"),
        "document_id": ctx.job.inputs.get("document_id"),
        "uploaded": True,
    }


async def handle_vfs_book_appointment(ctx: HandlerContext) -> dict[str, Any]:
    """Pick the earliest slot inside ``preferred_window`` and confirm.

    Inputs:
      * ``visa_file_id`` (EntityId)
      * ``preferred_window`` (dict[str, str]) with ``start`` and optional
        ``end`` in ISO-8601 UTC.

    Output includes the chosen datetime. Callers must note: the portal
    may surface only the nearest available slot *after* the window
    start when nothing matches inside the window — handlers log the
    deviation but still return a datetime.
    """
    country = ctx.job.inputs.get("destination_country")
    selectors = _resolve(country)
    window = ctx.job.inputs.get("preferred_window") or {}
    start_iso = window.get("start")
    end_iso = window.get("end")
    if not start_iso:
        raise ValueError("vfs.book_appointment: preferred_window.start is required.")
    start = datetime.fromisoformat(start_iso).astimezone(timezone.utc)
    end = (
        datetime.fromisoformat(end_iso).astimezone(timezone.utc)
        if end_iso
        else None
    )

    await _ensure_logged_in(ctx, selectors)
    await steps.goto(ctx.page, selectors["appointment_url"])

    slots = await ctx.page.query_selector_all(selectors["appointment_slot"])
    chosen: datetime | None = None
    chosen_el: Any = None
    for slot in slots:
        time_attr_el = await slot.query_selector("[data-time]")
        if time_attr_el is None:
            continue
        raw = await time_attr_el.get_attribute("data-time")
        if not raw:
            continue
        try:
            slot_dt = datetime.fromisoformat(raw).astimezone(timezone.utc)
        except ValueError:
            continue
        if slot_dt < start:
            continue
        if end is not None and slot_dt > end:
            continue
        if chosen is None or slot_dt < chosen:
            chosen = slot_dt
            chosen_el = slot

    if chosen is None:
        logger.info(
            "vfs.book_appointment.no_slot_in_window",
            extra={
                "window_start": start_iso,
                "window_end": end_iso,
                "tenant_id": ctx.tenant_id,
            },
        )
        # PLACEHOLDER: fallback — choose the earliest slot regardless.
        for slot in slots:
            time_attr_el = await slot.query_selector("[data-time]")
            if time_attr_el is None:
                continue
            raw = await time_attr_el.get_attribute("data-time")
            if not raw:
                continue
            try:
                slot_dt = datetime.fromisoformat(raw).astimezone(timezone.utc)
            except ValueError:
                continue
            if chosen is None or slot_dt < chosen:
                chosen = slot_dt
                chosen_el = slot
    if chosen is None or chosen_el is None:
        raise RuntimeError("vfs.book_appointment: no appointment slots available.")

    await chosen_el.click()
    await steps.click(ctx.page, selectors["appointment_confirm"])

    return {
        "visa_file_id": ctx.job.inputs.get("visa_file_id"),
        "appointment_at": chosen.isoformat(),
    }


# Canonical status mapping. Keep keys lowercase for case-insensitive
# lookup; values must be :class:`VisaStatus` members.
_STATUS_MAP: dict[str, VisaStatus] = {
    "draft": VisaStatus.DRAFT,
    "submitted": VisaStatus.APPLICATION_SUBMITTED,
    "application submitted": VisaStatus.APPLICATION_SUBMITTED,
    "appointment booked": VisaStatus.APPOINTMENT_BOOKED,
    "biometrics done": VisaStatus.BIOMETRICS_DONE,
    "in process": VisaStatus.IN_PROCESS,
    "processing": VisaStatus.IN_PROCESS,
    "approved": VisaStatus.APPROVED,
    "issued": VisaStatus.APPROVED,
    "granted": VisaStatus.APPROVED,
    "rejected": VisaStatus.REJECTED,
    "refused": VisaStatus.REJECTED,
    "withdrawn": VisaStatus.WITHDRAWN,
}


async def handle_vfs_read_status(ctx: HandlerContext) -> dict[str, Any]:
    """Read the portal status for ``application_ref``.

    Inputs:
      * ``application_ref`` (str)
      * ``destination_country`` (CountryCode, optional)

    Output: ``{"status": "<VisaStatus value>", "raw_status": "<text>"}``.
    """
    country = ctx.job.inputs.get("destination_country")
    selectors = _resolve(country)
    ref = str(ctx.job.inputs["application_ref"])

    await _ensure_logged_in(ctx, selectors)
    await steps.goto(ctx.page, f"{selectors['status_url']}?ref={ref}")
    raw = await steps.extract_text(ctx.page, selectors["status_text"])
    canonical = _STATUS_MAP.get(raw.strip().lower(), VisaStatus.IN_PROCESS)

    return {
        "application_ref": ref,
        "status": canonical.value,
        "raw_status": raw,
    }


__all__ = [
    "SELECTOR_OVERRIDES",
    "handle_vfs_book_appointment",
    "handle_vfs_checklist_prepare",
    "handle_vfs_fill_form",
    "handle_vfs_read_status",
    "handle_vfs_upload_document",
]
