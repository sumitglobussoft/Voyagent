"""Session state — conversation history and pending approvals.

The v0 implementation is in-memory only. A Postgres-backed
:class:`SessionStore` lands when the persistence story is finalized.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from schemas.canonical import ActorKind, EntityId

# Maximum per-session SSE replay buffer. Sized for long-running turns
# that can emit tool_use / tool_result / text_delta events in the
# hundreds; 200 entries fits a typical 8-tool turn with comfortable
# headroom.
SSE_REPLAY_BUFFER_CAP: int = 200

# Default lifetime of a PendingApproval before it auto-expires. Tools
# may override per-call via ``approval_ttl_seconds``.
DEFAULT_APPROVAL_TTL_SECONDS: int = 15 * 60


ApprovalStatus = Literal["pending", "granted", "rejected", "expired"]


class CrossTenantApprovalError(PermissionError):
    """Raised when an actor from tenant A attempts to resolve an approval
    that belongs to tenant B. Subclasses ``PermissionError`` so existing
    HTTP-layer catches that map ``PermissionError`` to 403 keep working."""


def _runtime_config() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Message(BaseModel):
    """One message in the Anthropic-shaped transcript.

    ``content`` is a list of content blocks — ``{"type": "text", "text": ...}``
    for user/assistant text, and tool-use / tool-result blocks for
    intermediate turns. See Anthropic's SDK docs for the full shape.
    """

    model_config = _runtime_config()

    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: list[dict[str, Any]]


class PendingApproval(BaseModel):
    """An approval the runtime is waiting on a human to resolve."""

    model_config = _runtime_config()

    id: str
    tool_name: str
    summary: str
    turn_id: str
    requested_at: datetime = Field(default_factory=_utcnow)
    granted: bool | None = None
    resolved_at: datetime | None = None
    # Populated from requested_at + TTL when the approval is minted. Left
    # Optional on the model itself to keep migrations painless for rows
    # already in flight; the store guarantees a value on every new row.
    expires_at: datetime | None = None
    status: ApprovalStatus = "pending"


class Session(BaseModel):
    """In-process conversation state.

    ``message_history`` is append-only within a session; approvals can
    be overwritten when a human resolves them.
    """

    model_config = _runtime_config()

    id: EntityId
    tenant_id: EntityId
    actor_id: EntityId
    actor_kind: ActorKind = ActorKind.HUMAN
    message_history: list[Message] = Field(default_factory=list)
    pending_approvals: dict[str, PendingApproval] = Field(default_factory=dict)
    # Monotonic per-session counter for SSE frame ids. Incremented every
    # time the chat stream emits an ``agent_event`` frame so reconnecting
    # clients can resume via the ``Last-Event-ID`` header. Not persisted
    # to Postgres in v0 — it lives on the in-process Session only.
    sse_last_event_id: int = 0
    # Rolling buffer of recently-emitted SSE frames for replay on
    # reconnect. Each entry is ``(event_id, payload_json)``. Capped at
    # :data:`SSE_REPLAY_BUFFER_CAP` — older frames are dropped. Also
    # non-persistent.
    sse_event_buffer: list[tuple[int, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def approvals_map(self) -> dict[str, bool]:
        """Return ``{approval_id: granted}`` for every resolved approval."""
        return {
            ap_id: ap.granted
            for ap_id, ap in self.pending_approvals.items()
            if ap.granted is not None
        }


class SessionStore(Protocol):
    """Session persistence surface. In-memory impl below; Postgres later."""

    async def get(self, session_id: EntityId) -> Session | None: ...
    async def put(self, session: Session) -> None: ...
    async def append_message(self, session_id: EntityId, msg: Message) -> None: ...
    async def add_approval(
        self,
        session_id: EntityId,
        ap: PendingApproval,
        *,
        approval_ttl_seconds: int | None = None,
    ) -> None: ...
    async def resolve_approval(
        self,
        session_id: EntityId,
        approval_id: str,
        granted: bool,
        *,
        actor_tenant_id: EntityId | None = None,
    ) -> None: ...
    async def expire_stale_approvals(
        self, session_id: EntityId | None = None, *, now: datetime | None = None
    ) -> int: ...


class InMemorySessionStore:
    """Non-persistent :class:`SessionStore` for v0 and tests."""

    def __init__(self) -> None:
        self._sessions: dict[EntityId, Session] = {}

    async def get(self, session_id: EntityId) -> Session | None:
        return self._sessions.get(session_id)

    async def put(self, session: Session) -> None:
        self._sessions[session.id] = session

    async def append_message(self, session_id: EntityId, msg: Message) -> None:
        sess = self._sessions[session_id]
        sess.message_history = [*sess.message_history, msg]
        sess.updated_at = _utcnow()

    async def add_approval(
        self,
        session_id: EntityId,
        ap: PendingApproval,
        *,
        approval_ttl_seconds: int | None = None,
    ) -> None:
        sess = self._sessions[session_id]
        # Stamp expires_at if the caller didn't supply one. We compute off
        # requested_at (not "now") so backfilled rows have a deterministic
        # TTL even when their requested_at is in the past.
        if ap.expires_at is None:
            ttl = (
                approval_ttl_seconds
                if approval_ttl_seconds is not None
                else DEFAULT_APPROVAL_TTL_SECONDS
            )
            ap = ap.model_copy(
                update={"expires_at": ap.requested_at + timedelta(seconds=ttl)}
            )
        sess.pending_approvals = {**sess.pending_approvals, ap.id: ap}
        sess.updated_at = _utcnow()

    async def resolve_approval(
        self,
        session_id: EntityId,
        approval_id: str,
        granted: bool,
        *,
        actor_tenant_id: EntityId | None = None,
    ) -> None:
        sess = self._sessions[session_id]
        # Cross-tenant guard: an approval is scoped to the session's
        # tenant. Callers that know their tenant MUST pass it; callers
        # that omit it are trusted internal code (backfills, expiry
        # sweeps) where the check is redundant.
        if actor_tenant_id is not None and sess.tenant_id != actor_tenant_id:
            raise CrossTenantApprovalError(
                f"actor tenant {actor_tenant_id!r} cannot resolve approval "
                f"owned by tenant {sess.tenant_id!r}."
            )
        existing = sess.pending_approvals.get(approval_id)
        if existing is None:
            raise KeyError(f"No pending approval {approval_id!r} on session {session_id!r}.")
        updated = existing.model_copy(
            update={
                "granted": granted,
                "resolved_at": _utcnow(),
                "status": "granted" if granted else "rejected",
            }
        )
        sess.pending_approvals = {**sess.pending_approvals, approval_id: updated}
        sess.updated_at = _utcnow()

    async def expire_stale_approvals(
        self,
        session_id: EntityId | None = None,
        *,
        now: datetime | None = None,
    ) -> int:
        """Transition pending approvals past their expires_at to ``expired``.

        Returns the number of rows flipped. Orchestrator calls this
        lazily before reading approvals so there's no background sweeper.
        ``session_id=None`` sweeps every session in the store.
        """
        ts = now or _utcnow()
        targets = (
            [self._sessions[session_id]]
            if session_id is not None and session_id in self._sessions
            else list(self._sessions.values())
        )
        flipped = 0
        for sess in targets:
            new_map = dict(sess.pending_approvals)
            touched = False
            for ap_id, ap in sess.pending_approvals.items():
                if ap.status != "pending":
                    continue
                if ap.expires_at is None:
                    continue
                if ap.expires_at <= ts:
                    new_map[ap_id] = ap.model_copy(update={"status": "expired"})
                    flipped += 1
                    touched = True
            if touched:
                sess.pending_approvals = new_map
                sess.updated_at = _utcnow()
        return flipped


__all__ = [
    "ApprovalStatus",
    "CrossTenantApprovalError",
    "DEFAULT_APPROVAL_TTL_SECONDS",
    "InMemorySessionStore",
    "Message",
    "PendingApproval",
    "SSE_REPLAY_BUFFER_CAP",
    "Session",
    "SessionStore",
]
