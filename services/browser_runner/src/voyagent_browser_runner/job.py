"""Job + JobResult models exchanged between drivers and the worker.

Kept deliberately thin: jobs describe *what to do*, not *how*. The handler
table in :mod:`voyagent_browser_runner.handlers` owns the "how" and can be
extended per portal without widening the job schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.canonical import EntityId


def _strict() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class JobKind(StrEnum):
    """Routable job kinds. Prefixed by portal namespace.

    Adding a new portal means:
      1. appending a ``<namespace>.<op>`` value here,
      2. writing a handler in ``handlers/<namespace>.py``,
      3. registering it in ``handlers/__init__.py``.
    """

    VFS_CHECKLIST_PREPARE = "vfs.checklist_prepare"
    VFS_FILL_FORM = "vfs.fill_form"
    VFS_UPLOAD_DOCUMENT = "vfs.upload_document"
    VFS_BOOK_APPOINTMENT = "vfs.book_appointment"
    VFS_READ_STATUS = "vfs.read_status"
    GENERIC_SCREENSHOT = "generic.screenshot"
    GENERIC_GOTO_AND_EXTRACT = "generic.goto_and_extract"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """A unit of browser work to be executed by the runner.

    ``tenant_credentials_ref`` is an opaque handle — typically a secrets-manager
    key. The worker resolves it to real credentials inside the handler; the
    driver-side process never transports the actual username/password.
    """

    model_config = _strict()

    id: EntityId
    tenant_id: EntityId
    kind: JobKind
    inputs: dict[str, Any] = Field(default_factory=dict)
    tenant_credentials_ref: str = Field(
        description="Opaque reference to tenant credentials. Resolved worker-side, never logged."
    )
    attempts: int = 0
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    deadline_at: datetime | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return True when ``deadline_at`` has passed."""
        if self.deadline_at is None:
            return False
        current = now or datetime.now(timezone.utc)
        return current >= self.deadline_at


class JobResult(BaseModel):
    """Outcome of a :class:`Job`. Artifacts are URIs into the artifact sink,
    not inline blobs — results travel through Redis and must stay small."""

    model_config = _strict()

    job_id: EntityId
    status: JobStatus
    outputs: dict[str, Any] | None = None
    error: str | None = None
    artifact_uris: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    completed_at: datetime | None = None


__all__ = ["Job", "JobKind", "JobResult", "JobStatus"]
