"""Job queue abstraction.

Two implementations ship with v0:

* :class:`RedisJobQueue` — production; uses ``redis.asyncio`` with a list
  for the job queue and a hash for results. Matches the Redis deployment
  in ``infra/docker/dev.yml``.
* :class:`InMemoryJobQueue` — tests and local one-shot usage; implemented
  with :class:`asyncio.Queue` and a dict.

Both satisfy the :class:`JobQueue` Protocol. Drivers receive a queue via
:class:`BrowserRunnerClient` and never care which concrete type is in use.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from schemas.canonical import EntityId

from .job import Job, JobResult

if TYPE_CHECKING:
    from .settings import BrowserRunnerSettings

logger = logging.getLogger(__name__)


@runtime_checkable
class JobQueue(Protocol):
    """Transport for jobs and their results.

    Enqueue and dequeue operate on the pending-job list. Results go on a
    separate channel keyed by job_id, so a driver can await a result
    without consuming jobs intended for the worker pool.
    """

    async def enqueue(self, job: Job) -> None:
        ...

    async def dequeue(self, *, block: bool = True, timeout: float = 5.0) -> Job | None:
        ...

    async def put_result(self, result: JobResult) -> None:
        ...

    async def wait_for_result(
        self, job_id: EntityId, timeout_s: float
    ) -> JobResult | None:
        ...

    async def aclose(self) -> None:
        ...


# --------------------------------------------------------------------------- #
# In-memory implementation                                                    #
# --------------------------------------------------------------------------- #


class InMemoryJobQueue:
    """Asyncio-only queue for tests and co-located workers.

    Drivers and the worker loop must run in the *same* event loop for
    this implementation. Production code uses :class:`RedisJobQueue`.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._results: dict[str, JobResult] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._closed = False

    async def enqueue(self, job: Job) -> None:
        if self._closed:
            raise RuntimeError("queue is closed")
        self._events.setdefault(job.id, asyncio.Event())
        await self._queue.put(job)

    async def dequeue(self, *, block: bool = True, timeout: float = 5.0) -> Job | None:
        if self._closed:
            return None
        try:
            if block:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return self._queue.get_nowait()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    async def put_result(self, result: JobResult) -> None:
        self._results[result.job_id] = result
        event = self._events.setdefault(result.job_id, asyncio.Event())
        event.set()

    async def wait_for_result(
        self, job_id: EntityId, timeout_s: float
    ) -> JobResult | None:
        event = self._events.setdefault(job_id, asyncio.Event())
        if job_id in self._results:
            return self._results[job_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None
        return self._results.get(job_id)

    async def aclose(self) -> None:
        self._closed = True


# --------------------------------------------------------------------------- #
# Redis implementation                                                        #
# --------------------------------------------------------------------------- #


class RedisJobQueue:
    """Production queue backed by Redis lists + hashes.

    Keys:
      * ``<queue_name>``                    — the pending-jobs list (RPUSH/BLPOP).
      * ``<queue_name>:result:<job_id>``    — JSON result with TTL.
    """

    def __init__(
        self,
        *,
        redis_url: str,
        queue_name: str,
        result_ttl_seconds: int,
    ) -> None:
        # Local import — tests that never touch Redis won't require the
        # wheel to be installed.
        from redis.asyncio import Redis

        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._queue_name = queue_name
        self._result_ttl = result_ttl_seconds

    def _result_key(self, job_id: EntityId) -> str:
        return f"{self._queue_name}:result:{job_id}"

    async def enqueue(self, job: Job) -> None:
        payload = job.model_dump_json()
        await self._client.rpush(self._queue_name, payload)
        logger.info(
            "queue.enqueued",
            extra={"job_id": job.id, "kind": str(job.kind), "queue": self._queue_name},
        )

    async def dequeue(self, *, block: bool = True, timeout: float = 5.0) -> Job | None:
        if block:
            result = await self._client.blpop(self._queue_name, timeout=int(timeout))
            if result is None:
                return None
            _key, payload = result
        else:
            payload = await self._client.lpop(self._queue_name)
            if payload is None:
                return None
        return Job.model_validate_json(payload)

    async def put_result(self, result: JobResult) -> None:
        key = self._result_key(result.job_id)
        await self._client.set(
            key, result.model_dump_json(), ex=self._result_ttl
        )
        logger.info(
            "queue.result_stored",
            extra={
                "job_id": result.job_id,
                "status": str(result.status),
                "duration_ms": result.duration_ms,
            },
        )

    async def wait_for_result(
        self, job_id: EntityId, timeout_s: float
    ) -> JobResult | None:
        """Poll with bounded exponential backoff.

        Redis pub/sub would be tidier, but a simple poll keeps the
        number of moving parts low for v0 and avoids another connection
        per waiter.
        """
        deadline = time.monotonic() + timeout_s
        delay = 0.1
        key = self._result_key(job_id)
        while True:
            payload = await self._client.get(key)
            if payload is not None:
                return JobResult.model_validate_json(payload)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(delay, remaining))
            delay = min(delay * 2, 2.0)

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception:  # noqa: BLE001
            logger.warning("redis queue aclose failed", exc_info=True)


def build_queue(settings: BrowserRunnerSettings) -> JobQueue:
    """Construct a :class:`JobQueue` appropriate for ``settings``.

    Always returns a :class:`RedisJobQueue` — the in-memory queue is
    test-only and must be constructed explicitly.
    """
    return RedisJobQueue(
        redis_url=settings.redis_url,
        queue_name=settings.queue_name,
        result_ttl_seconds=settings.result_ttl_seconds,
    )


__all__ = [
    "InMemoryJobQueue",
    "JobQueue",
    "RedisJobQueue",
    "build_queue",
]
