"""Ticketing + visa domain agent.

Owns flight search, PNR reads, and ticket issuance. The agent runs its
own Anthropic stream with the ticketing/visa system prompt and the
:data:`TICKETING_VISA_TOOL_NAMES` tool subset.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from .._agent_loop import run_agent_turn
from ..anthropic_client import AnthropicClient
from ..events import AgentEvent, AgentEventKind
from ..prompts import TICKETING_VISA_SYSTEM_PROMPT
from ..session import Message
from ..tools import TICKETING_VISA_TOOL_NAMES, AuditSink
from .base import DomainAgentRequest

logger = logging.getLogger(__name__)


class TicketingVisaAgent:
    """Agent specialised in flights, PNRs, and visa files."""

    name = "ticketing_visa"
    system_prompt = TICKETING_VISA_SYSTEM_PROMPT
    tools = TICKETING_VISA_TOOL_NAMES

    def __init__(self, client: AnthropicClient, audit_sink: AuditSink) -> None:
        self._client = client
        self._audit = audit_sink

    async def run(self, request: DomainAgentRequest) -> AsyncIterator[AgentEvent]:
        """Stream one handoff — a greeting + intake + any tool calls.

        The agent seeds its own message with the orchestrator's goal plus
        the original user message, so it has the same context the
        orchestrator saw.
        """
        session = request.session
        ctx = request.tool_context

        seed = (
            f"[handoff from orchestrator]\nGoal: {request.goal}\n"
            f"User said: {request.user_message}"
        )
        working_messages: list[dict] = [
            *[m.model_dump() for m in session.message_history],
            {"role": "user", "content": [{"type": "text", "text": seed}]},
        ]

        final_emitted = False
        async for ev in run_agent_turn(
            client=self._client,
            audit_sink=self._audit,
            session_id=session.id,
            turn_id=ctx.turn_id,
            system_prompt=self.system_prompt,
            tool_names=self.tools,
            messages=working_messages,
            tool_context=ctx,
        ):
            yield ev
            if ev.kind is AgentEventKind.APPROVAL_REQUEST:
                # Caller pauses until approval resolves.
                return
            if ev.kind is AgentEventKind.ERROR:
                final_emitted = False  # still emit FINAL

        # Persist new messages back onto the session so the next turn has
        # the right transcript. We only append what was added beyond the
        # pre-seeded history.
        baseline = len(session.message_history) + 1  # + seed message
        for m in working_messages[baseline:]:
            session.message_history = [
                *session.message_history,
                Message(role=m["role"], content=list(m["content"])),
            ]

        if not final_emitted:
            # No explicit FINAL inside the loop; orchestrator will emit the
            # turn-level FINAL. Domain agents do not emit FINAL themselves.
            return


__all__ = ["TicketingVisaAgent"]
