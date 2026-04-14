"""Tool registry, validation, approval gating, and audit behavior."""

from __future__ import annotations

from typing import Any

import pytest

from schemas.canonical import AuditStatus

from voyagent_agent_runtime.tools import (
    InMemoryAuditSink,
    ToolContext,
    ToolSpec,
    get_tool,
    invoke_tool,
    list_tools,
    register_tool,
)


# ------------------------------------------------------------------ #
# Registry isolation                                                 #
# ------------------------------------------------------------------ #
#
# The tool registry is a module-level dict populated on import. Tools
# added mid-test must be uniquely named (we use a ``_test_`` prefix).


# ------------------------------------------------------------------ #
# Schema validation                                                  #
# ------------------------------------------------------------------ #


async def test_invalid_input_returns_error(tool_context: ToolContext) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "search_flights",
        {"origin": "X"},  # missing required fields, origin too short
        tool_context,
        audit_sink=sink,
    )
    assert outcome.kind == "error"
    assert "validation" in (outcome.error_message or "").lower()
    assert sink.events == []


# ------------------------------------------------------------------ #
# Approval gating                                                    #
# ------------------------------------------------------------------ #


async def test_approval_required_short_circuits(tool_context: ToolContext) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "issue_ticket",
        {"pnr_id": "PNR123"},
        tool_context,
        audit_sink=sink,
    )
    assert outcome.kind == "approval_needed"
    assert outcome.approval_id and outcome.approval_id.startswith("ap-")
    assert outcome.approval_summary is not None
    # No audit before human acts on approval.
    assert sink.events == []


async def test_approval_granted_executes_and_audits(
    tool_context: ToolContext,
) -> None:
    sink = InMemoryAuditSink()

    # First call yields approval id.
    first = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR123"}, tool_context, audit_sink=sink
    )
    assert first.kind == "approval_needed"
    tool_context.approvals = {first.approval_id: True}

    # Second call executes the handler; the stub raises CapabilityNotSupported,
    # which the handler catches and returns a structured not-supported result.
    second = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR123"}, tool_context, audit_sink=sink
    )
    assert second.kind == "success"
    assert (second.output or {}).get("issued") is False
    assert (second.output or {}).get("reason") == "capability_not_supported"

    # Two audit events: STARTED then SUCCEEDED.
    assert len(sink.events) == 2
    assert sink.events[0].status == AuditStatus.STARTED
    assert sink.events[-1].status == AuditStatus.SUCCEEDED
    assert sink.events[-1].approved_by == tool_context.actor_id


async def test_approval_denied_records_rejected_audit(
    tool_context: ToolContext,
) -> None:
    sink = InMemoryAuditSink()
    first = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR123"}, tool_context, audit_sink=sink
    )
    tool_context.approvals = {first.approval_id: False}
    second = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR123"}, tool_context, audit_sink=sink
    )
    assert second.kind == "error"
    assert "denied" in (second.error_message or "").lower()
    assert [ev.status for ev in sink.events] == [AuditStatus.REJECTED]


# ------------------------------------------------------------------ #
# Handler exceptions produce failed audits                           #
# ------------------------------------------------------------------ #


async def test_side_effect_handler_failure_audits_failed(
    tool_context: ToolContext,
) -> None:
    """Register a custom side-effect tool that raises, and confirm the audit
    event is written with status=FAILED."""
    sink = InMemoryAuditSink()

    async def _explode(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        raise RuntimeError("boom")

    register_tool(
        ToolSpec(
            name="_test_explode",
            description="Test-only failing tool.",
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
        _explode,
    )
    outcome = await invoke_tool("_test_explode", {}, tool_context, audit_sink=sink)
    assert outcome.kind == "error"
    assert len(sink.events) == 2
    assert sink.events[-1].status == AuditStatus.FAILED
    assert "boom" in (sink.events[-1].error or "")


# ------------------------------------------------------------------ #
# Registry listing                                                   #
# ------------------------------------------------------------------ #


def test_list_tools_by_domain() -> None:
    tv = [t.spec.name for t in list_tools("ticketing_visa")]
    assert {"search_flights", "read_pnr", "issue_ticket"}.issubset(set(tv))
    cc = [t.spec.name for t in list_tools("cross_cutting")]
    assert {"handoff", "clarify"}.issubset(set(cc))


def test_get_tool_roundtrip() -> None:
    t = get_tool("search_flights")
    assert t.spec.domain == "ticketing_visa"
    assert t.spec.side_effect is False
