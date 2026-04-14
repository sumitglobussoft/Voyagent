"""Tests for the browser-runner job queue.

We exercise both :class:`InMemoryJobQueue` directly and
:class:`RedisJobQueue` with an in-process fake Redis client (no live
Redis required). Coverage goals:

  * Enqueue/dequeue happy path.
  * FIFO ordering across many jobs.
  * A result round-trips through ``put_result`` → ``wait_for_result``.
  * Multiple workers each dequeue exactly one job (no double-take).
  * The Redis-backed queue writes/reads through the expected keys.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from voyagent_browser_runner.job import Job, JobKind, JobResult, JobStatus
from voyagent_browser_runner.queue import InMemoryJobQueue, RedisJobQueue


_TENANT_ID = "01900000-0000-7000-8000-000000000001"


def _make_job(suffix: str, *, kind: JobKind = JobKind.GENERIC_SCREENSHOT) -> Job:
    # EntityId is a shape-checked string; a hand-crafted UUIDv7 slice is fine.
    job_id = f"01900000-0000-7000-8000-0000000000{suffix:>02s}"
    return Job(
        id=job_id,
        tenant_id=_TENANT_ID,
        kind=kind,
        inputs={"marker": suffix},
        tenant_credentials_ref="vault://test/creds",
    )


# --------------------------------------------------------------------------- #
# InMemoryJobQueue                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_inmemory_enqueue_dequeue_roundtrip() -> None:
    q = InMemoryJobQueue()
    job = _make_job("01")
    await q.enqueue(job)

    got = await q.dequeue(block=True, timeout=1.0)
    assert got is not None
    assert got.id == job.id
    assert got.inputs == {"marker": "01"}
    await q.aclose()


@pytest.mark.asyncio
async def test_inmemory_fifo_order() -> None:
    q = InMemoryJobQueue()
    jobs = [_make_job(f"{i:02d}") for i in range(1, 6)]
    for j in jobs:
        await q.enqueue(j)

    dequeued: list[str] = []
    for _ in range(len(jobs)):
        item = await q.dequeue(block=True, timeout=1.0)
        assert item is not None
        dequeued.append(item.id)
    assert dequeued == [j.id for j in jobs]
    await q.aclose()


@pytest.mark.asyncio
async def test_inmemory_each_job_consumed_once_across_multiple_workers() -> None:
    """Multiple concurrent dequeuers must each see exactly one job."""
    q = InMemoryJobQueue()
    jobs = [_make_job(f"{i:02d}") for i in range(1, 4)]
    for j in jobs:
        await q.enqueue(j)

    results: list[Job] = []

    async def _worker() -> None:
        item = await q.dequeue(block=True, timeout=1.0)
        if item is not None:
            results.append(item)

    await asyncio.gather(_worker(), _worker(), _worker())

    assert sorted(r.id for r in results) == sorted(j.id for j in jobs)
    assert len({r.id for r in results}) == len(results), "job delivered twice"
    await q.aclose()


@pytest.mark.asyncio
async def test_inmemory_wait_for_result_roundtrips() -> None:
    q = InMemoryJobQueue()
    job = _make_job("01")
    await q.enqueue(job)

    result = JobResult(
        job_id=job.id,
        status=JobStatus.SUCCEEDED,
        outputs={"ok": True},
        duration_ms=42,
        completed_at=datetime.now(timezone.utc),
    )

    async def _late_put() -> None:
        await asyncio.sleep(0.01)
        await q.put_result(result)

    asyncio.create_task(_late_put())
    got = await q.wait_for_result(job.id, timeout_s=1.0)
    assert got is not None
    assert got.status is JobStatus.SUCCEEDED
    assert got.outputs == {"ok": True}
    await q.aclose()


@pytest.mark.asyncio
async def test_inmemory_dequeue_timeout_returns_none() -> None:
    q = InMemoryJobQueue()
    got = await q.dequeue(block=True, timeout=0.05)
    assert got is None
    await q.aclose()


@pytest.mark.asyncio
async def test_inmemory_closed_queue_refuses_enqueue() -> None:
    q = InMemoryJobQueue()
    await q.aclose()
    with pytest.raises(RuntimeError):
        await q.enqueue(_make_job("01"))


# --------------------------------------------------------------------------- #
# RedisJobQueue with a fake client                                            #
# --------------------------------------------------------------------------- #


class _FakeRedisAsync:
    """In-process fake for ``redis.asyncio.Redis`` — just the bits we use."""

    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._strings: dict[str, tuple[str, float | None]] = {}

    async def rpush(self, key: str, value: str) -> int:
        self._lists.setdefault(key, []).append(value)
        return len(self._lists[key])

    async def lpop(self, key: str) -> str | None:
        lst = self._lists.get(key)
        if not lst:
            return None
        return lst.pop(0)

    async def blpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:
        # Synchronous "block": immediately return whatever is there.
        value = await self.lpop(key)
        if value is None:
            return None
        return (key, value)

    async def set(
        self, key: str, value: str, *, ex: int | None = None
    ) -> None:
        self._strings[key] = (value, float(ex) if ex else None)

    async def get(self, key: str) -> str | None:
        pair = self._strings.get(key)
        if pair is None:
            return None
        return pair[0]

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_redis_queue_uses_expected_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify RPUSH/BLPOP and result SET use the queue_name + :result:<id>
    key layout the production design promises."""
    fake = _FakeRedisAsync()

    import redis.asyncio as redis_async  # type: ignore[import-not-found]

    monkeypatch.setattr(
        redis_async.Redis, "from_url", classmethod(lambda cls, url, **kw: fake)
    )

    q = RedisJobQueue(
        redis_url="redis://fake:6379/1",
        queue_name="voyagent:browser_jobs",
        result_ttl_seconds=3600,
    )
    job = _make_job("01")
    await q.enqueue(job)

    # Payload landed on the expected list key.
    assert "voyagent:browser_jobs" in fake._lists
    payload = fake._lists["voyagent:browser_jobs"][0]
    decoded = json.loads(payload)
    assert decoded["id"] == job.id
    assert decoded["kind"] == "generic.screenshot"

    # Dequeue round-trips.
    got = await q.dequeue(block=False)
    assert got is not None and got.id == job.id

    # put_result stores under queue_name:result:<id>.
    result = JobResult(job_id=job.id, status=JobStatus.SUCCEEDED, duration_ms=5)
    await q.put_result(result)
    expected_key = f"voyagent:browser_jobs:result:{job.id}"
    assert expected_key in fake._strings

    fetched = await q.wait_for_result(job.id, timeout_s=1.0)
    assert fetched is not None and fetched.status is JobStatus.SUCCEEDED
    await q.aclose()


@pytest.mark.asyncio
async def test_redis_queue_dequeue_empty_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedisAsync()
    import redis.asyncio as redis_async  # type: ignore[import-not-found]

    monkeypatch.setattr(
        redis_async.Redis, "from_url", classmethod(lambda cls, url, **kw: fake)
    )
    q = RedisJobQueue(
        redis_url="redis://fake:6379/1",
        queue_name="empty_q",
        result_ttl_seconds=60,
    )
    assert await q.dequeue(block=False) is None
    # blocking variant also yields None when the fake has nothing.
    assert await q.dequeue(block=True, timeout=0) is None
    await q.aclose()
