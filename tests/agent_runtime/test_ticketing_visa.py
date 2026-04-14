"""TicketingVisa tool handler tests — exercise them directly against the stub."""

from __future__ import annotations

import pytest

from voyagent_agent_runtime.tools import InMemoryAuditSink, invoke_tool


async def test_search_flights_produces_compact_summaries(tool_context, stub_amadeus):
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "search_flights",
        {
            "origin": "DEL",
            "destination": "DXB",
            "outbound_date": "2026-05-10",
            "passengers": {"adult": 2},
            "cabin": "economy",
            "direct_only": False,
        },
        tool_context,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    assert outcome.output is not None
    assert outcome.output["count"] == 1
    fare = outcome.output["fares"][0]
    assert fare["price"].startswith("INR ")
    assert fare["source"] == "stub_amadeus"
    # Read-only: no audit event written.
    assert sink.events == []
    assert len(stub_amadeus.search_calls) == 1


async def test_read_pnr_returns_structured_summary(tool_context, stub_amadeus):
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "read_pnr",
        {"locator": "ABC123"},
        tool_context,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    assert outcome.output["locator"] == "ABC123"
    assert outcome.output["source"] == "stub_amadeus"
    assert outcome.output["passenger_count"] == 1
    assert sink.events == []
    assert stub_amadeus.read_calls == ["ABC123"]


async def test_issue_ticket_is_gated_by_approval(tool_context, stub_amadeus):
    sink = InMemoryAuditSink()
    first = await invoke_tool(
        "issue_ticket",
        {"pnr_id": "ORDER-1"},
        tool_context,
        audit_sink=sink,
    )
    assert first.kind == "approval_needed"
    # Handler was never called without approval.
    assert stub_amadeus.issue_calls == []


async def test_issue_ticket_after_approval_returns_not_supported(
    tool_context, stub_amadeus
):
    sink = InMemoryAuditSink()
    first = await invoke_tool(
        "issue_ticket",
        {"pnr_id": "ORDER-1"},
        tool_context,
        audit_sink=sink,
    )
    tool_context.approvals = {first.approval_id: True}
    second = await invoke_tool(
        "issue_ticket",
        {"pnr_id": "ORDER-1"},
        tool_context,
        audit_sink=sink,
    )
    assert second.kind == "success"
    assert second.output["issued"] is False
    assert second.output["reason"] == "capability_not_supported"
    assert stub_amadeus.issue_calls == ["ORDER-1"]
