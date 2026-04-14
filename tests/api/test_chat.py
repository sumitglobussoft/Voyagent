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

Auth is handled by the in-house service: each test seeds an isolated
SQLite database with a tenant + user, mints a real access token via
``issue_access_token``, and passes it as a Bearer header.
"""

from __future__ import annotations

import os
import sys
import types
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, AsyncIterator

import pytest
from pydantic import BaseModel


# Set the auth secret BEFORE importing voyagent_api modules.
os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)


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
    sse_last_event_id: int = 0
    sse_event_buffer: list[tuple[int, str]] = []


class _StubStore:
    def __init__(self) -> None:
        self._sessions: dict[str, _StubSession] = {}

    async def get(self, session_id: str) -> _StubSession | None:
        return self._sessions.get(session_id)

    async def put(self, session: _StubSession) -> None:
        self._sessions[session.id] = session


class _StubOrchestrator:
    def __init__(self) -> None:
        self.run_count = 0

    async def run_turn(
        self,
        session: _StubSession,
        user_message: str,
        approvals: dict[str, bool] | None = None,
        actor_role: str | None = None,
    ) -> AsyncIterator[_StubAgentEvent]:
        self.run_count += 1
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
    mod.SSE_REPLAY_BUFFER_CAP = 200  # type: ignore[attr-defined]
    sys.modules["voyagent_agent_runtime"] = mod


_install_stub_runtime()


# Import after the stub is in place so the lru_cache captures it.
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base, Tenant, User, UserRole  # noqa: E402

from voyagent_api import chat as chat_module  # noqa: E402
from voyagent_api import db as db_module  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.auth_inhouse.tokens import issue_access_token  # noqa: E402
from voyagent_api.main import app  # noqa: E402


@pytest.fixture
async def seeded_principal() -> dict[str, Any]:
    """Spin up a SQLite DB, seed a tenant + user, return token + ids."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)
    get_auth_settings.cache_clear()

    async with sm() as session:
        tenant = Tenant(display_name="Test Agency", default_currency="USD")
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id,
            external_id="ext-1",
            display_name="Agent Smith",
            email="smith@example.com",
            role=UserRole.AGENCY_ADMIN,
            password_hash=None,
            email_verified=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await session.refresh(tenant)
        ids = {"tenant_id": str(tenant.id), "user_id": str(user.id)}

    token, _exp, _jti = issue_access_token(
        user_id=ids["user_id"],
        tenant_id=ids["tenant_id"],
        email="smith@example.com",
        role="agency_admin",
    )
    yield {**ids, "token": token, "engine": engine, "sm": sm}

    db_module.set_engine_for_test(None)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_runtime_caches() -> None:
    chat_module._runtime.cache_clear()
    chat_module._bundle = None
    _install_stub_runtime()
    yield


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_session_and_stream_sse(seeded_principal) -> None:
    client = TestClient(app)
    headers = _bearer(seeded_principal["token"])

    r = client.post("/chat/sessions", json={}, headers=headers)
    assert r.status_code == 201, r.text
    session_id = r.json()["session_id"]

    meta = client.get(f"/chat/sessions/{session_id}", headers=headers)
    assert meta.status_code == 200
    body = meta.json()
    assert body["session_id"] == session_id
    assert body["tenant_id"] == seeded_principal["tenant_id"]
    assert body["actor_id"] == seeded_principal["user_id"]
    assert body["pending_approvals"] == []

    with client.stream(
        "POST",
        f"/chat/sessions/{session_id}/messages",
        json={"message": "hi", "approvals": None},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        ctype = resp.headers["content-type"]
        assert ctype.startswith("text/event-stream"), ctype
        events = _parse_sse_stream(resp.iter_text())

    agent_events = [e for e in events if e["event"] == "agent_event"]
    assert len(agent_events) == 2
    assert agent_events[0]["data"]["kind"] == "text_delta"
    assert agent_events[1]["data"]["kind"] == "final"


@pytest.mark.asyncio
async def test_missing_session_returns_404(seeded_principal) -> None:
    client = TestClient(app)
    r = client.get(
        "/chat/sessions/does-not-exist",
        headers=_bearer(seeded_principal["token"]),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_session_returns_404(seeded_principal) -> None:
    """A session owned by tenant A must be invisible to tenant B (as 404)."""
    client = TestClient(app)
    headers = _bearer(seeded_principal["token"])
    r = client.post("/chat/sessions", json={}, headers=headers)
    assert r.status_code == 201
    session_id = r.json()["session_id"]

    # Mint a token for a *different* tenant + user, both seeded into the DB.
    sm = seeded_principal["sm"]
    async with sm() as session:
        tenant2 = Tenant(display_name="Other Agency", default_currency="USD")
        session.add(tenant2)
        await session.flush()
        user2 = User(
            tenant_id=tenant2.id,
            external_id="ext-2",
            display_name="Other",
            email="other@example.com",
            role=UserRole.AGENCY_ADMIN,
        )
        session.add(user2)
        await session.commit()
        await session.refresh(user2)
        await session.refresh(tenant2)
        other_token, _exp, _jti = issue_access_token(
            user_id=str(user2.id),
            tenant_id=str(tenant2.id),
            email="other@example.com",
            role="agency_admin",
        )

    r2 = client.get(
        f"/chat/sessions/{session_id}", headers=_bearer(other_token)
    )
    assert r2.status_code == 404


def test_missing_auth_returns_401() -> None:
    """No Authorization header → 401."""
    client = TestClient(app)
    r = client.post("/chat/sessions", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_runtime_unavailable_returns_503(seeded_principal) -> None:
    sys.modules.pop("voyagent_agent_runtime", None)
    chat_module._runtime.cache_clear()
    chat_module._bundle = None

    client = TestClient(app)
    r = client.post(
        "/chat/sessions",
        json={},
        headers=_bearer(seeded_principal["token"]),
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "agent_runtime_unavailable"


# --------------------------------------------------------------------------- #
# Gap-fill: SSE ordering, cross-tenant messages, missing body, approvals.      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_sse_event_ordering_is_stable(seeded_principal) -> None:
    """The SSE stream must emit events in run_turn order and end on FINAL."""
    client = TestClient(app)
    headers = _bearer(seeded_principal["token"])

    r = client.post("/chat/sessions", json={}, headers=headers)
    session_id = r.json()["session_id"]

    with client.stream(
        "POST",
        f"/chat/sessions/{session_id}/messages",
        json={"message": "hi"},
        headers=headers,
    ) as resp:
        events = _parse_sse_stream(resp.iter_text())

    agent = [e for e in events if e["event"] == "agent_event"]
    kinds = [e["data"]["kind"] for e in agent]
    # text_delta must come strictly before final.
    assert "text_delta" in kinds
    assert "final" in kinds
    assert kinds.index("text_delta") < kinds.index("final")
    # final must be last (stream stops on first final).
    assert kinds[-1] == "final"


def test_send_message_missing_body_returns_422(seeded_principal) -> None:
    """POST /messages without a JSON body gets a 422 validation error."""
    client = TestClient(app)
    headers = _bearer(seeded_principal["token"])
    r = client.post("/chat/sessions", json={}, headers=headers)
    session_id = r.json()["session_id"]

    # ``json=None`` sends an empty body — FastAPI returns 422 for a missing
    # required model.
    r2 = client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        # No json= and no content → FastAPI returns 422.
    )
    assert r2.status_code == 422, r2.text


@pytest.mark.asyncio
async def test_cross_tenant_message_post_returns_404(seeded_principal) -> None:
    """Posting a message to another tenant's session must 404 (no leak)."""
    client = TestClient(app)
    headers = _bearer(seeded_principal["token"])
    r = client.post("/chat/sessions", json={}, headers=headers)
    session_id = r.json()["session_id"]

    # Mint a token for a fresh tenant.
    sm = seeded_principal["sm"]
    async with sm() as db:
        from schemas.storage import Tenant, User, UserRole

        tenant2 = Tenant(display_name="Other Agency", default_currency="USD")
        db.add(tenant2)
        await db.flush()
        user2 = User(
            tenant_id=tenant2.id,
            external_id="ext-3",
            display_name="Stranger",
            email="stranger@example.com",
            role=UserRole.AGENCY_ADMIN,
        )
        db.add(user2)
        await db.commit()
        await db.refresh(user2)
        await db.refresh(tenant2)

        from voyagent_api.auth_inhouse.tokens import issue_access_token

        other, _exp, _jti = issue_access_token(
            user_id=str(user2.id),
            tenant_id=str(tenant2.id),
            email="stranger@example.com",
            role="agency_admin",
        )

    r2 = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"message": "ping"},
        headers=_bearer(other),
    )
    assert r2.status_code == 404
    assert r2.json()["detail"] == "session_not_found"


# --------------------------------------------------------------------------- #
# SSE parsing helper                                                          #
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
