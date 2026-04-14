"""Worker loop that drains :class:`JobQueue` and executes handlers.

The loop enforces:

* ``deadline_at`` — jobs past their deadline fail fast with
  ``deadline_exceeded`` without touching Playwright.
* ``job_timeout_seconds`` — per-job hard timeout via :mod:`asyncio`.
* ``retry_limit`` — transient failures are re-enqueued up to the
  configured count; each retry increments ``Job.attempts``.
* Failure-artifact capture — whenever a handler raises, the worker
  captures a screenshot + HTML snapshot before writing the failed
  :class:`JobResult`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .handlers import Credentials, HandlerContext, get_handler
from .job import Job, JobResult, JobStatus
from .steps import capture_failure

if TYPE_CHECKING:
    from .artifacts import ArtifactSink
    from .browser_pool import BrowserPool
    from .queue import JobQueue
    from .settings import BrowserRunnerSettings

logger = logging.getLogger(__name__)


CredentialResolver = Callable[[str], Awaitable[Credentials | None]]
"""A function mapping ``tenant_credentials_ref`` -> credentials.

Production supplies a resolver that reads from a secrets store. Tests
supply a stub that returns a canned :class:`Credentials` value.
"""


async def _null_resolver(_ref: str) -> Credentials | None:
    return None


def _namespace_for(kind: str) -> str:
    """Return the handler namespace for a job kind, e.g. ``"vfs"``.

    Used by :class:`BrowserPool` as part of the context cache key so
    cookies for one portal don't leak into another.
    """
    return kind.split(".", 1)[0] if "." in kind else kind


class Worker:
    """A single worker. One Playwright browser, N contexts via the pool."""

    def __init__(
        self,
        *,
        queue: "JobQueue",
        browser_pool: "BrowserPool",
        artifacts: "ArtifactSink",
        settings: "BrowserRunnerSettings",
        credential_resolver: CredentialResolver | None = None,
    ) -> None:
        self._queue = queue
        self._pool = browser_pool
        self._artifacts = artifacts
        self._settings = settings
        self._resolve_creds = credential_resolver or _null_resolver
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        """Ask the run loop to exit after the current job finishes."""
        self._stop.set()

    async def run_forever(self) -> None:
        """Drain the queue until :meth:`request_stop` is called."""
        await self._pool.start()
        logger.info(
            "worker.started",
            extra={
                "queue": getattr(self._settings, "queue_name", ""),
                "max_concurrency": self._settings.max_concurrency,
            },
        )
        try:
            while not self._stop.is_set():
                job = await self._queue.dequeue(block=True, timeout=5.0)
                if job is None:
                    continue
                await self.process_one(job)
        finally:
            await self._pool.aclose()

    async def process_one(self, job: Job) -> JobResult:
        """Execute ``job`` and persist its result. Always returns the result."""
        logger.info(
            "worker.job_received",
            extra={
                "job_id": job.id,
                "kind": str(job.kind),
                "tenant_id": job.tenant_id,
                "attempts": job.attempts,
            },
        )

        if job.is_expired():
            result = JobResult(
                job_id=job.id,
                status=JobStatus.FAILED,
                error="deadline_exceeded",
                completed_at=datetime.now(timezone.utc),
            )
            await self._queue.put_result(result)
            return result

        started = time.monotonic()
        namespace = _namespace_for(str(job.kind))

        try:
            handler = get_handler(job.kind)
        except KeyError as exc:
            result = JobResult(
                job_id=job.id,
                status=JobStatus.FAILED,
                error=f"no_handler: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
                completed_at=datetime.now(timezone.utc),
            )
            await self._queue.put_result(result)
            return result

        credentials = await self._resolve_creds(job.tenant_credentials_ref)

        outputs: dict[str, Any] | None = None
        failure: Exception | None = None
        artifact_uris: list[str] = []

        try:
            async with self._pool.acquire(job.tenant_id, namespace) as page:
                ctx = HandlerContext(
                    job=job,
                    page=page,
                    artifacts=self._artifacts,
                    credentials=credentials,
                    tenant_id=job.tenant_id,
                )
                try:
                    outputs = await asyncio.wait_for(
                        handler(ctx),
                        timeout=self._settings.job_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    failure = TimeoutError("job_timeout_exceeded")
                except Exception as exc:  # noqa: BLE001
                    failure = exc
                if failure is not None:
                    try:
                        artifact_uris = await capture_failure(
                            page, job.id, job.tenant_id, failure, self._artifacts
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "worker.capture_failure_failed",
                            extra={"job_id": job.id},
                            exc_info=True,
                        )
        except Exception as exc:  # noqa: BLE001 — pool acquisition itself failed
            failure = exc

        if failure is not None:
            transient = _looks_transient(failure)
            return await self._handle_failure(
                job, failure, started, transient=transient, artifact_uris=artifact_uris
            )

        result = JobResult(
            job_id=job.id,
            status=JobStatus.SUCCEEDED,
            outputs=outputs,
            duration_ms=int((time.monotonic() - started) * 1000),
            completed_at=datetime.now(timezone.utc),
        )
        await self._queue.put_result(result)
        logger.info(
            "worker.job_succeeded",
            extra={
                "job_id": job.id,
                "kind": str(job.kind),
                "duration_ms": result.duration_ms,
            },
        )
        return result

    async def _handle_failure(
        self,
        job: Job,
        exc: Exception,
        started: float,
        *,
        transient: bool,
        artifact_uris: list[str] | None = None,
    ) -> JobResult:
        """Decide retry-vs-fail and persist the result.

        ``artifact_uris`` are captured inside the pool-acquired page by
        the caller, so they are available even when pool re-acquisition
        would fail.
        """
        artifact_uris = artifact_uris or []

        if transient and job.attempts < self._settings.retry_limit:
            retry_job = job.model_copy(update={"attempts": job.attempts + 1})
            backoff = min(2 ** retry_job.attempts, 30)
            logger.info(
                "worker.job_retry_scheduled",
                extra={
                    "job_id": job.id,
                    "attempts": retry_job.attempts,
                    "backoff_s": backoff,
                    "error": type(exc).__name__,
                },
            )
            await asyncio.sleep(backoff)
            await self._queue.enqueue(retry_job)
            # Intentionally do NOT write a FAILED result yet — drivers
            # waiting on wait_for_result keep waiting until the final
            # attempt settles.
            return JobResult(
                job_id=job.id,
                status=JobStatus.QUEUED,
                error=f"transient_retry: {exc}",
                artifact_uris=artifact_uris,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        result = JobResult(
            job_id=job.id,
            status=JobStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}",
            artifact_uris=artifact_uris,
            duration_ms=int((time.monotonic() - started) * 1000),
            completed_at=datetime.now(timezone.utc),
        )
        await self._queue.put_result(result)
        logger.info(
            "worker.job_failed",
            extra={
                "job_id": job.id,
                "kind": str(job.kind),
                "error": type(exc).__name__,
                "duration_ms": result.duration_ms,
                "artifact_uris": artifact_uris,
            },
        )
        return result


def _looks_transient(exc: Exception) -> bool:
    """Heuristic: did ``exc`` look like a retryable failure?

    We bias toward retrying on TimeoutError / ConnectionError and on
    names that look like transient Playwright issues. Permanent
    failures (AttributeError, ValueError from our own code) never get
    retried.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "network", "temporar"))


async def run_forever(
    queue: "JobQueue",
    browser_pool: "BrowserPool",
    artifacts: "ArtifactSink",
    settings: "BrowserRunnerSettings",
    *,
    credential_resolver: CredentialResolver | None = None,
) -> None:
    """Convenience entry point used by ``cli.py``."""
    worker = Worker(
        queue=queue,
        browser_pool=browser_pool,
        artifacts=artifacts,
        settings=settings,
        credential_resolver=credential_resolver,
    )
    await worker.run_forever()


__all__ = ["CredentialResolver", "Worker", "run_forever"]
