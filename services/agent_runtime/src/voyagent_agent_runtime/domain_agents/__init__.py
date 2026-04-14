"""Domain agents — thin specialists fronted by the orchestrator.

Each domain agent opens its own Anthropic stream with a domain-scoped
system prompt and tool subset. They share the same event-streaming and
approval-gating shape as the orchestrator.
"""

from __future__ import annotations

from .accounting import AccountingAgent
from .base import DomainAgent, DomainAgentRequest
from .hotels_holidays import HotelsHolidaysAgent
from .ticketing_visa import TicketingVisaAgent

__all__ = [
    "AccountingAgent",
    "DomainAgent",
    "DomainAgentRequest",
    "HotelsHolidaysAgent",
    "TicketingVisaAgent",
]
