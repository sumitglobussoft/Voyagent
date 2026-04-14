"""Worker-loop tests.

Cover happy path, handler error + artifact capture, deadline expiry,
retry on transient exception.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from voyagent_browser_runner import (
    InMemoryArtifactSink,
    InMemoryJobQueue,
    Job,
    JobKind,
    JobStatus,
    Worker,
)
from voyagent_browser_runner.handlers import HandlerContext, register


@pytest.mark.asyncio
async def test_worker_happy_path(
    in_memory_queue: InMemoryJobQueue,
    in_memory_artifacts: InMemoryArtifactSink,
    fake_browser_pool,
    browser_settings,
    tenant_id: str,
    job_id: str,
) -> None:
    captured: dict[str, HandlerContext] = {}

    async def handler(ctx: HandlerContext) -> dict:
        captured["ctx"] = ctx
        return {"hello": "world"}

    register(JobKind.GENERIC_SCREENSHOT, handler)

    worker = Worker(
        queue=in_memory_queue,
        browser_pool=fake_browser_pool,
        artifacts=in_memory_artifacts,
        settings=browser_settings,
    )
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        kind=JobKind.GENERIC_SCREENSHOT,
        inputs={"url": "https://example.com"},
        tenant_credentials_ref="ref",
    )
    result = await worker.process_one(job)
    assert result.status == JobStatus.SUCCEEDED
    assert result.outputs == {"hello": "world"}
    assert captured["ctx"].tenant_id == tenant_id
    assert fake_browser_pool.acquisitions == [(tenant_id, "generic")]


@pytest.mark.asyncio
async def test_worker_failure_captures_artifacts(
    in_memory_queue: InMemoryJobQueue,
    in_memory_artifacts: InMemoryArtifactSink,
    fake_browser_pool,
    browser_settings,
    tenant_id: str,
    job_id: str,
) -> None:
    async def handler(_ctx: HandlerContext) -> dict:
        raise RuntimeError("boom")

    register(JobKind.GENERIC_SCREENSHOT, handler)

    worker = Worker(
        queue=in_memory_queue,
        browser_pool=fake_browser_pool,
        artifacts=in_memory_artifacts,
        settings=browser_settings,
    )
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        kind=JobKind.GENERIC_SCREENSHOT,
        inputs={"url": "https://example.com"},
        tenant_credentials_ref="ref",
    )
    result = await worker.process_one(job)
    assert result.status == JobStatus.FAILED
    assert "boom" in (result.error or "")
    # Two artifacts: screenshot + HTML snapshot
    assert len(result.artifact_uris) == 2
    # Both were persisted to the in-memory sink
    for uri in result.artifact_uris:
        assert in_memory_artifacts.get(uri) is not None


@pytest.mark.asyncio
async def test_worker_deadline_exceeded(
    in_memory_queue: InMemoryJobQueue,
    in_memory_artifacts: InMemoryArtifactSink,
    fake_browser_pool,
    browser_settings,
    tenant_id: str,
    job_id: str,
) -> None:
    worker = Worker(
        queue=in_memory_queue,
        browser_pool=fake_browser_pool,
        artifacts=in_memory_artifacts,
        settings=browser_settings,
    )
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        kind=JobKind.GENERIC_SCREENSHOT,
        inputs={"url": "https://example.com"},
        tenant_credentials_ref="ref",
        deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    result = await worker.process_one(job)
    assert result.status == JobStatus.FAILED
    assert result.error == "deadline_exceeded"
    # Pool never acquired for expired jobs.
    assert fake_browser_pool.acquisitions == []


@pytest.mark.asyncio
async def test_worker_retries_transient(
    in_memory_queue: InMemoryJobQueue,
    in_memory_artifacts: InMemoryArtifactSink,
    fake_browser_pool,
    browser_settings,
    tenant_id: str,
    job_id: str,
    monkeypatch,
) -> None:
    # Neutralise backoff so the test finishes promptly.
    async def instant_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    attempts: list[int] = []

    async def flaky_handler(ctx: HandlerContext) -> dict:
        attempts.append(ctx.job.attempts)
        if ctx.job.attempts == 0:
            raise TimeoutError("temporary network issue")
        return {"ok": True}

    register(JobKind.GENERIC_SCREENSHOT, flaky_handler)

    worker = Worker(
        queue=in_memory_queue,
        browser_pool=fake_browser_pool,
        artifacts=in_memory_artifacts,
        settings=browser_settings,
    )
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        kind=JobKind.GENERIC_SCREENSHOT,
        inputs={"url": "https://example.com"},
        tenant_credentials_ref="ref",
    )
    first = await worker.process_one(job)
    assert first.status == JobStatus.QUEUED
    # The worker re-enqueued the retry; pull it and process again.
    retry = await in_memory_queue.dequeue(timeout=0.5)
    assert retry is not None
    assert retry.attempts == 1
    second = await worker.process_one(retry)
    assert second.status == JobStatus.SUCCEEDED
    assert attempts == [0, 1]


@pytest.mark.asyncio
async def test_worker_no_handler_registered(
    in_memory_queue: InMemoryJobQueue,
    in_memory_artifacts: InMemoryArtifactSink,
    fake_browser_pool,
    browser_settings,
    tenant_id: str,
    job_id: str,
) -> None:
    from voyagent_browser_runner.handlers import _REGISTRY

    # Temporarily drop the handler to exercise the unregistered path.
    saved = _REGISTRY.pop(JobKind.GENERIC_SCREENSHOT, None)
    try:
        worker = Worker(
            queue=in_memory_queue,
            browser_pool=fake_browser_pool,
            artifacts=in_memory_artifacts,
            settings=browser_settings,
        )
        job = Job(
            id=job_id,
            tenant_id=tenant_id,
            kind=JobKind.GENERIC_SCREENSHOT,
            inputs={},
            tenant_credentials_ref="ref",
        )
        result = await worker.process_one(job)
        assert result.status == JobStatus.FAILED
        assert "no_handler" in (result.error or "")
    finally:
        if saved is not None:
            _REGISTRY[JobKind.GENERIC_SCREENSHOT] = saved
