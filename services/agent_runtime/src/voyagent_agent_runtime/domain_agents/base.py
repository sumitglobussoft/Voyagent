"""Protocol + request shape shared by every domain agent."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..events import AgentEvent
from ..session import Session
from ..tools import ToolContext


class DomainAgentRequest(BaseModel):
    """Bundle of inputs a domain agent needs for one handoff."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    session: Session
    goal: str = Field(min_length=1)
    user_message: str
    tool_context: ToolContext


class DomainAgent(Protocol):
    """Every domain agent streams :class:`AgentEvent` over one handoff."""

    name: str
    system_prompt: str
    tools: list[str]

    def run(self, request: DomainAgentRequest) -> AsyncIterator[AgentEvent]: ...


__all__ = ["DomainAgent", "DomainAgentRequest"]
