"""Orchestrator run_turn tests — happy path, error path, approval path."""

from __future__ import annotations

from typing import Any

import pytest

from voyagent_agent_runtime.domain_agents.base import DomainAgentRequest
from voyagent_agent_runtime.events import AgentEvent, AgentEventKind
from voyagent_agent_runtime.orchestrator import Orchestrator

from .conftest import (
    FakeContentBlockDelta,
    FakeFinalMessage,
    FakeMessageStop,
    FakeTextBlock,
    FakeTextDelta,
    FakeToolUseBlock,
    make_script_text_then_stop,
    make_script_tool_use,
)


class StubDomainAgent:
    """Emits a fixed text delta and returns, simulating a domain agent."""

    name = "ticketing_visa"
    system_prompt = "x"
    tools: list[str] = []

    def __init__(self) -> None:
        self.calls: list[DomainAgentRequest] = []

    async def run(self, request: DomainAgentRequest):
        self.calls.append(request)
        yield AgentEvent(
            kind=AgentEventKind.TEXT_DELTA,
            session_id=request.session.id,
            turn_id=request.tool_context.turn_id,
            text="ack from stub",
        )


async def _collect(stream) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    async for ev in stream:
        out.append(ev)
    return out


async def test_happy_path_handoff_then_domain_agent(
    fake_anthropic_factory,
    memory_audit_sink,
    make_session,
    driver_registry,
) -> None:
    # Scripts: orchestrator emits a text delta, then calls handoff tool.
    text_script = [
        FakeContentBlockDelta(delta=FakeTextDelta(text="Routing you to tickets. ")),
        FakeMessageStop(
            message=FakeFinalMessage(
                stop_reason="tool_use",
                content=[
                    FakeTextBlock(text="Routing you to tickets. "),
                    FakeToolUseBlock(
                        id="toolu_1",
                        name="handoff",
                        input={"domain": "ticketing_visa", "goal": "fare DEL-DXB"},
                    ),
                ],
            )
        ),
    ]
    client = fake_anthropic_factory([text_script])

    stub_agent = StubDomainAgent()
    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=memory_audit_sink,
        available_domains=["ticketing_visa"],
        handoff_resolver=lambda d: stub_agent,
        driver_registry=driver_registry,
    )

    sess = make_session()
    events = await _collect(orchestrator.run_turn(sess, "Fare DEL to DXB"))

    kinds = [ev.kind for ev in events]
    assert AgentEventKind.TEXT_DELTA in kinds
    assert AgentEventKind.TOOL_USE in kinds
    assert kinds[-1] is AgentEventKind.FINAL
    assert len(stub_agent.calls) == 1
    assert stub_agent.calls[0].goal == "fare DEL-DXB"


async def test_error_path_emits_error_then_final(
    fake_anthropic_factory,
    memory_audit_sink,
    make_session,
    driver_registry,
) -> None:
    class BoomMessages:
        def stream(self, **kwargs: Any):
            raise RuntimeError("upstream exploded")

    class BoomClient:
        messages = BoomMessages()

        async def close(self) -> None:
            return None

    from voyagent_agent_runtime.anthropic_client import AnthropicClient, Settings

    client = AnthropicClient(Settings(), client=BoomClient())

    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=memory_audit_sink,
        available_domains=["ticketing_visa"],
        handoff_resolver=lambda d: (_ for _ in ()).throw(  # pragma: no cover
            KeyError(d)
        ),
        driver_registry=driver_registry,
    )

    events = await _collect(orchestrator.run_turn(make_session(), "hello"))
    kinds = [ev.kind for ev in events]
    assert AgentEventKind.ERROR in kinds
    assert kinds[-1] is AgentEventKind.FINAL


async def test_approval_path_pauses_turn(
    fake_anthropic_factory,
    memory_audit_sink,
    make_session,
    driver_registry,
) -> None:
    """Orchestrator sends to ticketing agent; ticketing agent calls
    issue_ticket which triggers an approval request. The orchestrator
    yields APPROVAL_REQUEST and FINAL."""

    class IssueTicketAgent:
        name = "ticketing_visa"
        system_prompt = "x"
        tools: list[str] = ["issue_ticket"]

        async def run(self, request: DomainAgentRequest):
            from voyagent_agent_runtime.tools import invoke_tool

            outcome = await invoke_tool(
                "issue_ticket",
                {"pnr_id": "ORDER-1"},
                request.tool_context,
                audit_sink=memory_audit_sink,
            )
            yield AgentEvent(
                kind=AgentEventKind.APPROVAL_REQUEST,
                session_id=request.session.id,
                turn_id=request.tool_context.turn_id,
                tool_name="issue_ticket",
                tool_call_id="toolu_x",
                approval_id=outcome.approval_id,
                approval_summary=outcome.approval_summary,
            )

    # Orchestrator call: handoff to ticketing_visa.
    handoff_script = make_script_tool_use(
        "handoff",
        {"domain": "ticketing_visa", "goal": "issue the ticket"},
    )
    client = fake_anthropic_factory([handoff_script])

    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=memory_audit_sink,
        available_domains=["ticketing_visa"],
        handoff_resolver=lambda d: IssueTicketAgent(),
        driver_registry=driver_registry,
    )

    # contract changed — RBAC short-circuit runs before the approval gate; pass
    # actor_role so issue_ticket's approval_roles check lets the approval through.
    events = await _collect(
        orchestrator.run_turn(make_session(), "issue it", actor_role="agency_admin")
    )
    kinds = [ev.kind for ev in events]
    assert AgentEventKind.APPROVAL_REQUEST in kinds
    assert kinds[-1] is AgentEventKind.FINAL
