"""Hotels + holidays domain agent.

Owns hotel shopping, rate re-verification, booking, cancellation, and
reading existing hotel bookings. Mirrors the shape of the ticketing_visa
and accounting agents exactly — only the system prompt and tool subset
change.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from .._agent_loop import run_agent_turn
from ..anthropic_client import AnthropicClient
from ..events import AgentEvent, AgentEventKind
from ..prompts import HOTELS_HOLIDAYS_SYSTEM_PROMPT
from ..session import Message
from ..tools import HOTELS_HOLIDAYS_TOOL_NAMES, AuditSink
from .base import DomainAgentRequest

logger = logging.getLogger(__name__)


class HotelsHolidaysAgent:
    """Agent specialised in hotels, packages, and stay-side operations."""

    name = "hotels_holidays"
    system_prompt = HOTELS_HOLIDAYS_SYSTEM_PROMPT
    tools = HOTELS_HOLIDAYS_TOOL_NAMES

    def __init__(self, client: AnthropicClient, audit_sink: AuditSink) -> None:
        self._client = client
        self._audit = audit_sink

    async def run(self, request: DomainAgentRequest) -> AsyncIterator[AgentEvent]:
        """Stream one handoff — intake + any tool calls + narration.

        Structurally identical to
        :meth:`TicketingVisaAgent.run`; the approval gate pauses
        streaming on :class:`AgentEventKind.APPROVAL_REQUEST` so the
        caller can surface a human decision before ``book_hotel`` or
        ``cancel_hotel_booking`` execute.
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
                return
            if ev.kind is AgentEventKind.ERROR:
                final_emitted = False

        baseline = len(session.message_history) + 1
        for m in working_messages[baseline:]:
            session.message_history = [
                *session.message_history,
                Message(role=m["role"], content=list(m["content"])),
            ]

        if not final_emitted:
            return


__all__ = ["HotelsHolidaysAgent"]
