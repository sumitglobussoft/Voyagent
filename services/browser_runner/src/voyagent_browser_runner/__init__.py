"""Voyagent browser-runner — Playwright worker service.

A standalone async worker that executes browser-automation jobs submitted
by portal-based drivers (VFS Global, BLS, embassy portals, airline
extranets). Jobs flow through a :class:`JobQueue` (Redis in production,
in-memory in tests), get routed by :class:`JobKind` to a handler in
``handlers/``, and return a :class:`JobResult`.

Drivers never import Playwright directly — they use
:class:`BrowserRunnerClient` from ``client.py``.
"""

from __future__ import annotations

from .artifacts import ArtifactSink, InMemoryArtifactSink, S3ArtifactSink
from .browser_pool import BrowserPool
from .client import BrowserRunnerClient
from .job import Job, JobKind, JobResult, JobStatus
from .queue import InMemoryJobQueue, JobQueue, RedisJobQueue, build_queue
from .settings import BrowserRunnerSettings
from .worker import Worker, run_forever

__all__ = [
    "ArtifactSink",
    "BrowserPool",
    "BrowserRunnerClient",
    "BrowserRunnerSettings",
    "InMemoryArtifactSink",
    "InMemoryJobQueue",
    "Job",
    "JobKind",
    "JobQueue",
    "JobResult",
    "JobStatus",
    "RedisJobQueue",
    "S3ArtifactSink",
    "Worker",
    "build_queue",
    "run_forever",
]
