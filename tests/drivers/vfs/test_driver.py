"""VFS driver round-trip tests.

Every test wires a ``VFSDriver`` to a ``BrowserRunnerClient`` over an
``InMemoryJobQueue`` and a stub handler that short-circuits the VFS
handler chain. We do not exercise real Playwright here — the
handler-level contract is pinned in
``tests/services/browser_runner/test_vfs_handlers.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import pytest

from drivers.vfs import VFSConfig, VFSDriver
from drivers._contracts.errors import (
    AuthenticationError,
    ConflictError,
    PermanentError,
    UpstreamTimeoutError,
)
from schemas.canonical import Passenger, PassengerType, Period, VisaStatus
from voyagent_browser_runner import (
    BrowserRunnerClient,
    InMemoryArtifactSink,
    InMemoryJobQueue,
    JobKind,
    JobResult,
    JobStatus,
    Worker,
    BrowserRunnerSettings,
)
from voyagent_browser_runner.handlers import HandlerContext, _REGISTRY


def _uuid7() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


class _StubPool:
    """Hands out a minimal page — the stub handlers don't touch it."""

    def __init__(self) -> None:
        self.page = object()

    async def start(self) -> None:  # pragma: no cover - trivial
        return None

    def acquire(self, _tenant, _namespace):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            yield self.page

        return _cm()

    async def aclose(self) -> None:  # pragma: no cover - trivial
        return None


async def _drive(
    queue: InMemoryJobQueue,
    handler_overrides: dict[JobKind, Callable[[HandlerContext], Awaitable[dict[str, Any]]]],
) -> asyncio.Task:
    """Start a worker task bound to ``queue`` with stub handlers."""
    # Patch handler registry for the duration.
    original = {k: _REGISTRY.get(k) for k in handler_overrides}
    for k, v in handler_overrides.items():
        _REGISTRY[k] = v

    settings = BrowserRunnerSettings(
        redis_url="redis://unused.invalid/1",
        queue_name="test",
        result_ttl_seconds=60,
        max_concurrency=1,
        artifact_bucket="b",
        artifact_endpoint=None,
        retry_limit=0,
        job_timeout_seconds=5,
    )
    worker = Worker(
        queue=queue,
        browser_pool=_StubPool(),  # type: ignore[arg-type]
        artifacts=InMemoryArtifactSink(),
        settings=settings,
    )

    async def run() -> None:
        try:
            await worker.run_forever()
        finally:
            for k, v in original.items():
                if v is None:
                    _REGISTRY.pop(k, None)
                else:
                    _REGISTRY[k] = v

    task = asyncio.create_task(run())
    # Patch the pool into the worker — start() is a no-op here.
    return task


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


@pytest.fixture
def config() -> VFSConfig:
    return VFSConfig(
        destination_country="GB",
        username=None,
        password=None,
        credentials_ref="secrets://vfs/test",
        job_timeout_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_prepare_checklist_roundtrip(config: VFSConfig) -> None:
    queue = InMemoryJobQueue()

    async def stub(ctx: HandlerContext) -> dict[str, Any]:
        assert ctx.job.kind == JobKind.VFS_CHECKLIST_PREPARE
        return {
            "items": [
                {
                    "label": {"default": "Passport"},
                    "required": True,
                    "collected": False,
                    "document_id": None,
                    "notes": None,
                },
                {
                    "label": {"default": "Photo"},
                    "required": False,
                    "collected": False,
                    "document_id": None,
                    "notes": None,
                },
            ]
        }

    task = await _drive(queue, {JobKind.VFS_CHECKLIST_PREPARE: stub})
    try:
        client = BrowserRunnerClient(queue)
        driver = VFSDriver(client, config)
        items = await driver.prepare_checklist("GB", "tourist", _make_passenger())
        assert len(items) == 2
        assert items[0].label.default == "Passport"
        assert items[1].required is False
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_fill_form_success(config: VFSConfig) -> None:
    queue = InMemoryJobQueue()

    async def stub(ctx: HandlerContext) -> dict[str, Any]:
        return {
            "visa_file_id": ctx.job.inputs["visa_file_id"],
            "application_ref": "APP-1",
        }

    task = await _drive(queue, {JobKind.VFS_FILL_FORM: stub})
    try:
        client = BrowserRunnerClient(queue)
        driver = VFSDriver(client, config)
        # Returns None on success
        await driver.fill_form(_uuid7(), {"#given_name": "Jane"})
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_book_appointment_returns_datetime(config: VFSConfig) -> None:
    queue = InMemoryJobQueue()

    async def stub(_ctx: HandlerContext) -> dict[str, Any]:
        return {"appointment_at": "2026-05-12T09:00:00+00:00"}

    task = await _drive(queue, {JobKind.VFS_BOOK_APPOINTMENT: stub})
    try:
        client = BrowserRunnerClient(queue)
        driver = VFSDriver(client, config)
        window = Period(
            start=datetime(2026, 5, 11, tzinfo=timezone.utc),
            end=datetime(2026, 5, 14, tzinfo=timezone.utc),
        )
        when = await driver.book_appointment(_uuid7(), window)
        assert when == datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_read_status_maps_to_visa_status(config: VFSConfig) -> None:
    queue = InMemoryJobQueue()

    async def stub(_ctx: HandlerContext) -> dict[str, Any]:
        return {"application_ref": "APP-1", "status": "approved", "raw_status": "Approved"}

    task = await _drive(queue, {JobKind.VFS_READ_STATUS: stub})
    try:
        client = BrowserRunnerClient(queue)
        driver = VFSDriver(client, config)
        status = await driver.read_status("APP-1")
        assert status == VisaStatus.APPROVED
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_handler_failure_maps_to_driver_error(config: VFSConfig) -> None:
    queue = InMemoryJobQueue()

    async def stub(_ctx: HandlerContext) -> dict[str, Any]:
        raise RuntimeError("login failed — bad password")

    task = await _drive(queue, {JobKind.VFS_READ_STATUS: stub})
    try:
        client = BrowserRunnerClient(queue)
        driver = VFSDriver(client, config)
        with pytest.raises(AuthenticationError):
            await driver.read_status("APP-1")
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def test_manifest_shape(config: VFSConfig) -> None:
    queue = InMemoryJobQueue()
    driver = VFSDriver(BrowserRunnerClient(queue), config)
    manifest = driver.manifest()
    assert manifest.driver == "vfs"
    assert "VisaPortalDriver" in manifest.implements
    for key in (
        "prepare_checklist",
        "fill_form",
        "upload_document",
        "book_appointment",
        "read_status",
    ):
        assert manifest.capabilities[key] == "partial"
    assert "browser" in manifest.transport
    assert set(manifest.requires) >= {"browser_runner", "tenant_credentials"}
