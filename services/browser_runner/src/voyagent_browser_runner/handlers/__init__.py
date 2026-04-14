"""Handler registry for the browser-runner.

Each handler is an async function taking a :class:`HandlerContext` and
returning a dict of canonical outputs. The worker looks up the handler
by :class:`JobKind` at dequeue time.

Adding a portal:

1. Create ``handlers/<portal>.py`` exposing ``async def
   handle_<kind>(ctx) -> dict``.
2. Register each handler below under its :class:`JobKind`.
3. Extend :class:`JobKind` itself if the operation is new.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from schemas.canonical import EntityId

from ..job import Job, JobKind

if TYPE_CHECKING:
    from ..artifacts import ArtifactSink

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
    """Minimal credentials bag for portal logins.

    Worker-side only. Never serialized into a ``JobResult`` or log line.
    """

    username: str
    password: str
    extra: dict[str, str]


@dataclass
class HandlerContext:
    """Everything a handler may use.

    ``credentials`` is resolved by the worker via the
    :class:`CredentialResolver` registered on the worker — handlers
    simply dereference the attribute.
    """

    job: Job
    page: Any
    artifacts: "ArtifactSink"
    credentials: Credentials | None
    tenant_id: EntityId


HandlerFn = Callable[[HandlerContext], Awaitable[dict[str, Any]]]


_REGISTRY: dict[JobKind, HandlerFn] = {}


def register(kind: JobKind, fn: HandlerFn) -> None:
    """Register ``fn`` as the handler for ``kind`` (last writer wins)."""
    _REGISTRY[kind] = fn


def get_handler(kind: JobKind) -> HandlerFn:
    """Return the registered handler for ``kind``.

    Raises :class:`KeyError` when unknown — the worker turns this into
    a FAILED :class:`JobResult` with a ``no_handler`` error.
    """
    try:
        return _REGISTRY[kind]
    except KeyError as exc:
        raise KeyError(f"no handler registered for job kind {kind!r}") from exc


def iter_registered() -> list[tuple[JobKind, HandlerFn]]:
    return list(_REGISTRY.items())


def _register_builtins() -> None:
    """Register the handlers that ship with the runner."""
    from . import generic, vfs_in

    register(JobKind.VFS_CHECKLIST_PREPARE, vfs_in.handle_vfs_checklist_prepare)
    register(JobKind.VFS_FILL_FORM, vfs_in.handle_vfs_fill_form)
    register(JobKind.VFS_UPLOAD_DOCUMENT, vfs_in.handle_vfs_upload_document)
    register(JobKind.VFS_BOOK_APPOINTMENT, vfs_in.handle_vfs_book_appointment)
    register(JobKind.VFS_READ_STATUS, vfs_in.handle_vfs_read_status)
    register(JobKind.GENERIC_SCREENSHOT, generic.handle_generic_screenshot)
    register(JobKind.GENERIC_GOTO_AND_EXTRACT, generic.handle_generic_goto_and_extract)


_register_builtins()


__all__ = [
    "Credentials",
    "HandlerContext",
    "HandlerFn",
    "get_handler",
    "iter_registered",
    "register",
]
