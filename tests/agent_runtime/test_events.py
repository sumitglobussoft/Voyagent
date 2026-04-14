"""AgentEvent validator coverage."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from voyagent_agent_runtime.events import AgentEvent, AgentEventKind


def _id() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def test_text_delta_requires_text() -> None:
    with pytest.raises(ValidationError):
        AgentEvent(kind=AgentEventKind.TEXT_DELTA, session_id=_id(), turn_id="t-1")


def test_tool_use_requires_tool_fields() -> None:
    with pytest.raises(ValidationError):
        AgentEvent(
            kind=AgentEventKind.TOOL_USE,
            session_id=_id(),
            turn_id="t-1",
            tool_name="search_flights",
            # missing tool_input + tool_call_id
        )


def test_tool_use_valid() -> None:
    ev = AgentEvent(
        kind=AgentEventKind.TOOL_USE,
        session_id=_id(),
        turn_id="t-1",
        tool_name="search_flights",
        tool_input={"origin": "DEL"},
        tool_call_id="toolu_1",
    )
    assert ev.tool_name == "search_flights"


def test_approval_request_requires_summary() -> None:
    with pytest.raises(ValidationError):
        AgentEvent(
            kind=AgentEventKind.APPROVAL_REQUEST,
            session_id=_id(),
            turn_id="t-1",
            approval_id="ap-1",
        )


def test_error_requires_message() -> None:
    with pytest.raises(ValidationError):
        AgentEvent(kind=AgentEventKind.ERROR, session_id=_id(), turn_id="t-1")


def test_final_has_no_required_payload() -> None:
    ev = AgentEvent(kind=AgentEventKind.FINAL, session_id=_id(), turn_id="t-1")
    assert ev.kind is AgentEventKind.FINAL
