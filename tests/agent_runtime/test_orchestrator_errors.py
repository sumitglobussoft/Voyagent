"""Error-path tests for the orchestrator + shared agent loop.

These exercise failure modes that the happy-path suite in
``test_orchestrator.py`` does not cover:

  * A domain tool raising a DriverError.
  * An Anthropic client raising a simulated RateLimitError.
  * Upstream rate-limit bubbling up into a user-visible ERROR event.
  * Rejected approvals flowing back to the model as an error result
    rather than silently skipping.

Some of these are asserted in a forward-looking way; where the current
production implementation has a gap, the test is marked ``xfail`` with
``strict=False`` and a pointer to the missing behaviour.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from voyagent_agent_runtime.domain_agents.base import DomainAgentRequest
from voyagent_agent_runtime.events import AgentEvent, AgentEventKind
from voyagent_agent_runtime.orchestrator import Orchestrator
from voyagent_agent_runtime.tools import (
    InMemoryAuditSink,
    ToolContext,
    ToolSpec,
    invoke_tool,
    list_tools,
    register_tool,
)

from .conftest import (
    FakeFinalMessage,
    FakeMessageStop,
    FakeTextBlock,
    FakeToolUseBlock,
    make_script_tool_use,
)


pytestmark = pytest.mark.asyncio


async def _collect(stream) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    async for ev in stream:
        out.append(ev)
    return out


# --------------------------------------------------------------------------- #
# A domain agent whose single tool call blows up with a DriverError.          #
# --------------------------------------------------------------------------- #


def _register_boom_tool() -> str:
    """Register a one-off side-effect tool that raises a DriverError.

    Returns the tool name. Idempotent across tests in a module.
    """
    name = "_test_boom_tool"
    if name in {t.spec.name for t in list_tools()}:
        return name

    async def _handler(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        from drivers._contracts.errors import PermanentError

        raise PermanentError("stub", "simulated upstream failure")

    register_tool(
        ToolSpec(
            name=name,
            description="Test-only tool that always raises a DriverError.",
            input_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            side_effect=True,
            reversible=True,
            approval_required=False,
            domain="cross_cutting",
        ),
        _handler,
    )
    return name


class _FareLike(BaseModel):
    """Minimal output schema we can attach to a test tool to drive output validation."""

    id: str
    currency: str
    price: float


_BAD_SHAPE_CALLS: dict[str, int] = {"count": 0}


def _register_bad_shape_tool() -> str:
    """Register a tool that returns a dict that does NOT match a Fare shape.

    Production tool specs now carry an optional ``output_schema``; this
    test-only tool declares one and returns a payload that fails it on
    every call to exercise the retry-once-then-fail path.
    """
    name = "_test_bad_shape_fare"
    if name in {t.spec.name for t in list_tools()}:
        return name

    async def _handler(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        _BAD_SHAPE_CALLS["count"] += 1
        # Deliberately missing "price" — fails _FareLike validation.
        return {"id": "offer-1", "currency": "USD"}

    register_tool(
        ToolSpec(
            name=name,
            description="Test-only tool that returns an invalid Fare shape.",
            input_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            output_schema=_FareLike,
            side_effect=False,
            reversible=True,
            approval_required=False,
            domain="cross_cutting",
        ),
        _handler,
    )
    return name


# --------------------------------------------------------------------------- #
# 1. Tool raises a domain exception                                           #
# --------------------------------------------------------------------------- #


async def test_domain_tool_raising_driver_error_is_captured_as_audit_and_error(
    fake_anthropic_factory,
    memory_audit_sink: InMemoryAuditSink,
    make_session,
    driver_registry,
    tool_context: ToolContext,
) -> None:
    """When a tool raises, ``invoke_tool`` records an error outcome and a
    FAILED audit event. The orchestrator's domain agent can then surface
    that to the stream without crashing the loop."""
    tool_name = _register_boom_tool()

    class BoomAgent:
        name = "ticketing_visa"
        system_prompt = "x"
        tools = [tool_name]

        async def run(self, request: DomainAgentRequest):
            outcome = await invoke_tool(
                tool_name,
                {},
                request.tool_context,
                audit_sink=memory_audit_sink,
            )
            # Domain agent translates the failed outcome into a TOOL_RESULT
            # event with an error payload; the loop does not crash.
            # contract changed — AgentEvent (events.py) now requires tool_call_id
            # on TOOL_RESULT events.
            yield AgentEvent(
                kind=AgentEventKind.TOOL_RESULT,
                session_id=request.session.id,
                turn_id=request.tool_context.turn_id,
                tool_name=tool_name,
                tool_call_id="toolu_boom",
                tool_output={"error": outcome.error_message or "unknown"},
            )

    handoff_script = make_script_tool_use(
        "handoff", {"domain": "ticketing_visa", "goal": "use the boom tool"}
    )
    client = fake_anthropic_factory([handoff_script])

    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=memory_audit_sink,
        available_domains=["ticketing_visa"],
        handoff_resolver=lambda d: BoomAgent(),
        driver_registry=driver_registry,
    )

    events = await _collect(orchestrator.run_turn(make_session(), "do it"))
    kinds = [ev.kind for ev in events]
    # Loop did not explode; we saw a TOOL_RESULT and a FINAL.
    assert AgentEventKind.TOOL_RESULT in kinds
    assert kinds[-1] is AgentEventKind.FINAL
    # The failing tool left a FAILED audit row.
    from schemas.canonical import AuditStatus

    assert any(ev.status == AuditStatus.FAILED for ev in memory_audit_sink.events)


# --------------------------------------------------------------------------- #
# 2. Tool returns an invalid output shape                                     #
# --------------------------------------------------------------------------- #


async def test_tool_returning_invalid_shape_is_rejected_and_retried_once(
    tool_context: ToolContext,
) -> None:
    tool_name = _register_bad_shape_tool()
    sink = InMemoryAuditSink()
    _BAD_SHAPE_CALLS["count"] = 0

    outcome = await invoke_tool(tool_name, {}, tool_context, audit_sink=sink)
    assert outcome.kind == "error"
    assert "price" in (outcome.error_message or "").lower()
    # Retry-once policy: the handler runs twice before the error surfaces.
    assert _BAD_SHAPE_CALLS["count"] == 2
    # Error message uses the agreed tool_output_invalid prefix so the
    # agent loop can classify this distinctly from driver failures.
    assert "tool_output_invalid" in (outcome.error_message or "")


# --------------------------------------------------------------------------- #
# 3. Anthropic RateLimitError surfaces as an ERROR event                      #
# --------------------------------------------------------------------------- #


class _RateLimitedMessages:
    """Fake ``.messages`` that always raises a rate-limit-shaped error."""

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, **kwargs: Any):
        self.calls += 1
        # Anthropic's SDK raises ``anthropic.RateLimitError`` but we don't
        # want to import it in tests; a distinctly-named subclass of
        # ``Exception`` is sufficient — the agent loop catches Exception
        # and emits an ERROR event regardless of the exact type.
        class RateLimitError(Exception):  # noqa: D401
            """Simulated Anthropic rate limit."""

        raise RateLimitError("429 rate_limited: slow down")


class _RateLimitedClient:
    def __init__(self) -> None:
        self.messages = _RateLimitedMessages()

    async def close(self) -> None:
        return None


async def test_rate_limit_error_surfaces_as_final_error_event(
    memory_audit_sink: InMemoryAuditSink,
    make_session,
    driver_registry,
    monkeypatch,
) -> None:
    """An upstream rate-limit must become a user-visible ERROR event and
    still terminate cleanly with a FINAL — after retries are exhausted.
    """
    from voyagent_agent_runtime import _agent_loop
    from voyagent_agent_runtime.anthropic_client import AnthropicClient, Settings

    # Zero the retry backoff so the suite doesn't wait on real seconds.
    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_agent_loop, "_sleep", _no_sleep)

    inner = _RateLimitedClient()
    client = AnthropicClient(Settings(), client=inner)

    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=memory_audit_sink,
        available_domains=["ticketing_visa"],
        handoff_resolver=lambda d: (_ for _ in ()).throw(KeyError(d)),  # pragma: no cover
        driver_registry=driver_registry,
    )

    events = await _collect(orchestrator.run_turn(make_session(), "hi"))
    kinds = [ev.kind for ev in events]
    assert AgentEventKind.ERROR in kinds
    assert kinds[-1] is AgentEventKind.FINAL
    # User-visible error text mentions rate-limiting.
    error_events = [ev for ev in events if ev.kind is AgentEventKind.ERROR]
    assert any(
        "rate" in (ev.error_message or "").lower() for ev in error_events
    )


async def test_rate_limit_error_is_retried_before_surfacing(
    memory_audit_sink: InMemoryAuditSink,
    make_session,
    driver_registry,
    monkeypatch,
) -> None:
    from voyagent_agent_runtime import _agent_loop
    from voyagent_agent_runtime.anthropic_client import AnthropicClient, Settings

    # Zero-delay the retry backoff so the test runs in millis.
    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_agent_loop, "_sleep", _no_sleep)

    inner = _RateLimitedClient()
    client = AnthropicClient(Settings(), client=inner)
    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=memory_audit_sink,
        available_domains=["ticketing_visa"],
        handoff_resolver=lambda d: (_ for _ in ()).throw(KeyError(d)),  # pragma: no cover
        driver_registry=driver_registry,
    )
    events = await _collect(orchestrator.run_turn(make_session(), "hi"))
    expected_attempts = 1 + len(_agent_loop.RATE_LIMIT_BACKOFF_SECONDS)
    # 1 initial + one retry per configured backoff delay.
    assert inner.messages.calls == expected_attempts, (
        f"expected {expected_attempts} attempts, got {inner.messages.calls}"
    )
    assert inner.messages.calls >= 2
    # After retries exhaust, an ERROR bubbles up and FINAL closes cleanly.
    kinds = [ev.kind for ev in events]
    assert AgentEventKind.ERROR in kinds
    assert kinds[-1] is AgentEventKind.FINAL
    rate_msgs = [
        ev.error_message
        for ev in events
        if ev.kind is AgentEventKind.ERROR and ev.error_message
    ]
    assert any(
        "rate-limited" in m.lower() or "rate_limit" in m.lower() for m in rate_msgs
    )


# --------------------------------------------------------------------------- #
# 4. Approval-required + user rejection                                       #
# --------------------------------------------------------------------------- #


async def test_approval_rejected_yields_rejection_not_tool_error(
    tool_context: ToolContext,
) -> None:
    """A human-rejected approval is a REJECTED audit row, not a FAILED
    tool-error row. The tool handler never runs."""
    from schemas.canonical import AuditStatus

    sink = InMemoryAuditSink()

    # First invocation: approval requested.
    first = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR-reject-1"}, tool_context, audit_sink=sink
    )
    assert first.kind == "approval_needed"
    approval_id = first.approval_id
    assert approval_id is not None

    # Human rejects the approval.
    tool_context.approvals = {approval_id: False}

    second = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR-reject-1"}, tool_context, audit_sink=sink
    )
    # Contract: the outcome is an ``error`` outcome whose message signals
    # the rejection, not a raw driver-level failure.
    assert second.kind == "error"
    assert "denied" in (second.error_message or "").lower() or "reject" in (
        second.error_message or ""
    ).lower()
    # Audit shows a REJECTED row — NOT a FAILED row.
    statuses = [ev.status for ev in sink.events]
    assert AuditStatus.REJECTED in statuses
    assert AuditStatus.FAILED not in statuses
