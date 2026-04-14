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


@pytest.mark.xfail(
    reason=(
        "InMemorySessionStore does not yet support approval expiry: "
        "PendingApproval has no TTL / expires_at and resolve_approval "
        "never transitions to 'expired'. A test that fast-forwards the "
        "clock cannot detect the timeout until the store grows a "
        "sweeper. Once the contract exists this test should pass by "
        "calling a new ``store.expire_stale_approvals(now)`` helper."
    ),
    strict=False,
)
async def test_pending_approval_timeout_marks_expired_and_returns_timeout_result() -> None:
    tenant_id = _new_uuid7_like()
    store = InMemorySessionStore()
    sess, approval_id = await _seed_session_with_pending(store, tenant_id=tenant_id)

    # Forward-looking API — does not exist yet.
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


# --------------------------------------------------------------------------- #
# 2. Cross-tenant approval resolution                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    reason=(
        "InMemorySessionStore.resolve_approval does not accept a "
        "'resolver tenant' argument and therefore cannot reject a "
        "cross-tenant attempt. Once the store signature grows an "
        "``actor_tenant_id`` check this test should pass by calling "
        "``store.resolve_approval(..., actor_tenant_id=other_tenant)`` "
        "and expecting a PermissionError / 403 from the caller."
    ),
    strict=False,
)
async def test_cross_tenant_approval_resolution_is_rejected_and_stays_pending() -> None:
    owner_tenant = _new_uuid7_like()
    foreign_tenant = _new_uuid7_like()
    store = InMemorySessionStore()
    sess, approval_id = await _seed_session_with_pending(store, tenant_id=owner_tenant)

    # Forward-looking: store.resolve_approval should take an actor_tenant_id
    # argument and reject resolution if it does not match sess.tenant_id.
    with pytest.raises(PermissionError):
        await store.resolve_approval(
            sess.id,
            approval_id,
            True,
            actor_tenant_id=foreign_tenant,  # type: ignore[call-arg]
        )

    refreshed = await store.get(sess.id)
    assert refreshed is not None
    ap = refreshed.pending_approvals[approval_id]
    # The approval is still un-resolved.
    assert ap.granted is None
    assert ap.resolved_at is None


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

    # A fresh call with cleared approvals must request a new approval id,
    # not silently re-use the old one.
    tool_context.approvals = {}
    third = await invoke_tool(
        "issue_ticket", {"pnr_id": "PNR-RESEAT"}, tool_context, audit_sink=sink
    )
    assert third.kind == "approval_needed"
    assert third.approval_id != first_id
