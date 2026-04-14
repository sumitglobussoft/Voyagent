"""Fixtures for the VFS driver suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _restore_handler_registry():
    """Restore the handler registry after every test.

    Tests patch ``_REGISTRY`` to inject stub handlers; without this the
    builtin VFS handlers would stay overridden between tests.
    """
    from voyagent_browser_runner.handlers import _REGISTRY

    snapshot = dict(_REGISTRY)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)
