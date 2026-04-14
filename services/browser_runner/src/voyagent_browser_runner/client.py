"""Thin client drivers import to enqueue jobs and await their results.

Drivers never touch Redis, Playwright, or the handler registry directly —
they compose work into :class:`Job` objects and hand them to
:class:`BrowserRunnerClient`, which returns the matching
:class:`JobResult` when it settles.

The client is intentionally transport-agnostic: pass a
:class:`RedisJobQueue` in production, an :class:`InMemoryJobQueue` in
tests.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from schemas.canonical import EntityId

from .job import Job, JobKind, JobResult, JobStatus
from .queue import JobQueue

logger = logging.getLogger(__name__)


def _new_job_id() -> EntityId:
    """Mint a UUIDv7-shaped id. Matches the canonical EntityId pattern."""
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


class BrowserRunnerClient:
    """Driver-facing SDK over a :class:`JobQueue`."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    async def submit(
        self,
        kind: JobKind,
        inputs: dict[str, Any],
        *,
        tenant_id: EntityId,
        tenant_credentials_ref: str,
        timeout_s: float = 180.0,
        deadline_at: datetime | None = None,
    ) -> JobResult:
        """Enqueue a job and await its :class:`JobResult`.

        Returns a :class:`JobResult` in FAILED state with a
        ``client_timeout`` error when the worker does not settle the
        job before ``timeout_s`` — the caller's driver then maps this
        to ``UpstreamTimeoutError``.
        """
        job = Job(
            id=_new_job_id(),
            tenant_id=tenant_id,
            kind=kind,
            inputs=inputs,
            tenant_credentials_ref=tenant_credentials_ref,
            created_at=datetime.now(timezone.utc),
            deadline_at=deadline_at
            or (datetime.now(timezone.utc) + timedelta(seconds=timeout_s)),
        )
        await self._queue.enqueue(job)
        logger.info(
            "browser_runner_client.submitted",
            extra={
                "job_id": job.id,
                "kind": str(kind),
                "tenant_id": tenant_id,
                "timeout_s": timeout_s,
            },
        )
        result = await self._queue.wait_for_result(job.id, timeout_s=timeout_s)
        if result is None:
            return JobResult(
                job_id=job.id,
                status=JobStatus.FAILED,
                error="client_timeout",
                duration_ms=int(timeout_s * 1000),
                completed_at=datetime.now(timezone.utc),
            )
        return result

    # Alias spelled out — keeps the signature uncluttered at call sites.
    submit_and_await = submit


__all__ = ["BrowserRunnerClient"]
