"""Voyagent agent runtime — orchestrator, domain agents, tool runtime.

The runtime is the "agentic" layer of Voyagent: it turns a user message
into an orchestrated sequence of canonical tool calls that eventually
drive real external systems through drivers.
"""

from __future__ import annotations

from .anthropic_client import AnthropicClient, Settings
from .domain_agents import DomainAgent, DomainAgentRequest, TicketingVisaAgent
from .drivers import DriverRegistry, build_default_registry
from .events import AgentEvent, AgentEventKind
from .orchestrator import HandoffResolver, Orchestrator
from .passenger_resolver import (
    InMemoryPassengerResolver,
    PASSENGER_RESOLVER_KEY,
    StoragePassengerResolver,
    build_passenger_resolver,
)
from .tenant_registry import (
    CredentialResolver,
    EnvCredentialResolver,
    StorageCredentialResolver,
    TENANT_REGISTRY_KEY,
    TenantRegistry,
    default_credential_resolver,
)
from .runtime import (
    DefaultRuntime,
    build_default_runtime,
    coerce_entity_id,
    get_default_runtime,
    new_session_id,
)
from .session import (
    InMemorySessionStore,
    Message,
    PendingApproval,
    SSE_REPLAY_BUFFER_CAP,
    Session,
    SessionStore,
)
from .tools import (
    AuditSink,
    InMemoryAuditSink,
    Tool,
    ToolContext,
    ToolInvocationOutcome,
    ToolSpec,
    anthropic_tool_defs,
    get_tool,
    invoke_tool,
    list_tools,
    register_tool,
    tool,
)

__all__ = [
    "AgentEvent",
    "AgentEventKind",
    "AnthropicClient",
    "AuditSink",
    "CredentialResolver",
    "DefaultRuntime",
    "DomainAgent",
    "DomainAgentRequest",
    "DriverRegistry",
    "EnvCredentialResolver",
    "HandoffResolver",
    "StorageCredentialResolver",
    "TENANT_REGISTRY_KEY",
    "TenantRegistry",
    "default_credential_resolver",
    "InMemoryAuditSink",
    "InMemoryPassengerResolver",
    "InMemorySessionStore",
    "Message",
    "Orchestrator",
    "PASSENGER_RESOLVER_KEY",
    "PendingApproval",
    "StoragePassengerResolver",
    "build_passenger_resolver",
    "SSE_REPLAY_BUFFER_CAP",
    "Session",
    "SessionStore",
    "Settings",
    "TicketingVisaAgent",
    "Tool",
    "ToolContext",
    "ToolInvocationOutcome",
    "ToolSpec",
    "anthropic_tool_defs",
    "build_default_registry",
    "build_default_runtime",
    "coerce_entity_id",
    "get_default_runtime",
    "get_tool",
    "invoke_tool",
    "list_tools",
    "new_session_id",
    "register_tool",
    "tool",
]
