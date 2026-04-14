"""Queue roundtrip tests.

``RedisJobQueue`` tests are skipped unless ``VOYAGENT_BROWSER_TEST_REDIS_URL``
is exported — CI isn't guaranteed to have a reachable Redis.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import pytest

from voyagent_browser_runner import (
    InMemoryJobQueue,
    Job,
    JobKind,
    JobResult,
    JobStatus,
    RedisJobQueue,
)


@pytest.mark.asyncio
async def test_in_memory_queue_roundtrip(tenant_id: str, job_id: str) -> None:
    q = InMemoryJobQueue()
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        kind=JobKind.VFS_READ_STATUS,
        inputs={"application_ref": "EX-1"},
        tenant_credentials_ref="ref",
        created_at=datetime.now(timezone.utc),
    )
    await q.enqueue(job)
    dequeued = await q.dequeue(timeout=1.0)
    assert dequeued is not None
    assert dequeued.id == job.id

    result = JobResult(job_id=job.id, status=JobStatus.SUCCEEDED, outputs={"ok": True})
    await q.put_result(result)
    fetched = await q.wait_for_result(job.id, timeout_s=1.0)
    assert fetched is not None
    assert fetched.status == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_in_memory_dequeue_timeout() -> None:
    q = InMemoryJobQueue()
    result = await q.dequeue(timeout=0.05)
    assert result is None


@pytest.mark.asyncio
async def test_in_memory_wait_for_result_timeout(job_id: str) -> None:
    q = InMemoryJobQueue()
    result = await q.wait_for_result(job_id, timeout_s=0.05)
    assert result is None


@pytest.mark.asyncio
async def test_in_memory_wait_for_result_awaits(tenant_id: str, job_id: str) -> None:
    """Late-arriving result wakes a pending waiter."""
    q = InMemoryJobQueue()

    async def put_late() -> None:
        await asyncio.sleep(0.05)
        await q.put_result(
            JobResult(job_id=job_id, status=JobStatus.SUCCEEDED, outputs={"n": 1})
        )

    producer = asyncio.create_task(put_late())
    result = await q.wait_for_result(job_id, timeout_s=1.0)
    await producer
    assert result is not None
    assert result.outputs == {"n": 1}


@pytest.mark.skipif(
    not os.environ.get("VOYAGENT_BROWSER_TEST_REDIS_URL"),
    reason="Redis not available; set VOYAGENT_BROWSER_TEST_REDIS_URL to run.",
)
@pytest.mark.asyncio
async def test_redis_queue_roundtrip(tenant_id: str, job_id: str) -> None:
    url = os.environ["VOYAGENT_BROWSER_TEST_REDIS_URL"]
    q = RedisJobQueue(
        redis_url=url,
        queue_name="voyagent:test:roundtrip",
        result_ttl_seconds=30,
    )
    try:
        job = Job(
            id=job_id,
            tenant_id=tenant_id,
            kind=JobKind.GENERIC_SCREENSHOT,
            inputs={"url": "https://example.com"},
            tenant_credentials_ref="ref",
        )
        await q.enqueue(job)
        fetched = await q.dequeue(timeout=2.0)
        assert fetched is not None
        assert fetched.id == job.id
        await q.put_result(
            JobResult(job_id=job.id, status=JobStatus.SUCCEEDED, outputs={})
        )
        settled = await q.wait_for_result(job.id, timeout_s=2.0)
        assert settled is not None
    finally:
        await q.aclose()
