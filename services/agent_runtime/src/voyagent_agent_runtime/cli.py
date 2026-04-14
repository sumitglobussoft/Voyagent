"""Interactive REPL for manual smoke-testing of the agent runtime.

    voyagent-agent-runtime chat

Reads user lines from stdin, runs :meth:`Orchestrator.run_turn`, and
prints events to stdout. When an APPROVAL_REQUEST is emitted, the CLI
prompts ``[y/N]`` and resubmits the turn with the approvals populated.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import Any

from schemas.canonical import ActorKind

from .anthropic_client import AnthropicClient, Settings
from .domain_agents import TicketingVisaAgent
from .drivers import DriverRegistry, build_default_registry
from .events import AgentEvent, AgentEventKind
from .orchestrator import Orchestrator
from .session import InMemorySessionStore, Session
from .tools import InMemoryAuditSink


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def _print(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


async def _chat() -> int:
    settings = Settings()
    if not settings.anthropic_api_key.get_secret_value():
        sys.stderr.write(
            "ANTHROPIC_API_KEY is not set. Set it in your environment and retry.\n"
        )
        return 2

    client = AnthropicClient(settings)
    audit = InMemoryAuditSink()
    try:
        registry: DriverRegistry = build_default_registry()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"Failed to build driver registry: {exc}\n"
            f"Set VOYAGENT_AMADEUS_CLIENT_ID / _CLIENT_SECRET.\n"
        )
        return 2

    ticketing = TicketingVisaAgent(client, audit)

    def _resolver(domain: str) -> Any:
        if domain == "ticketing_visa":
            return ticketing
        raise KeyError(f"No domain agent registered for {domain!r}.")

    orchestrator = Orchestrator(
        anthropic_client=client,
        audit_sink=audit,
        available_domains=["ticketing_visa"],
        handoff_resolver=_resolver,
        driver_registry=registry,
    )

    store = InMemorySessionStore()
    session = Session(
        id=_uuid7_like(),
        tenant_id=_uuid7_like(),
        actor_id=_uuid7_like(),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(session)

    _print(
        "Voyagent agent runtime — chat REPL.\n"
        f"Model: {client.model}. Session: {session.id}\n"
        "Type your message and press Enter. Ctrl-C to exit.\n\n"
    )

    try:
        while True:
            try:
                _print("you> ")
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            except KeyboardInterrupt:
                break
            if not line:
                break
            user_msg = line.strip()
            if not user_msg:
                continue

            approvals: dict[str, bool] = {}
            while True:
                pending_ap: str | None = None
                async for ev in orchestrator.run_turn(session, user_msg, approvals=approvals):
                    _render(ev)
                    if ev.kind is AgentEventKind.APPROVAL_REQUEST:
                        pending_ap = ev.approval_id
                if pending_ap is None:
                    break
                _print(f"\n[approval needed: {pending_ap}] Approve? [y/N] ")
                resp = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                approvals[pending_ap] = resp.strip().lower().startswith("y")
                # Replay the same user message so the loop resumes; in real API
                # flow this is a separate call that carries only the approval.
            _print("\n")
    except KeyboardInterrupt:
        pass
    finally:
        await client.aclose()
        await registry.aclose()

    return 0


def _render(ev: AgentEvent) -> None:
    """Lightweight renderer for the REPL."""
    if ev.kind is AgentEventKind.TEXT_DELTA:
        _print(ev.text or "")
    elif ev.kind is AgentEventKind.TOOL_USE:
        _print(f"\n[tool_use {ev.tool_name} input={ev.tool_input}]\n")
    elif ev.kind is AgentEventKind.TOOL_RESULT:
        _print(f"[tool_result {ev.tool_name} output={ev.tool_output}]\n")
    elif ev.kind is AgentEventKind.APPROVAL_REQUEST:
        _print(f"\n[approval_request {ev.approval_id}] {ev.approval_summary}\n")
    elif ev.kind is AgentEventKind.ERROR:
        _print(f"\n[error] {ev.error_message}\n")
    elif ev.kind is AgentEventKind.FINAL:
        _print("\n[final]\n")


def main() -> int:
    """Entry point for the ``voyagent-agent-runtime`` script."""
    parser = argparse.ArgumentParser(prog="voyagent-agent-runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("chat", help="Start an interactive chat REPL.")
    args = parser.parse_args()

    if args.cmd == "chat":
        try:
            return asyncio.run(_chat())
        except KeyboardInterrupt:
            return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
