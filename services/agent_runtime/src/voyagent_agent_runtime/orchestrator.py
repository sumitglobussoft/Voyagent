"""The orchestrator — Voyagent's router and per-turn controller.

The orchestrator accepts a user message, runs the orchestrator agent
loop with ``handoff`` + ``clarify`` tools, and — on a ``handoff`` call —
resolves the target domain agent and re-streams its events. On any tool
call that needs human approval, the orchestrator yields an APPROVAL_REQUEST
and stops; the caller (API) resumes the next turn with the approvals map
populated.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from ._agent_loop import run_agent_turn
from .anthropic_client import AnthropicClient
from .domain_agents.base import DomainAgent, DomainAgentRequest
from .events import AgentEvent, AgentEventKind
from .prompts import ORCHESTRATOR_SYSTEM_PROMPT
from .session import Message, Session
from .tenant_registry import TENANT_REGISTRY_KEY, TenantRegistry
from .tools import (
    ORCHESTRATOR_TOOL_NAMES,
    AuditSink,
    DRIVER_REGISTRY_KEY,
    ToolContext,
)

logger = logging.getLogger(__name__)


HandoffResolver = Callable[[str], DomainAgent]


class Orchestrator:
    """Top-level per-turn controller.

    Constructor:
      ``anthropic_client``   Wrapper that streams Anthropic responses.
      ``audit_sink``         Where tool-side-effect audit events go.
      ``available_domains``  Domain keys the orchestrator is allowed to route to.
      ``handoff_resolver``   Maps ``"ticketing_visa"`` → a concrete domain agent.
      ``tenant_registry``    :class:`TenantRegistry` that resolves a
                             per-tenant :class:`DriverRegistry` on demand.
                             Attached to the :class:`ToolContext` so
                             domain-agent tools can look up drivers
                             scoped to ``ctx.tenant_id``.
      ``driver_registry``    Deprecated process-wide fallback. When
                             supplied it is attached to the
                             :class:`ToolContext` under the legacy key
                             so pre-multi-tenant tool handlers keep
                             working during the migration.
    """

    def __init__(
        self,
        *,
        anthropic_client: AnthropicClient,
        audit_sink: AuditSink,
        available_domains: list[str],
        handoff_resolver: HandoffResolver,
        tenant_registry: TenantRegistry | None = None,
        driver_registry: Any | None = None,
    ) -> None:
        if tenant_registry is None and driver_registry is None:
            raise ValueError(
                "Orchestrator requires tenant_registry (preferred) or "
                "driver_registry (deprecated)."
            )
        self._client = anthropic_client
        self._audit = audit_sink
        self._domains = list(available_domains)
        self._resolve = handoff_resolver
        self._tenant_registry = tenant_registry
        self._drivers = driver_registry

    async def run_turn(
        self,
        session: Session,
        user_message: str,
        approvals: dict[str, bool] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn and stream events. Always ends with one FINAL event.

        ``approvals`` resumes a previously paused turn — the keys are
        approval ids emitted on the earlier APPROVAL_REQUEST events.
        """
        turn_id = _new_turn_id()
        extensions: dict[str, Any] = {}
        if self._tenant_registry is not None:
            extensions[TENANT_REGISTRY_KEY] = self._tenant_registry
        if self._drivers is not None:
            # Retained for tool handlers that still read the legacy key
            # during the multi-tenant migration.
            extensions[DRIVER_REGISTRY_KEY] = self._drivers
        ctx = ToolContext(
            tenant_id=session.tenant_id,
            actor_id=session.actor_id,
            actor_kind=session.actor_kind,
            session_id=session.id,
            turn_id=turn_id,
            approvals=dict(approvals or session.approvals_map()),
            extensions=extensions,
        )

        # Append the user message onto the transcript.
        user_turn = Message(
            role="user",
            content=[{"type": "text", "text": user_message}],
        )
        session.message_history = [*session.message_history, user_turn]

        working: list[dict] = [m.model_dump() for m in session.message_history]

        # Track handoff — if the orchestrator calls ``handoff``, we run the
        # target domain agent and surface its events instead of continuing
        # the orchestrator loop.
        handoff_target: dict[str, str] | None = None

        async def _on_tool_use(name: str, tool_input: dict[str, Any]):
            """Intercept ``handoff`` / ``clarify`` locally."""
            nonlocal handoff_target
            if name == "handoff":
                domain = str(tool_input.get("domain", "")).strip()
                goal = str(tool_input.get("goal", "")).strip()
                if domain not in self._domains:
                    return [
                        AgentEvent(
                            kind=AgentEventKind.ERROR,
                            session_id=session.id,
                            turn_id=turn_id,
                            error_message=(
                                f"Handoff to unknown domain {domain!r}."
                            ),
                        )
                    ]
                handoff_target = {"domain": domain, "goal": goal}
                return []
            # Clarify is emitted as a plain TEXT_DELTA for the UI:
            if name == "clarify":
                question = str(tool_input.get("question", "")).strip()
                return [
                    AgentEvent(
                        kind=AgentEventKind.TEXT_DELTA,
                        session_id=session.id,
                        turn_id=turn_id,
                        text=question,
                    )
                ]
            return None

        errored = False
        approval_paused = False
        try:
            async for ev in run_agent_turn(
                client=self._client,
                audit_sink=self._audit,
                session_id=session.id,
                turn_id=turn_id,
                system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
                tool_names=ORCHESTRATOR_TOOL_NAMES,
                messages=working,
                tool_context=ctx,
                on_tool_use=_on_tool_use,
            ):
                yield ev
                if ev.kind is AgentEventKind.APPROVAL_REQUEST:
                    approval_paused = True
                    break
                if ev.kind is AgentEventKind.ERROR:
                    errored = True
        except Exception as exc:  # noqa: BLE001
            logger.exception("orchestrator stream failed")
            errored = True
            yield AgentEvent(
                kind=AgentEventKind.ERROR,
                session_id=session.id,
                turn_id=turn_id,
                error_message=f"{type(exc).__name__}: {exc}",
            )

        # Persist any assistant / tool-result turns the loop added.
        _sync_history(session, working)

        # If the orchestrator decided to hand off, run the domain agent.
        if handoff_target is not None and not approval_paused and not errored:
            try:
                agent = self._resolve(handoff_target["domain"])
                request = DomainAgentRequest(
                    session=session,
                    goal=handoff_target["goal"],
                    user_message=user_message,
                    tool_context=ctx,
                )
                async for ev in agent.run(request):
                    yield ev
                    if ev.kind is AgentEventKind.APPROVAL_REQUEST:
                        approval_paused = True
                        break
                    if ev.kind is AgentEventKind.ERROR:
                        errored = True
            except Exception as exc:  # noqa: BLE001
                logger.exception("domain agent failed")
                errored = True
                yield AgentEvent(
                    kind=AgentEventKind.ERROR,
                    session_id=session.id,
                    turn_id=turn_id,
                    error_message=f"{type(exc).__name__}: {exc}",
                )

        yield AgentEvent(
            kind=AgentEventKind.FINAL,
            session_id=session.id,
            turn_id=turn_id,
        )


def _new_turn_id() -> str:
    import uuid

    return f"t-{uuid.uuid4().hex[:12]}"


def _sync_history(session: Session, working: list[dict[str, Any]]) -> None:
    """Mirror any freshly-appended messages from ``working`` back onto session."""
    have = len(session.message_history)
    for m in working[have:]:
        session.message_history = [
            *session.message_history,
            Message(role=m["role"], content=list(m["content"])),
        ]


__all__ = ["HandoffResolver", "Orchestrator"]
