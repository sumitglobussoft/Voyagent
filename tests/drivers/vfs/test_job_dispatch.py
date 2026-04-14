"""Tests that pin down the job shape the VFS driver sends to the runner.

These bypass the worker loop entirely and plug a capture-only fake
:class:`JobQueue` into :class:`BrowserRunnerClient`. We assert on the
exact :class:`Job` the client tried to enqueue: ``kind``, ``inputs``
JSON, credentials reference, timeout deadline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from drivers.vfs import VFSConfig, VFSDriver
from schemas.canonical import Passenger, PassengerType, Period, VisaStatus
from voyagent_browser_runner import (
    BrowserRunnerClient,
    Job,
    JobKind,
    JobResult,
    JobStatus,
)


def _uuid7() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


class _CaptureQueue:
    """A fake :class:`JobQueue` that stores the enqueued job and
    returns a stub :class:`JobResult` without running any handler.

    The driver tests only need to observe the shape of the job it
    dispatched — they don't need to simulate the full worker loop.
    """

    def __init__(self, result_outputs: dict[str, Any] | None = None) -> None:
        self.last_job: Job | None = None
        self._result_outputs = result_outputs or {}

    async def enqueue(self, job: Job) -> None:
        self.last_job = job

    async def wait_for_result(self, job_id: str, timeout_s: float) -> JobResult:
        return JobResult(
            job_id=job_id,
            status=JobStatus.SUCCEEDED,
            outputs=self._result_outputs,
            completed_at=datetime.now(timezone.utc),
        )

    # Unused by the client, but part of the Protocol surface.
    async def dequeue(self, *, block: bool = True, timeout: float = 5.0):  # pragma: no cover
        return None

    async def put_result(self, result: JobResult) -> None:  # pragma: no cover
        return None

    async def aclose(self) -> None:  # pragma: no cover
        return None


def _config() -> VFSConfig:
    return VFSConfig(
        destination_country="GB",
        credentials_ref="secrets://vfs/tenant-42",
        job_timeout_seconds=120.0,
    )


def _make_passenger() -> Passenger:
    now = datetime.now(timezone.utc)
    return Passenger(
        id=_uuid7(),
        tenant_id=_uuid7(),
        type=PassengerType.ADULT,
        given_name="Jane",
        family_name="Doe",
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# prepare_checklist                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_prepare_checklist_dispatches_vfs_checklist_prepare_job() -> None:
    queue = _CaptureQueue(result_outputs={"items": []})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config(), tenant_id=_uuid7())
    passenger = _make_passenger()

    await driver.prepare_checklist("GB", "tourist", passenger)

    assert queue.last_job is not None
    assert queue.last_job.kind == JobKind.VFS_CHECKLIST_PREPARE


@pytest.mark.asyncio
async def test_prepare_checklist_inputs_contain_destination_category_and_passenger_id() -> None:
    queue = _CaptureQueue(result_outputs={"items": []})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())
    passenger = _make_passenger()

    await driver.prepare_checklist("GB", "tourist", passenger)

    assert queue.last_job is not None
    inputs = queue.last_job.inputs
    assert inputs["destination_country"] == "GB"
    assert inputs["visa_category"] == "tourist"
    assert inputs["passenger_id"] == passenger.id


# --------------------------------------------------------------------------- #
# fill_form                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fill_form_dispatches_vfs_fill_form_job() -> None:
    queue = _CaptureQueue(result_outputs={})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())

    visa_file_id = _uuid7()
    field_values = {"#given_name": "Jane", "#surname": "Doe"}

    await driver.fill_form(visa_file_id, field_values)

    assert queue.last_job is not None
    assert queue.last_job.kind == JobKind.VFS_FILL_FORM
    assert queue.last_job.inputs["visa_file_id"] == visa_file_id
    assert queue.last_job.inputs["field_values"] == field_values
    assert queue.last_job.inputs["destination_country"] == "GB"


# --------------------------------------------------------------------------- #
# upload_document                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_upload_document_dispatches_vfs_upload_document_job() -> None:
    queue = _CaptureQueue(result_outputs={})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())
    visa_file_id = _uuid7()
    document_id = _uuid7()

    await driver.upload_document(visa_file_id, document_id)

    assert queue.last_job is not None
    assert queue.last_job.kind == JobKind.VFS_UPLOAD_DOCUMENT
    assert queue.last_job.inputs["visa_file_id"] == visa_file_id
    assert queue.last_job.inputs["document_id"] == document_id
    assert queue.last_job.inputs["destination_country"] == "GB"


# --------------------------------------------------------------------------- #
# book_appointment                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_book_appointment_serialises_window_as_iso_strings() -> None:
    queue = _CaptureQueue(result_outputs={"appointment_at": "2026-05-12T09:00:00+00:00"})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())

    window = Period(
        start=datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 14, 17, 0, tzinfo=timezone.utc),
    )
    await driver.book_appointment(_uuid7(), window)

    assert queue.last_job is not None
    assert queue.last_job.kind == JobKind.VFS_BOOK_APPOINTMENT
    pw = queue.last_job.inputs["preferred_window"]
    assert pw["start"] == "2026-05-11T09:00:00+00:00"
    assert pw["end"] == "2026-05-14T17:00:00+00:00"


@pytest.mark.asyncio
async def test_book_appointment_open_ended_window_has_null_end() -> None:
    queue = _CaptureQueue(result_outputs={"appointment_at": "2026-05-12T09:00:00+00:00"})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())

    window = Period(
        start=datetime(2026, 5, 11, tzinfo=timezone.utc),
        end=None,
    )
    await driver.book_appointment(_uuid7(), window)

    assert queue.last_job is not None
    pw = queue.last_job.inputs["preferred_window"]
    assert pw["end"] is None


# --------------------------------------------------------------------------- #
# read_status                                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_read_status_dispatches_vfs_read_status_job() -> None:
    queue = _CaptureQueue(result_outputs={"status": VisaStatus.APPROVED.value})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())

    await driver.read_status("APP-42")

    assert queue.last_job is not None
    assert queue.last_job.kind == JobKind.VFS_READ_STATUS
    assert queue.last_job.inputs["application_ref"] == "APP-42"
    assert queue.last_job.inputs["destination_country"] == "GB"


# --------------------------------------------------------------------------- #
# Credentials + deadline plumbing                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_driver_passes_tenant_credentials_ref_to_every_job() -> None:
    queue = _CaptureQueue(result_outputs={"items": []})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())

    await driver.prepare_checklist("GB", "tourist", _make_passenger())

    assert queue.last_job is not None
    assert queue.last_job.tenant_credentials_ref == "secrets://vfs/tenant-42"


@pytest.mark.asyncio
async def test_driver_stamps_job_deadline_within_config_timeout() -> None:
    queue = _CaptureQueue(result_outputs={"items": []})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config())

    before = datetime.now(timezone.utc)
    await driver.prepare_checklist("GB", "tourist", _make_passenger())
    after = datetime.now(timezone.utc)

    assert queue.last_job is not None
    assert queue.last_job.deadline_at is not None
    # Deadline is created_at + timeout. Config has 120s timeout.
    expected_min = before + timedelta(seconds=119)
    expected_max = after + timedelta(seconds=121)
    assert expected_min <= queue.last_job.deadline_at <= expected_max


@pytest.mark.asyncio
async def test_driver_stamps_tenant_id_on_every_job() -> None:
    tenant = _uuid7()
    queue = _CaptureQueue(result_outputs={"items": []})
    client = BrowserRunnerClient(queue)
    driver = VFSDriver(client, _config(), tenant_id=tenant)

    await driver.prepare_checklist("GB", "tourist", _make_passenger())

    assert queue.last_job is not None
    assert queue.last_job.tenant_id == tenant
