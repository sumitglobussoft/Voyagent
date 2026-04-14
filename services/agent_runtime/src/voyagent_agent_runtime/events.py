"""The canonical agent event stream.

Every public surface of the agent runtime — orchestrator, domain agents,
tool runner — emits :class:`AgentEvent` values. The API service relays
these events out to clients over Server-Sent Events.

The stream is deliberately narrow: one discriminated kind per event, with
kind-specific fields. Strict validation keeps every producer honest.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.canonical import EntityId


class AgentEventKind(StrEnum):
    """Discriminator for :class:`AgentEvent`."""

    TEXT_DELTA = "text_delta"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    ERROR = "error"
    FINAL = "final"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentEvent(BaseModel):
    """One event in the runtime's public stream.

    The :attr:`kind` determines which payload fields are required. A
    validator rejects events that drop required fields or carry fields
    that don't belong to the selected kind.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    kind: AgentEventKind
    session_id: EntityId
    turn_id: str = Field(min_length=1, description="Per-turn correlation id.")
    timestamp: datetime = Field(default_factory=_utcnow)

    # kind-specific payload
    text: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: dict[str, Any] | None = None
    tool_call_id: str | None = None
    approval_id: str | None = None
    approval_summary: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> AgentEvent:
        """Validate that required fields are populated for this kind."""
        k = self.kind
        if k is AgentEventKind.TEXT_DELTA:
            if self.text is None:
                raise ValueError("TEXT_DELTA events require `text`.")
        elif k is AgentEventKind.TOOL_USE:
            if not (self.tool_name and self.tool_call_id and self.tool_input is not None):
                raise ValueError(
                    "TOOL_USE events require `tool_name`, `tool_call_id`, `tool_input`."
                )
        elif k is AgentEventKind.TOOL_RESULT:
            if not (self.tool_name and self.tool_call_id and self.tool_output is not None):
                raise ValueError(
                    "TOOL_RESULT events require `tool_name`, `tool_call_id`, `tool_output`."
                )
        elif k is AgentEventKind.APPROVAL_REQUEST:
            if not (self.approval_id and self.approval_summary):
                raise ValueError(
                    "APPROVAL_REQUEST events require `approval_id` and `approval_summary`."
                )
        elif k in (AgentEventKind.APPROVAL_GRANTED, AgentEventKind.APPROVAL_DENIED):
            if not self.approval_id:
                raise ValueError(f"{k.value} events require `approval_id`.")
        elif k is AgentEventKind.ERROR:
            if not self.error_message:
                raise ValueError("ERROR events require `error_message`.")
        # FINAL: no required payload.
        return self


__all__ = ["AgentEvent", "AgentEventKind"]
