# voyagent-agent-runtime

The Voyagent agent runtime — a thin orchestrator + a small set of
domain agents + a rich canonical tool set. Turns user messages into
ordered tool calls that drive the real world through drivers.

## What lives here

- `orchestrator.py` — per-turn router. Calls Anthropic with
  `handoff` + `clarify` tools, routes to the right domain agent, and
  streams `AgentEvent` values.
- `domain_agents/ticketing_visa.py` — flights / PNRs / tickets /
  visa specialist. Owns `search_flights`, `read_pnr`, `issue_ticket`.
- `tools.py` — tool registry, JSON-schema validation, side-effect
  gating, audit writes. Tools are declared with `@tool(...)`.
- `drivers.py` — runtime `DriverRegistry`, keyed by capability
  protocol (`FareSearchDriver`, `PNRDriver`, ...).
- `anthropic_client.py` — async wrapper around `AsyncAnthropic` with
  prompt caching on the system prompt + the tools array.
- `session.py` — in-memory `Session` + `SessionStore` for v0.
- `events.py` — the `AgentEvent` stream the API relays to clients.
- `prompts.py` — orchestrator + domain-agent system prompts.
- `cli.py` — a terminal REPL for manual smoke-testing.

## Running the terminal chat

```sh
export ANTHROPIC_API_KEY=sk-ant-...
export VOYAGENT_AMADEUS_CLIENT_ID=...
export VOYAGENT_AMADEUS_CLIENT_SECRET=...
# Optional:
export VOYAGENT_AGENT_MODEL=claude-sonnet-4-5   # default

uv run voyagent-agent-runtime chat
```

Type a message (e.g. "I need a fare from DEL to DXB on 2026-05-10 for
two adults"). The REPL prints streaming text deltas, `[tool_use]` /
`[tool_result]` lines as tools fire, and `[approval_request]` prompts
for side-effect tools.

## Tool registry pattern

A tool is a Pydantic-described spec + an async handler. Register with
the decorator:

```python
@tool(
    name="search_flights",
    description="Shop for fares. Read-only.",
    domain="ticketing_visa",
    input_schema=SEARCH_FLIGHTS_SCHEMA,
    side_effect=False,
)
async def search_flights(tool_input, ctx):
    ...
```

Handlers receive validated `tool_input` and a `ToolContext`. The context
carries `tenant_id` / `actor_id` / `session_id` / `turn_id`, the
`approvals` map, and `extensions` — where the `DriverRegistry` is
injected. Invocation is centralised in `invoke_tool(...)` which:

1. JSON-schema-validates the input.
2. If `side_effect + approval_required` and no approval in the context,
   returns `kind="approval_needed"` with a stable `approval_id`.
3. Otherwise writes an `AuditEvent` (STARTED), runs the handler, and
   closes the audit with SUCCEEDED / FAILED.

## How approval gating works

Side-effect tools with `approval_required=True` short-circuit on first
call. The orchestrator yields an `AgentEvent(kind=APPROVAL_REQUEST, ...)`
and the turn ends. The API surfaces the summary to a human; their
response populates the `approvals` map on the next `run_turn` call. When
the same tool fires again it sees `approvals[approval_id] == True` and
executes, emitting a full `AuditEvent` with `approved_by` + `approved_at`.

Denied approvals write an `AuditEvent` with `status=REJECTED`.

## Adding a new domain agent

1. Pick a domain key (`"hotels_holidays"` or a fresh one).
2. Add `<DOMAIN>_SYSTEM_PROMPT` to `prompts.py`.
3. Register the domain's tools with `@tool(..., domain=<key>)` in
   `tools.py`. Keep responses compact — tool outputs are charged tokens.
4. Implement a new class in `domain_agents/<domain>.py` that mirrors
   `TicketingVisaAgent`: set `name`, `system_prompt`, `tools`, and
   implement `async def run(request) -> AsyncIterator[AgentEvent]`.
5. Teach the CLI / API's `handoff_resolver` about the new agent.

## Audit events

Every `side_effect=True` tool invocation writes a canonical
`AuditEvent` (`schemas.canonical.AuditEvent`) through an `AuditSink`.
v0 ships `InMemoryAuditSink`. A Postgres sink lands when persistence
does.

## The AgentEvent stream

`Orchestrator.run_turn` returns `AsyncIterator[AgentEvent]`. Every
event is Pydantic-validated; every turn ends with exactly one
`kind=FINAL` event. The API service wraps this stream as SSE:

```
event: text_delta   { "text": "Searching fares..." }
event: tool_use     { "tool_name": "search_flights", ... }
event: tool_result  { "tool_name": "search_flights", "tool_output": {...} }
event: final        { }
```

Kinds: `text_delta`, `tool_use`, `tool_result`, `approval_request`,
`approval_granted`, `approval_denied`, `error`, `final`.

## Status

v0. In-memory sessions, in-memory audit, one domain agent, Anthropic
Sonnet 4.5 by default. Persistence, multi-tenant isolation, and the
hotels/accounting domains arrive after this slice proves out.
