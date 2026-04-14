"""Domain agents — thin specialists fronted by the orchestrator.

Each domain agent opens its own Anthropic stream with a domain-scoped
system prompt and tool subset. They share the same event-streaming and
approval-gating shape as the orchestrator.
"""

from __future__ import annotations

from .base import DomainAgent, DomainAgentRequest
from .ticketing_visa import TicketingVisaAgent

__all__ = ["DomainAgent", "DomainAgentRequest", "TicketingVisaAgent"]
