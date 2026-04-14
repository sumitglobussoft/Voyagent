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


# A local helper so RBAC tests can mint contexts with varying actor_role.
def _with_role(ctx: ToolContext, role: str) -> ToolContext:
    return ctx.model_copy(update={"actor_role": role})


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


# ------------------------------------------------------------------ #
# RBAC                                                               #
# ------------------------------------------------------------------ #


def _register_role_test_tools() -> None:
    """Register RBAC-scoped fixtures exactly once across the suite."""

    async def _noop(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        return {"ok": True}

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    if "_test_rbac_scoped" not in {t.spec.name for t in list_tools()}:
        register_tool(
            ToolSpec(
                name="_test_rbac_scoped",
                description="Approval-required tool limited to accountants.",
                input_schema=schema,
                side_effect=True,
                reversible=True,
                approval_required=True,
                approval_roles=["accountant"],
                domain="cross_cutting",
            ),
            _noop,
        )
    if "_test_rbac_any_role" not in {t.spec.name for t in list_tools()}:
        register_tool(
            ToolSpec(
                name="_test_rbac_any_role",
                description="Approval-required tool with empty approval_roles.",
                input_schema=schema,
                side_effect=True,
                reversible=True,
                approval_required=True,
                approval_roles=[],
                domain="cross_cutting",
            ),
            _noop,
        )


async def test_rbac_denies_when_role_missing(tool_context: ToolContext) -> None:
    _register_role_test_tools()
    sink = InMemoryAuditSink()
    ctx = _with_role(tool_context, "agent")
    outcome = await invoke_tool("_test_rbac_scoped", {}, ctx, audit_sink=sink)
    assert outcome.kind == "permission_denied"
    assert outcome.message and "not in" in outcome.message
    # A REJECTED audit row is written; no STARTED/SUCCEEDED pair.
    assert [ev.status for ev in sink.events] == [AuditStatus.REJECTED]


async def test_rbac_allows_when_role_matches(tool_context: ToolContext) -> None:
    _register_role_test_tools()
    sink = InMemoryAuditSink()
    ctx = _with_role(tool_context, "accountant")
    # First call asks for approval; second call with approval executes.
    first = await invoke_tool("_test_rbac_scoped", {}, ctx, audit_sink=sink)
    assert first.kind == "approval_needed"
    ctx.approvals = {first.approval_id: True}
    second = await invoke_tool("_test_rbac_scoped", {}, ctx, audit_sink=sink)
    assert second.kind == "success"
    assert sink.events[-1].status == AuditStatus.SUCCEEDED


async def test_rbac_empty_roles_means_any_authenticated_role(
    tool_context: ToolContext,
) -> None:
    _register_role_test_tools()
    sink = InMemoryAuditSink()
    ctx = _with_role(tool_context, "agent")
    # Empty approval_roles → RBAC short-circuit does not fire; falls
    # through to the normal approval gate.
    first = await invoke_tool("_test_rbac_any_role", {}, ctx, audit_sink=sink)
    assert first.kind == "approval_needed"
    ctx.approvals = {first.approval_id: True}
    second = await invoke_tool("_test_rbac_any_role", {}, ctx, audit_sink=sink)
    assert second.kind == "success"


# ------------------------------------------------------------------ #
# Domain scoping                                                     #
# ------------------------------------------------------------------ #


def test_list_tools_domain_scope_excludes_other_domains() -> None:
    """A ticketing-visa tool must NOT appear in the hotels tool set."""
    hotels = {t.spec.name for t in list_tools("hotels_holidays")}
    tv = {t.spec.name for t in list_tools("ticketing_visa")}
    accounting = {t.spec.name for t in list_tools("accounting")}

    # ticketing_visa tools are invisible to hotel listings.
    assert "search_flights" in tv
    assert "search_flights" not in hotels
    assert "search_flights" not in accounting

    # Hotel tools invisible to ticketing.
    assert "search_hotels" in hotels
    assert "search_hotels" not in tv


def test_get_unknown_tool_returns_error_outcome() -> None:
    """Looking up an unknown tool by name returns a KeyError on get_tool,
    but invoke_tool wraps the miss into a ``kind="error"`` outcome."""
    import asyncio

    from voyagent_agent_runtime.tools import InMemoryAuditSink

    async def _go() -> None:
        from schemas.canonical import ActorKind

        ctx = ToolContext(
            tenant_id="01900000-0000-7000-8000-000000000001",
            actor_id="01900000-0000-7000-8000-000000000002",
            actor_kind=ActorKind.HUMAN,
            session_id="01900000-0000-7000-8000-000000000003",
            turn_id="t-not-a-tool",
            approvals={},
            extensions={},
        )
        sink = InMemoryAuditSink()
        outcome = await invoke_tool(
            "this_tool_does_not_exist", {}, ctx, audit_sink=sink
        )
        assert outcome.kind == "error"
        assert "this_tool_does_not_exist" in (outcome.error_message or "")
        # No audit is written for a missing tool (short-circuits before
        # side-effect gate).
        assert sink.events == []

    asyncio.run(_go())


async def test_raising_read_only_handler_is_wrapped_as_error(
    tool_context: ToolContext,
) -> None:
    """A read-only tool that raises should not crash the runtime: invoke_tool
    must trap and return ``kind="error"``. Read-only tools don't produce
    audit events, so the sink stays empty."""
    sink = InMemoryAuditSink()

    async def _explode(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        raise RuntimeError("readonly boom")

    register_tool(
        ToolSpec(
            name="_test_readonly_explode",
            description="Read-only tool that raises.",
            input_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            side_effect=False,
            reversible=True,
            approval_required=False,
            domain="cross_cutting",
        ),
        _explode,
    )

    outcome = await invoke_tool(
        "_test_readonly_explode", {}, tool_context, audit_sink=sink
    )
    assert outcome.kind == "error"
    assert "readonly boom" in (outcome.error_message or "")
    # No audit for a read-only tool.
    assert sink.events == []
