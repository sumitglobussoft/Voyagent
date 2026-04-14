"""VFS handler tests against the FakePage.

Selectors in the handlers are the documented placeholders. These tests
assert the exact placeholder strings so that when a tenant ships a real
selector pack, both sides update in lock-step.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from voyagent_browser_runner import InMemoryArtifactSink, Job, JobKind
from voyagent_browser_runner.handlers import Credentials, HandlerContext
from voyagent_browser_runner.handlers.vfs_in import (
    _DEFAULT_SELECTORS,
    handle_vfs_book_appointment,
    handle_vfs_checklist_prepare,
    handle_vfs_fill_form,
    handle_vfs_read_status,
    handle_vfs_upload_document,
)


def _ctx(page, artifacts, tenant_id: str, job_id: str, *, kind, inputs):
    creds = Credentials(username="dev@example.com", password="hunter2", extra={})
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        kind=kind,
        inputs=inputs,
        tenant_credentials_ref="ref",
    )
    return HandlerContext(
        job=job,
        page=page,
        artifacts=artifacts,
        credentials=creds,
        tenant_id=tenant_id,
    )


@pytest.mark.asyncio
async def test_checklist_prepare(
    fake_page, in_memory_artifacts: InMemoryArtifactSink, tenant_id, job_id
) -> None:
    # Program the FakePage with two "checklist rows".
    from .conftest import FakeElement

    rows = [
        FakeElement(
            children={
                ".label": FakeElement(text="Passport"),
                ".required": FakeElement(text="true"),
            }
        ),
        FakeElement(
            children={
                ".label": FakeElement(text="Photo"),
                ".required": FakeElement(text="false"),
            }
        ),
    ]
    fake_page.selector_lists[_DEFAULT_SELECTORS["checklist_item"]] = rows

    ctx = _ctx(
        fake_page,
        in_memory_artifacts,
        tenant_id,
        job_id,
        kind=JobKind.VFS_CHECKLIST_PREPARE,
        inputs={
            "destination_country": "GB",
            "visa_category": "tourist",
            "passenger_id": None,
        },
    )
    out = await handle_vfs_checklist_prepare(ctx)
    assert len(out["items"]) == 2
    assert out["items"][0]["label"] == {"default": "Passport"}
    assert out["items"][0]["required"] is True
    assert out["items"][1]["required"] is False
    # Login page was visited.
    assert _DEFAULT_SELECTORS["login_url"] in fake_page.url_history
    # Password was filled masked (we can't introspect the log, but the
    # fill must have happened against the password selector).
    assert any(
        sel == _DEFAULT_SELECTORS["login_password"] for sel, _ in fake_page.fills
    )


@pytest.mark.asyncio
async def test_fill_form(
    fake_page, in_memory_artifacts, tenant_id, job_id
) -> None:
    fake_page.texts[_DEFAULT_SELECTORS["form_confirmation_ref"]] = "APP-12345"
    ctx = _ctx(
        fake_page,
        in_memory_artifacts,
        tenant_id,
        job_id,
        kind=JobKind.VFS_FILL_FORM,
        inputs={
            "visa_file_id": tenant_id,  # reused UUID shape
            "field_values": {
                "#given_name": "Jane",
                "#family_name": "Doe",
                "__mask__": ["#passport_number"],
                "#passport_number": "A1234567",
            },
        },
    )
    out = await handle_vfs_fill_form(ctx)
    assert out["application_ref"] == "APP-12345"
    # All three real fields were filled.
    filled_selectors = {sel for sel, _ in fake_page.fills}
    assert {"#given_name", "#family_name", "#passport_number"} <= filled_selectors


@pytest.mark.asyncio
async def test_upload_document(
    fake_page, in_memory_artifacts, tenant_id, job_id, tmp_path
) -> None:
    f = tmp_path / "passport.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    ctx = _ctx(
        fake_page,
        in_memory_artifacts,
        tenant_id,
        job_id,
        kind=JobKind.VFS_UPLOAD_DOCUMENT,
        inputs={
            "visa_file_id": tenant_id,
            "document_id": tenant_id,
            "local_path": str(f),
        },
    )
    out = await handle_vfs_upload_document(ctx)
    assert out["uploaded"] is True
    assert fake_page.uploads == [(_DEFAULT_SELECTORS["upload_selector"], str(f))]


@pytest.mark.asyncio
async def test_book_appointment_picks_earliest_in_window(
    fake_page, in_memory_artifacts, tenant_id, job_id
) -> None:
    from .conftest import FakeElement

    slots = [
        FakeElement(
            children={
                "[data-time]": FakeElement(attributes={"data-time": "2026-05-10T08:00:00+00:00"}),
            }
        ),
        FakeElement(
            children={
                "[data-time]": FakeElement(attributes={"data-time": "2026-05-12T09:00:00+00:00"}),
            }
        ),
        FakeElement(
            children={
                "[data-time]": FakeElement(attributes={"data-time": "2026-05-15T09:00:00+00:00"}),
            }
        ),
    ]
    fake_page.selector_lists[_DEFAULT_SELECTORS["appointment_slot"]] = slots

    ctx = _ctx(
        fake_page,
        in_memory_artifacts,
        tenant_id,
        job_id,
        kind=JobKind.VFS_BOOK_APPOINTMENT,
        inputs={
            "visa_file_id": tenant_id,
            "preferred_window": {
                "start": "2026-05-11T00:00:00+00:00",
                "end": "2026-05-14T00:00:00+00:00",
            },
        },
    )
    out = await handle_vfs_book_appointment(ctx)
    assert out["appointment_at"].startswith("2026-05-12T09:00")
    # The middle slot was clicked, then the confirm button.
    assert slots[1].click_count == 1
    assert _DEFAULT_SELECTORS["appointment_confirm"] in fake_page.clicks


@pytest.mark.asyncio
async def test_read_status_maps_canonical(
    fake_page, in_memory_artifacts, tenant_id, job_id
) -> None:
    fake_page.texts[_DEFAULT_SELECTORS["status_text"]] = "Approved"
    ctx = _ctx(
        fake_page,
        in_memory_artifacts,
        tenant_id,
        job_id,
        kind=JobKind.VFS_READ_STATUS,
        inputs={"application_ref": "APP-12345"},
    )
    out = await handle_vfs_read_status(ctx)
    assert out["status"] == "approved"
    assert out["raw_status"] == "Approved"
    # Status URL carried the ref.
    assert any("ref=APP-12345" in u for u in fake_page.url_history)


@pytest.mark.asyncio
async def test_read_status_unknown_maps_to_in_process(
    fake_page, in_memory_artifacts, tenant_id, job_id
) -> None:
    fake_page.texts[_DEFAULT_SELECTORS["status_text"]] = "Pending adjudication"
    ctx = _ctx(
        fake_page,
        in_memory_artifacts,
        tenant_id,
        job_id,
        kind=JobKind.VFS_READ_STATUS,
        inputs={"application_ref": "APP-99"},
    )
    out = await handle_vfs_read_status(ctx)
    assert out["status"] == "in_process"


def test_default_selectors_are_placeholders() -> None:
    """Guard: every URL value must remain an .invalid placeholder.

    A tenant replacing placeholders with real selectors flips this
    test red; they update the expectation at the same time they update
    the handler, keeping drift visible.
    """
    url_keys = ("login_url", "checklist_url", "form_url", "appointment_url", "status_url")
    for key in url_keys:
        assert _DEFAULT_SELECTORS[key].endswith(".invalid") or "example.invalid" in _DEFAULT_SELECTORS[key], (
            f"_DEFAULT_SELECTORS[{key!r}] is no longer a placeholder: "
            f"{_DEFAULT_SELECTORS[key]!r}"
        )


def test_default_selectors_exact_strings() -> None:
    """Pin the exact placeholder values — tests and handlers change together."""
    assert _DEFAULT_SELECTORS["login_email"] == "#email"
    assert _DEFAULT_SELECTORS["login_password"] == "#password"
    assert _DEFAULT_SELECTORS["login_submit"] == "button[data-voyagent-login]"
    assert _DEFAULT_SELECTORS["form_submit"] == "button[data-voyagent-submit]"
    assert _DEFAULT_SELECTORS["form_confirmation_ref"] == "[data-voyagent-application-ref]"
    assert _DEFAULT_SELECTORS["upload_selector"] == "input[type=file][data-voyagent-upload]"
    assert _DEFAULT_SELECTORS["appointment_slot"] == ".slot-available"
    assert _DEFAULT_SELECTORS["appointment_confirm"] == "button[data-voyagent-confirm-slot]"
    assert _DEFAULT_SELECTORS["status_text"] == "[data-voyagent-status]"
