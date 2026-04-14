"""Accounting domain agent.

Owns the ledger-facing tool subset: listing chart of accounts, posting
journals, creating invoices, fetching BSP statements, and running
deterministic BSP reconciliation. The agent runs its own Anthropic
stream with the accounting system prompt.

Design constraints (see :mod:`prompts`):

* Posting journals and creating invoices require explicit human
  approval — the runtime enforces the gate via
  :func:`voyagent_agent_runtime.tools.invoke_tool`; the agent's job is
  to assemble a clear approval summary.
* Reconciliation is deterministic — the agent narrates findings, it
  does not "decide" the outcomes.
* Ledger account ids are never fabricated — the agent calls
  ``list_ledger_accounts`` first and references returned ids verbatim.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from .._agent_loop import run_agent_turn
from ..anthropic_client import AnthropicClient
from ..events import AgentEvent, AgentEventKind
from ..prompts import ACCOUNTING_SYSTEM_PROMPT
from ..session import Message
from ..tools import ACCOUNTING_TOOL_NAMES, AuditSink
from .base import DomainAgentRequest

logger = logging.getLogger(__name__)


class AccountingAgent:
    """Agent specialised in ledger, invoices, and BSP reconciliation."""

    name = "accounting"
    system_prompt = ACCOUNTING_SYSTEM_PROMPT
    tools = ACCOUNTING_TOOL_NAMES

    def __init__(self, client: AnthropicClient, audit_sink: AuditSink) -> None:
        self._client = client
        self._audit = audit_sink

    async def run(self, request: DomainAgentRequest) -> AsyncIterator[AgentEvent]:
        """Stream one handoff — intake + any tool calls + narration.

        Mirrors :class:`TicketingVisaAgent.run` exactly; the only
        difference is the tool subset and the system prompt.
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


__all__ = ["AccountingAgent"]
