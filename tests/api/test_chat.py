"""Tests for the /chat SSE surface.

Strategy
--------
We avoid a hard dependency on the real ``voyagent_agent_runtime`` package by
**injecting a stub module into ``sys.modules``** before ``voyagent_api.chat``
imports it. The stub exposes the minimum surface the chat router calls:
``AgentEvent``, ``AgentEventKind``, ``Session``, ``new_session_id``,
``coerce_entity_id``, and a ``build_default_runtime()`` returning a bundle
with ``session_store`` + ``orchestrator`` whose ``run_turn`` yields two
events.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, AsyncIterator

import pytest
from pydantic import BaseModel


# --------------------------------------------------------------------------- #
# Build and register the stub runtime BEFORE importing the chat module.       #
# --------------------------------------------------------------------------- #


class _StubKind(StrEnum):
    TEXT_DELTA = "text_delta"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    ERROR = "error"
    FINAL = "final"


class _StubAgentEvent(BaseModel):
    kind: _StubKind
    session_id: str
    turn_id: str
    timestamp: datetime
    text: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: dict[str, Any] | None = None
    tool_call_id: str | None = None
    approval_id: str | None = None
    approval_summary: str | None = None
    error_message: str | None = None


class _StubPendingApproval(BaseModel):
    id: str
    tool_name: str
    summary: str
    granted: bool | None = None


class _StubSession(BaseModel):
    id: str
    tenant_id: str
    actor_id: str
    message_history: list[dict[str, Any]] = []
    pending_approvals: dict[str, _StubPendingApproval] = {}


class _StubStore:
    def __init__(self) -> None:
        self._sessions: dict[str, _StubSession] = {}

    async def get(self, session_id: str) -> _StubSession | None:
        return self._sessions.get(session_id)

    async def put(self, session: _StubSession) -> None:
        self._sessions[session.id] = session


class _StubOrchestrator:
    async def run_turn(
        self,
        session: _StubSession,
        user_message: str,
        approvals: dict[str, bool] | None = None,
    ) -> AsyncIterator[_StubAgentEvent]:
        now = datetime.now(timezone.utc)
        yield _StubAgentEvent(
            kind=_StubKind.TEXT_DELTA,
            session_id=session.id,
            turn_id="t1",
            timestamp=now,
            text="Hello, ",
        )
        yield _StubAgentEvent(
            kind=_StubKind.FINAL,
            session_id=session.id,
            turn_id="t1",
            timestamp=now,
            text="world!",
        )


class _StubBundle:
    def __init__(self) -> None:
        self.session_store = _StubStore()
        self.orchestrator = _StubOrchestrator()


def _new_session_id() -> str:
    # Stub — the real runtime emits UUIDv7s; tests don't care about shape.
    import uuid

    return str(uuid.uuid4())


def _coerce_entity_id(raw: str, *, namespace: str = "") -> str:
    return raw


def _install_stub_runtime() -> None:
    mod = types.ModuleType("voyagent_agent_runtime")
    mod.AgentEvent = _StubAgentEvent  # type: ignore[attr-defined]
    mod.AgentEventKind = _StubKind  # type: ignore[attr-defined]
    mod.Session = _StubSession  # type: ignore[attr-defined]
    mod.build_default_runtime = _StubBundle  # type: ignore[attr-defined]
    mod.new_session_id = _new_session_id  # type: ignore[attr-defined]
    mod.coerce_entity_id = _coerce_entity_id  # type: ignore[attr-defined]
    sys.modules["voyagent_agent_runtime"] = mod


_install_stub_runtime()


# Import after the stub is in place so the lru_cache captures it.
from fastapi.testclient import TestClient  # noqa: E402

from voyagent_api import auth as auth_module  # noqa: E402
from voyagent_api import chat as chat_module  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# Dev-mode auth headers shared across tests.
_DEV_HEADERS = {
    "X-Voyagent-Dev-Tenant": "t1",
    "X-Voyagent-Dev-Actor": "a1",
    "X-Voyagent-Dev-Role": "agent",
}


@pytest.fixture(autouse=True)
def _reset_runtime_caches() -> None:
    chat_module._runtime.cache_clear()
    chat_module._bundle = None
    _install_stub_runtime()
    # Disable auth signature verification; rely on dev headers.
    auth_module.set_auth_settings_for_test(
        auth_module.AuthSettings(
            enabled=False,
            jwks_url="",
            issuer="",
        )
    )
    yield
    auth_module.set_auth_settings_for_test(None)


def test_create_session_and_stream_sse() -> None:
    client = TestClient(app)

    r = client.post("/chat/sessions", json={}, headers=_DEV_HEADERS)
    assert r.status_code == 201, r.text
    session_id = r.json()["session_id"]

    meta = client.get(f"/chat/sessions/{session_id}", headers=_DEV_HEADERS)
    assert meta.status_code == 200
    body = meta.json()
    assert body["session_id"] == session_id
    # Canonical ids are derived deterministically from the dev headers.
    from voyagent_api.tenancy import tenant_id_from_external, user_id_from_external

    assert body["tenant_id"] == tenant_id_from_external("t1")
    assert body["actor_id"] == user_id_from_external("t1", "a1")
    assert body["pending_approvals"] == []

    with client.stream(
        "POST",
        f"/chat/sessions/{session_id}/messages",
        json={"message": "hi", "approvals": None},
        headers=_DEV_HEADERS,
    ) as resp:
        assert resp.status_code == 200
        ctype = resp.headers["content-type"]
        assert ctype.startswith("text/event-stream"), ctype
        events = _parse_sse_stream(resp.iter_text())

    agent_events = [e for e in events if e["event"] == "agent_event"]
    assert len(agent_events) == 2
    assert agent_events[0]["data"]["kind"] == "text_delta"
    assert agent_events[0]["data"]["text"] == "Hello, "
    assert agent_events[1]["data"]["kind"] == "final"


def test_missing_session_returns_404() -> None:
    client = TestClient(app)
    r = client.get("/chat/sessions/does-not-exist", headers=_DEV_HEADERS)
    assert r.status_code == 404


def test_cross_tenant_session_returns_404() -> None:
    """A session owned by tenant A must be invisible to tenant B (as 404)."""
    client = TestClient(app)
    r = client.post("/chat/sessions", json={}, headers=_DEV_HEADERS)
    assert r.status_code == 201
    session_id = r.json()["session_id"]

    # Same user, different tenant → must look like the session doesn't exist.
    other_headers = {
        **_DEV_HEADERS,
        "X-Voyagent-Dev-Tenant": "t2",
    }
    r2 = client.get(f"/chat/sessions/{session_id}", headers=other_headers)
    assert r2.status_code == 404


def test_missing_auth_returns_401() -> None:
    """Dev mode without the dev headers → 401, not a silent demo principal."""
    client = TestClient(app)
    r = client.post("/chat/sessions", json={})
    assert r.status_code == 401


def test_runtime_unavailable_returns_503() -> None:
    sys.modules.pop("voyagent_agent_runtime", None)
    chat_module._runtime.cache_clear()
    chat_module._bundle = None

    client = TestClient(app)
    r = client.post("/chat/sessions", json={}, headers=_DEV_HEADERS)
    assert r.status_code == 503
    assert r.json()["detail"] == "agent_runtime_unavailable"


# --------------------------------------------------------------------------- #
# SSE parsing helper — minimal, local to this test module.                    #
# --------------------------------------------------------------------------- #


def _parse_sse_stream(chunks: Any) -> list[dict[str, Any]]:
    import json

    buffer = ""
    events: list[dict[str, Any]] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            data_lines = []
            return
        raw = "\n".join(data_lines)
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        events.append({"event": event_name, "data": parsed})
        event_name = "message"
        data_lines = []

    for chunk in chunks:
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line == "":
                flush()
                for ev in events:
                    if (
                        ev["event"] == "agent_event"
                        and isinstance(ev["data"], dict)
                        and ev["data"].get("kind") == "final"
                    ):
                        return events
                continue
            if line.startswith(":"):
                continue
            if ":" in line:
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
            else:
                field, value = line, ""
            if field == "event":
                event_name = value
            elif field == "data":
                data_lines.append(value)
    flush()
    return events
