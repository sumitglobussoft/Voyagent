"""Unit tests for voyagent_api.observability.

Targets the pure helpers + PII scrubbing wiring around the Sentry SDK
(``init_sentry``, ``_before_send``, ``TenantTaggingMiddleware``). The
Sentry SDK itself is not tested — we only verify the wiring that lives
inside this repo. All interactions with ``sentry_sdk`` are mocked so
no network calls or global SDK state are created.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# Auth secret must be set before any voyagent_api module imports (some
# shared fixtures import main.py transitively).
os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from voyagent_api import observability  # noqa: E402
from voyagent_api.observability import (  # noqa: E402
    TenantTaggingMiddleware,
    _before_send,
    _scrub_event,
    init_sentry,
)


# --------------------------------------------------------------------------- #
# init_sentry                                                                 #
# --------------------------------------------------------------------------- #


def test_init_sentry_is_noop_when_dsn_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGENT_SENTRY_DSN_API", raising=False)
    with patch("sentry_sdk.init") as mock_init:
        init_sentry()
    assert mock_init.call_count == 0


def test_init_sentry_calls_sdk_when_dsn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGENT_SENTRY_DSN_API", "https://abc@sentry.example.invalid/1")
    monkeypatch.setenv("VOYAGENT_SENTRY_ENVIRONMENT", "test-env")
    monkeypatch.setenv("VOYAGENT_VERSION", "9.9.9-test")
    monkeypatch.delenv("VOYAGENT_SENTRY_TRACES_SAMPLE_RATE", raising=False)
    with patch("sentry_sdk.init") as mock_init:
        init_sentry()
    assert mock_init.call_count == 1
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://abc@sentry.example.invalid/1"
    assert kwargs["environment"] == "test-env"
    assert kwargs["release"] == "9.9.9-test"
    assert kwargs["traces_sample_rate"] == 0.1
    assert kwargs["send_default_pii"] is False
    # The scrubbing hook must be wired in.
    assert kwargs["before_send"] is _before_send


def test_init_sentry_respects_traces_sample_rate_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGENT_SENTRY_DSN_API", "https://abc@sentry.example.invalid/1")
    monkeypatch.setenv("VOYAGENT_SENTRY_TRACES_SAMPLE_RATE", "0.5")
    with patch("sentry_sdk.init") as mock_init:
        init_sentry()
    assert mock_init.call_args.kwargs["traces_sample_rate"] == 0.5


# --------------------------------------------------------------------------- #
# before_send / event scrubbing                                               #
# --------------------------------------------------------------------------- #


def test_before_send_strips_authorization_header() -> None:
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
                "x-trace-id": "abc-123",
            }
        }
    }
    out = _before_send(event, {})
    assert out["request"]["headers"]["authorization"] != "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    assert "eyJhbGciOiJIUzI1NiJ9.payload.sig" not in str(out["request"]["headers"]["authorization"])
    # Unrelated header preserved.
    assert out["request"]["headers"]["x-trace-id"] == "abc-123"


def test_before_send_strips_cookie_header() -> None:
    event = {
        "request": {
            "headers": {"cookie": "voyagent_at=supersecret; other=1"}
        }
    }
    out = _before_send(event, {})
    assert "supersecret" not in str(out["request"]["headers"]["cookie"])


def test_before_send_strips_password_field() -> None:
    event = {"extra": {"password": "hunter2", "user": "alice"}}
    out = _before_send(event, {})
    assert out["extra"]["password"] != "hunter2"
    assert "hunter2" not in str(out["extra"]["password"])
    assert out["extra"]["user"] == "alice"


def test_before_send_strips_jwt_in_query_string() -> None:
    event = {
        "request": {
            "query_string": "token=eyJhbGciOiJIUzI1NiJ9.xyz.abc&foo=bar"
        }
    }
    out = _before_send(event, {})
    assert "eyJhbGciOiJIUzI1NiJ9.xyz.abc" not in out["request"]["query_string"]
    assert "foo=bar" in out["request"]["query_string"]


def test_before_send_preserves_unrelated_fields() -> None:
    event = {
        "request": {
            "headers": {"x-trace-id": "abc-123"},
            "query_string": "page=2&size=10",
        },
        "extra": {"order_id": "ORD-42", "items": [1, 2, 3]},
        "level": "info",
    }
    out = _before_send(event, {})
    assert out["request"]["headers"]["x-trace-id"] == "abc-123"
    assert out["request"]["query_string"] == "page=2&size=10"
    assert out["extra"]["order_id"] == "ORD-42"
    assert out["extra"]["items"] == [1, 2, 3]
    assert out["level"] == "info"


def test_scrub_event_handles_malformed_event_without_raising() -> None:
    # Non-dict request / extra values must not crash the scrubber.
    event: dict = {"request": "not-a-dict", "extra": 42}
    out = _before_send(event, {})
    assert out is event or out == event


# --------------------------------------------------------------------------- #
# TenantTaggingMiddleware                                                     #
# --------------------------------------------------------------------------- #


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TenantTaggingMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _make_fake_jwt(payload: dict) -> str:
    """Hand-rolled unsigned JWT so we don't require PyJWT to encode."""
    import base64
    import json

    def b64(obj: dict) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(obj).encode())
            .rstrip(b"=")
            .decode()
        )

    header = b64({"alg": "none", "typ": "JWT"})
    body = b64(payload)
    return f"{header}.{body}.sig"


def test_tenant_tagging_middleware_sets_scope_tags() -> None:
    app = _build_app()
    token = _make_fake_jwt({"tenant_id": "tenant-42", "sub": "user-7"})

    fake_scope = MagicMock()
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_scope)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    # We need the middleware's `import sentry_sdk` inside dispatch to
    # succeed and return our stub. Use a fake module in sys.modules.
    import sys
    import types

    fake_sentry = types.ModuleType("sentry_sdk")
    fake_sentry.configure_scope = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkey_prev = sys.modules.get("sentry_sdk")
    sys.modules["sentry_sdk"] = fake_sentry
    try:
        with TestClient(app) as client:
            r = client.get("/ping", headers={"Authorization": f"Bearer {token}"})
    finally:
        if monkey_prev is not None:
            sys.modules["sentry_sdk"] = monkey_prev
        else:
            del sys.modules["sentry_sdk"]

    assert r.status_code == 200
    # The two expected tags were written to the scope.
    tag_calls = {call.args[0]: call.args[1] for call in fake_scope.set_tag.call_args_list}
    assert tag_calls.get("tenant_id") == "tenant-42"
    assert tag_calls.get("user_id") == "user-7"


def test_tenant_tagging_middleware_silent_on_missing_header() -> None:
    app = _build_app()
    fake_scope = MagicMock()
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_scope)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    import sys
    import types

    fake_sentry = types.ModuleType("sentry_sdk")
    fake_sentry.configure_scope = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkey_prev = sys.modules.get("sentry_sdk")
    sys.modules["sentry_sdk"] = fake_sentry
    try:
        with TestClient(app) as client:
            r = client.get("/ping")
    finally:
        if monkey_prev is not None:
            sys.modules["sentry_sdk"] = monkey_prev
        else:
            del sys.modules["sentry_sdk"]

    assert r.status_code == 200
    # No tags should have been written because there was no principal.
    assert fake_scope.set_tag.call_count == 0


def test_tenant_tagging_middleware_silent_on_bad_jwt() -> None:
    app = _build_app()
    fake_scope = MagicMock()
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_scope)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    import sys
    import types

    fake_sentry = types.ModuleType("sentry_sdk")
    fake_sentry.configure_scope = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkey_prev = sys.modules.get("sentry_sdk")
    sys.modules["sentry_sdk"] = fake_sentry
    try:
        with TestClient(app) as client:
            r = client.get(
                "/ping", headers={"Authorization": "Bearer garbage.not.jwt"}
            )
    finally:
        if monkey_prev is not None:
            sys.modules["sentry_sdk"] = monkey_prev
        else:
            del sys.modules["sentry_sdk"]

    assert r.status_code == 200
    assert fake_scope.set_tag.call_count == 0
