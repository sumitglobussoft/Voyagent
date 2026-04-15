"""Pending-approval flow tests.

Covers two failure modes that are not currently asserted elsewhere:

  * A pending approval that times out — the tool call should be marked
    ``expired`` and the agent should receive a timeout result instead
    of a stale ``approval_needed`` outcome.
  * An approval resolved by a user from a different tenant — the
    resolution must be rejected and the original approval must stay
    pending.

Both behaviours require session-store changes that the in-memory
:class:`InMemorySessionStore` does not yet implement. The tests are
marked ``xfail(strict=False)`` with a specific reason so the gap is
visible in CI output.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from schemas.canonical import ActorKind
from voyagent_agent_runtime.session import (
    InMemorySessionStore,
    PendingApproval,
    Session,
)
from voyagent_agent_runtime.tools import (
    InMemoryAuditSink,
    ToolContext,
    invoke_tool,
)


pytestmark = pytest.mark.asyncio


def _new_uuid7_like() -> str:
    import uuid

    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


async def _seed_session_with_pending(
    store: InMemorySessionStore,
    *,
    tenant_id: str,
) -> tuple[Session, str]:
    sess = Session(
        id=_new_uuid7_like(),
        tenant_id=tenant_id,
        actor_id=_new_uuid7_like(),
        actor_kind=ActorKind.HUMAN,
    )
    await store.put(sess)
    ap = PendingApproval(
        id="ap-timeout-xyz",
        tool_name="issue_ticket",
        summary="Issue ticket for PNR-42",
        turn_id="t-testturn0001",
        requested_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    await store.add_approval(sess.id, ap)
    return sess, ap.id


# --------------------------------------------------------------------------- #
# 1. Approval timeout                                                         #
# --------------------------------------------------------------------------- #


async def test_pending_approval_timeout_marks_expired_and_returns_timeout_result() -> None:
    tenant_id = _new_uuid7_like()
    store = InMemorySessionStore()
    sess, approval_id = await _seed_session_with_pending(store, tenant_id=tenant_id)

    expire_stale = getattr(store, "expire_stale_approvals", None)
    assert expire_stale is not None, "InMemorySessionStore.expire_stale_approvals missing"
    n_expired = await expire_stale(
        now=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    assert n_expired == 1

    refreshed = await store.get(sess.id)
    assert refreshed is not None
    ap = refreshed.pending_approvals[approval_id]
    assert getattr(ap, "granted", None) is None
    assert getattr(ap, "status", None) == "expired"

    # Re-running the sweep with no new stale rows must be a no-op.
    n_second = await expire_stale(
        now=datetime.now(timezone.utc) + timedelta(hours=2)
    )
    assert n_second == 0

    # A fresh pending approval seeded AFTER the sweep is not flipped
    # until its own expires_at passes.
    from voyagent_agent_runtime.session import PendingApproval

    now = datetime.now(timezone.utc)
    fresh = PendingApproval(
        id="ap-fresh-xyz",
        tool_name="issue_ticket",
        summary="Issue fresh ticket",
        turn_id="t-fresh000",
        requested_at=now,
    )
    await store.add_approval(sess.id, fresh)
    n_third = await expire_stale(now=now + timedelta(minutes=1))
    assert n_third == 0
    refreshed = await store.get(sess.id)
    assert refreshed is not None
    assert refreshed.pending_approvals["ap-fresh-xyz"].status == "pending"


# --------------------------------------------------------------------------- #
# 2. Cross-tenant approval resolution                                         #
# --------------------------------------------------------------------------- #


async def test_cross_tenant_approval_resolution_is_rejected_and_stays_pending() -> None:
    from voyagent_agent_runtime.session import CrossTenantApprovalError

    owner_tenant = _new_uuid7_like()
    foreign_tenant = _new_uuid7_like()
    store = InMemorySessionStore()
    sess, approval_id = await _seed_session_with_pending(store, tenant_id=owner_tenant)

    # A foreign tenant cannot resolve an approval scoped to another.
    with pytest.raises(CrossTenantApprovalError):
        await store.resolve_approval(
            sess.id,
            approval_id,
            True,
            actor_tenant_id=foreign_tenant,
        )

    refreshed = await store.get(sess.id)
    assert refreshed is not None
    ap = refreshed.pending_approvals[approval_id]
    # The approval is still un-resolved.
    assert ap.granted is None
    assert ap.resolved_at is None
    assert ap.status == "pending"

    # CrossTenantApprovalError must be a PermissionError subclass so the
    # HTTP layer's existing 403 mapping works without changes.
    assert issubclass(CrossTenantApprovalError, PermissionError)

    # The legitimate owner can still resolve it.
    await store.resolve_approval(
        sess.id, approval_id, True, actor_tenant_id=owner_tenant
    )
    refreshed = await store.get(sess.id)
    assert refreshed is not None
    ap = refreshed.pending_approvals[approval_id]
    assert ap.granted is True
    assert ap.status == "granted"


# --------------------------------------------------------------------------- #
# 3. A concrete approval-flow invariant that DOES hold today                  #
# --------------------------------------------------------------------------- #


async def test_approval_granted_then_revoked_replay_short_circuits(
    tool_context: ToolContext,
) -> None:
    """If an approval is granted and the tool runs, a second invocation
    with a fresh approval requirement must not accidentally reuse the
    prior approval id — each call re-requests its own approval."""
    sink = InMemoryAuditSink()

    first = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR-RESEAT"}, tool_context, audit_sink=sink
    )
    assert first.kind == "approval_needed"
    first_id = first.approval_id

    # Grant and execute.
    tool_context.approvals = {first_id: True}
    second = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR-RESEAT"}, tool_context, audit_sink=sink
    )
    assert second.kind == "success"

    # A fresh call with cleared approvals re-requests approval.
    # contract changed — approval ids are now deterministic in (turn_id, tool_name)
    # (see tools._approval_id_for: "Stable approval id so the same tool call in
    # a retry keeps the id"), so a same-turn re-invocation reuses the id. The
    # invariant this test actually needs is that a cleared approval map
    # short-circuits back to ``approval_needed`` rather than silently running.
    tool_context.approvals = {}
    third = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR-RESEAT"}, tool_context, audit_sink=sink
    )
    assert third.kind == "approval_needed"
    assert third.approval_id == first_id
