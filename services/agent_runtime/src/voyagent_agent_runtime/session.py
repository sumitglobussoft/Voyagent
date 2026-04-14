"""Session state — conversation history and pending approvals.

The v0 implementation is in-memory only. A Postgres-backed
:class:`SessionStore` lands when the persistence story is finalized.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from schemas.canonical import ActorKind, EntityId

# Maximum per-session SSE replay buffer. Sized for long-running turns
# that can emit tool_use / tool_result / text_delta events in the
# hundreds; 200 entries fits a typical 8-tool turn with comfortable
# headroom.
SSE_REPLAY_BUFFER_CAP: int = 200


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
    async def add_approval(self, session_id: EntityId, ap: PendingApproval) -> None: ...
    async def resolve_approval(
        self, session_id: EntityId, approval_id: str, granted: bool
    ) -> None: ...


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

    async def add_approval(self, session_id: EntityId, ap: PendingApproval) -> None:
        sess = self._sessions[session_id]
        sess.pending_approvals = {**sess.pending_approvals, ap.id: ap}
        sess.updated_at = _utcnow()

    async def resolve_approval(
        self, session_id: EntityId, approval_id: str, granted: bool
    ) -> None:
        sess = self._sessions[session_id]
        existing = sess.pending_approvals.get(approval_id)
        if existing is None:
            raise KeyError(f"No pending approval {approval_id!r} on session {session_id!r}.")
        updated = existing.model_copy(
            update={"granted": granted, "resolved_at": _utcnow()}
        )
        sess.pending_approvals = {**sess.pending_approvals, approval_id: updated}
        sess.updated_at = _utcnow()


__all__ = [
    "InMemorySessionStore",
    "Message",
    "PendingApproval",
    "SSE_REPLAY_BUFFER_CAP",
    "Session",
    "SessionStore",
]
