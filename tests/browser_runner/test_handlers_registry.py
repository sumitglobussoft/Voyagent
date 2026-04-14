"""Tests for the handler registry in :mod:`voyagent_browser_runner.handlers`.

The registry is a module-level dict populated on import — we assert the
built-ins are wired to the right module, and that the registry surface
(``register``, ``get_handler``, ``iter_registered``) behaves sanely on
both happy and error paths.
"""

from __future__ import annotations

from typing import Any

import pytest

from voyagent_browser_runner import handlers as handlers_pkg
from voyagent_browser_runner.job import JobKind


# --------------------------------------------------------------------------- #
# Built-in registration                                                       #
# --------------------------------------------------------------------------- #


def test_every_job_kind_has_a_handler() -> None:
    for kind in JobKind:
        assert handlers_pkg.get_handler(kind) is not None


def test_vfs_in_kinds_route_to_vfs_in_module() -> None:
    """The five VFS kinds must dispatch to handlers living in ``vfs_in``."""
    from voyagent_browser_runner.handlers import vfs_in

    vfs_fns = {getattr(vfs_in, n) for n in dir(vfs_in) if callable(getattr(vfs_in, n))}

    for kind in (
        JobKind.VFS_CHECKLIST_PREPARE,
        JobKind.VFS_FILL_FORM,
        JobKind.VFS_UPLOAD_DOCUMENT,
        JobKind.VFS_BOOK_APPOINTMENT,
        JobKind.VFS_READ_STATUS,
    ):
        fn = handlers_pkg.get_handler(kind)
        assert fn in vfs_fns, f"{kind} not dispatched to vfs_in module"


def test_generic_kinds_route_to_generic_module() -> None:
    from voyagent_browser_runner.handlers import generic

    generic_fns = {
        getattr(generic, n) for n in dir(generic) if callable(getattr(generic, n))
    }
    for kind in (JobKind.GENERIC_SCREENSHOT, JobKind.GENERIC_GOTO_AND_EXTRACT):
        assert handlers_pkg.get_handler(kind) in generic_fns


# --------------------------------------------------------------------------- #
# Registry surface                                                            #
# --------------------------------------------------------------------------- #


def test_register_and_retrieve_a_custom_handler() -> None:
    """``register`` stores the last-writer-wins fn; ``get_handler`` returns it."""

    async def _replacement(ctx: Any) -> dict[str, Any]:
        return {"replaced": True}

    original = handlers_pkg.get_handler(JobKind.GENERIC_SCREENSHOT)
    try:
        handlers_pkg.register(JobKind.GENERIC_SCREENSHOT, _replacement)
        assert handlers_pkg.get_handler(JobKind.GENERIC_SCREENSHOT) is _replacement
    finally:
        # Restore so other tests aren't affected.
        handlers_pkg.register(JobKind.GENERIC_SCREENSHOT, original)


def test_unknown_kind_raises_keyerror_with_message() -> None:
    """``get_handler`` on an unknown kind must raise KeyError — the worker
    turns this into a ``no_handler`` FAILED JobResult rather than crashing."""

    class _FakeKind:
        # Not a real JobKind member; acts as a lookup key that isn't registered.
        value = "nonexistent.kind"

        def __repr__(self) -> str:
            return "_FakeKind"

    with pytest.raises(KeyError) as info:
        handlers_pkg.get_handler(_FakeKind())  # type: ignore[arg-type]
    assert "no handler registered" in str(info.value)


def test_iter_registered_lists_every_kind() -> None:
    registered = {k for k, _ in handlers_pkg.iter_registered()}
    # Every JobKind must appear in the registry enumeration.
    assert registered == set(JobKind)
