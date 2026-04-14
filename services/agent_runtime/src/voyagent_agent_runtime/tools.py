"""Tool registry, side-effect gating, and audit.

This module holds the canonical tool set for the Voyagent runtime. Every
tool has a declared :class:`ToolSpec` (name, JSON schema, side-effect
flags) and an async handler. The orchestrator and domain agents never
touch drivers directly — they invoke tools through :func:`invoke_tool`,
which validates input, enforces approval gating, runs the handler, and
writes an :class:`AuditEvent` when the tool has side effects.
"""

from __future__ import annotations

import inspect
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Literal, Protocol

import jsonschema
from pydantic import BaseModel, ConfigDict, Field

from drivers._contracts.errors import CapabilityNotSupportedError, DriverError
from drivers._contracts.fare_search import FareSearchCriteria
from schemas.canonical import (
    ActorKind,
    AuditEvent,
    AuditStatus,
    CabinClass,
    EntityId,
    PassengerType,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Model config                                                                #
# --------------------------------------------------------------------------- #


def _runtime_config() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )


ToolDomain = Literal["ticketing_visa", "hotels_holidays", "accounting", "cross_cutting"]


# --------------------------------------------------------------------------- #
# Public models                                                               #
# --------------------------------------------------------------------------- #


class ToolSpec(BaseModel):
    """Static metadata about a tool. Paired with a handler in :class:`Tool`."""

    model_config = _runtime_config()

    name: str = Field(min_length=1)
    description: str
    input_schema: dict[str, Any] = Field(
        description="JSON Schema (draft 2020-12) describing tool input."
    )
    side_effect: bool = False
    reversible: bool = True
    approval_required: bool = False
    approval_roles: list[str] = Field(default_factory=list)
    domain: ToolDomain


class ToolContext(BaseModel):
    """Per-turn call context passed into every handler.

    ``approvals`` is a map of approval_id → granted. A tool that needs
    approval inspects this map before executing. ``extensions`` carries
    dependency-injected infrastructure (driver registry, clocks, etc.)
    so tests can swap fakes without monkey-patching.
    """

    model_config = _runtime_config()

    tenant_id: EntityId
    actor_id: EntityId
    actor_kind: ActorKind
    session_id: EntityId
    turn_id: str
    approvals: dict[str, bool] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationOutcome(BaseModel):
    """Result of a single :func:`invoke_tool` call.

    ``kind`` distinguishes successful execution, an input/runtime error,
    and "approval needed" — the last short-circuits execution and asks
    the orchestrator to surface a human decision.
    """

    model_config = _runtime_config()

    kind: Literal["success", "error", "approval_needed"]
    output: dict[str, Any] | None = None
    error_message: str | None = None
    approval_id: str | None = None
    approval_summary: str | None = None
    audit_id: EntityId | None = None


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]


class Tool(BaseModel):
    """Spec + handler bundle living in the registry."""

    model_config = _runtime_config()

    spec: ToolSpec
    handler: ToolHandler


# --------------------------------------------------------------------------- #
# Audit sink                                                                  #
# --------------------------------------------------------------------------- #


class AuditSink(Protocol):
    """Append-only sink for :class:`AuditEvent`. Implementations must be
    safe to call from multiple concurrent handlers."""

    async def write(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Non-persistent audit sink for v0 and tests."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    async def write(self, event: AuditEvent) -> None:
        self._events.append(event.model_copy(deep=True))

    @property
    def events(self) -> list[AuditEvent]:
        """Return a snapshot of recorded events (read-only copy)."""
        return list(self._events)


# --------------------------------------------------------------------------- #
# Registry                                                                    #
# --------------------------------------------------------------------------- #


_REGISTRY: dict[str, Tool] = {}


def register_tool(spec: ToolSpec, handler: ToolHandler) -> None:
    """Register a tool. Raises if the name is already taken."""
    if spec.name in _REGISTRY:
        raise ValueError(f"Tool {spec.name!r} is already registered.")
    _REGISTRY[spec.name] = Tool(spec=spec, handler=handler)


def clear_registry() -> None:
    """Wipe the registry. Tests use this to isolate state."""
    _REGISTRY.clear()


def tool(
    *,
    name: str,
    description: str,
    domain: ToolDomain,
    input_schema: dict[str, Any] | None = None,
    input_model: type[BaseModel] | None = None,
    side_effect: bool = False,
    reversible: bool = True,
    approval_required: bool = False,
    approval_roles: list[str] | None = None,
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator that registers an async handler as a tool.

    Either ``input_schema`` (raw JSON Schema) or ``input_model`` (a
    Pydantic BaseModel class whose ``.model_json_schema()`` is used) must
    be provided. The decorator returns the original function so it can
    still be called directly from tests.
    """

    def _decorator(func: ToolHandler) -> ToolHandler:
        if input_schema is None and input_model is None:
            raise ValueError(f"Tool {name!r}: supply input_schema or input_model.")
        schema = input_schema or input_model.model_json_schema()  # type: ignore[union-attr]
        spec = ToolSpec(
            name=name,
            description=description,
            input_schema=schema,
            side_effect=side_effect,
            reversible=reversible,
            approval_required=approval_required,
            approval_roles=list(approval_roles or []),
            domain=domain,
        )
        register_tool(spec, func)
        return func

    return _decorator


def get_tool(name: str) -> Tool:
    """Return the registered tool by name. Raises ``KeyError`` if unknown."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"No tool registered as {name!r}.") from exc


def list_tools(domain: ToolDomain | None = None) -> list[Tool]:
    """Return all registered tools, optionally filtered by domain."""
    if domain is None:
        return list(_REGISTRY.values())
    return [t for t in _REGISTRY.values() if t.spec.domain == domain]


def anthropic_tool_defs(
    domain: ToolDomain | None = None,
    *,
    names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Produce the tool-definition payload the Anthropic SDK expects.

    Each entry is ``{name, description, input_schema}``. Use ``names`` to
    scope the output to a specific subset (e.g. one domain agent's
    tools) when ``domain`` alone is not enough.
    """
    if names is not None:
        wanted = {n: _REGISTRY[n] for n in names if n in _REGISTRY}
        source = list(wanted.values())
    else:
        source = list_tools(domain)
    return [
        {
            "name": t.spec.name,
            "description": t.spec.description,
            "input_schema": t.spec.input_schema,
        }
        for t in source
    ]


# --------------------------------------------------------------------------- #
# Invocation runner                                                           #
# --------------------------------------------------------------------------- #


def _uuid7_like() -> str:
    """Produce a UUIDv7-shaped string suitable for ``EntityId``."""
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def _approval_id_for(turn_id: str, tool_name: str) -> str:
    """Stable approval id so the same tool call in a retry keeps the id."""
    return f"ap-{turn_id}-{tool_name}"


def _summary_for(tool_name: str, tool_input: dict[str, Any]) -> str:
    """One short sentence describing what the tool would do. Conservative."""
    brief = ", ".join(f"{k}={v!r}" for k, v in list(tool_input.items())[:3])
    return f"Approve tool `{tool_name}` with {brief}?"


async def _run_handler(
    handler: ToolHandler, tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Call the handler, awaiting if it returns a coroutine. The decorator
    contract already requires an async def, but we defend against sync
    test doubles slipping through."""
    result = handler(tool_input, ctx)
    if inspect.isawaitable(result):
        return await result
    return result  # type: ignore[return-value]


async def invoke_tool(
    name: str,
    tool_input: dict[str, Any],
    ctx: ToolContext,
    *,
    audit_sink: AuditSink,
) -> ToolInvocationOutcome:
    """Validate, gate, execute, and audit a single tool call.

    Behaviour:
      1. JSON-schema validate ``tool_input`` against the spec.
      2. If side_effect + approval_required and no prior approval, return
         ``kind="approval_needed"`` without executing.
      3. Open an AuditEvent (STARTED), run the handler, close the event
         with SUCCEEDED / FAILED, and return the outcome.
    """
    try:
        entry = get_tool(name)
    except KeyError as exc:
        return ToolInvocationOutcome(kind="error", error_message=str(exc))

    spec = entry.spec

    # 1. input validation
    try:
        jsonschema.validate(tool_input, spec.input_schema)
    except jsonschema.ValidationError as exc:
        return ToolInvocationOutcome(
            kind="error",
            error_message=f"Input validation failed for {name!r}: {exc.message}",
        )

    # 2. approval gating
    approval_id = _approval_id_for(ctx.turn_id, name)
    if spec.side_effect and spec.approval_required:
        granted = ctx.approvals.get(approval_id)
        if granted is None:
            return ToolInvocationOutcome(
                kind="approval_needed",
                approval_id=approval_id,
                approval_summary=_summary_for(name, tool_input),
            )
        if granted is False:
            # Record the rejection as an audit event so denials are traceable.
            now = datetime.now(timezone.utc)
            audit = AuditEvent(
                id=_uuid7_like(),
                tenant_id=ctx.tenant_id,
                actor_id=ctx.actor_id,
                actor_kind=ctx.actor_kind,
                tool=name,
                inputs=_jsonable(tool_input),
                approval_required=True,
                started_at=now,
                completed_at=now,
                status=AuditStatus.REJECTED,
            )
            await audit_sink.write(audit)
            return ToolInvocationOutcome(
                kind="error",
                error_message=f"Approval denied for tool {name!r}.",
                audit_id=audit.id,
            )

    # 3. run with audit
    audit_id: EntityId | None = None
    audit: AuditEvent | None = None
    if spec.side_effect:
        audit = AuditEvent(
            id=_uuid7_like(),
            tenant_id=ctx.tenant_id,
            actor_id=ctx.actor_id,
            actor_kind=ctx.actor_kind,
            tool=name,
            inputs=_jsonable(tool_input),
            approval_required=spec.approval_required,
            approved_by=ctx.actor_id if spec.approval_required else None,
            approved_at=datetime.now(timezone.utc) if spec.approval_required else None,
            started_at=datetime.now(timezone.utc),
            status=AuditStatus.STARTED,
        )
        await audit_sink.write(audit)
        audit_id = audit.id

    try:
        output = await _run_handler(entry.handler, tool_input, ctx)
    except DriverError as exc:
        logger.warning("tool %s driver error: %s", name, exc.message)
        if audit is not None:
            audit.status = AuditStatus.FAILED
            audit.error = f"{type(exc).__name__}: {exc.message}"
            audit.completed_at = datetime.now(timezone.utc)
            await audit_sink.write(audit)
        return ToolInvocationOutcome(
            kind="error",
            error_message=f"{type(exc).__name__}: {exc.message}",
            audit_id=audit_id,
        )
    except Exception as exc:  # noqa: BLE001 — last-resort catch for the audit
        logger.exception("tool %s unexpected failure", name)
        if audit is not None:
            audit.status = AuditStatus.FAILED
            audit.error = f"{type(exc).__name__}: {exc}"
            audit.completed_at = datetime.now(timezone.utc)
            await audit_sink.write(audit)
        return ToolInvocationOutcome(
            kind="error",
            error_message=f"{type(exc).__name__}: {exc}",
            audit_id=audit_id,
        )

    if audit is not None:
        audit.status = AuditStatus.SUCCEEDED
        audit.outputs = _jsonable(output) if isinstance(output, dict) else {}
        audit.completed_at = datetime.now(timezone.utc)
        await audit_sink.write(audit)

    return ToolInvocationOutcome(kind="success", output=output, audit_id=audit_id)


def _jsonable(value: Any) -> dict[str, Any]:
    """Best-effort conversion of tool inputs/outputs into plain dicts.

    AuditEvent.inputs/outputs are ``dict[str, Any]``. We strip anything
    obviously non-serialisable while keeping strings and numbers intact.
    """
    if not isinstance(value, dict):
        return {"value": str(value)}
    out: dict[str, Any] = {}
    for k, v in value.items():
        if isinstance(v, (str, int, bool)) or v is None:
            out[str(k)] = v
        elif isinstance(v, (Decimal,)):
            out[str(k)] = str(v)
        elif isinstance(v, (list, dict)):
            out[str(k)] = v
        else:
            out[str(k)] = str(v)
    return out


# --------------------------------------------------------------------------- #
# --- orchestrator tools ---                                                  #
# --------------------------------------------------------------------------- #


_HANDOFF_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["domain", "goal"],
    "properties": {
        "domain": {
            "type": "string",
            "enum": ["ticketing_visa", "hotels_holidays", "accounting"],
        },
        "goal": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}


_CLARIFY_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["question"],
    "properties": {"question": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}


async def _handoff_handler(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """The handoff tool is resolved by the orchestrator itself — the
    handler just echoes input so downstream logic can read it."""
    return {"domain": tool_input["domain"], "goal": tool_input["goal"]}


async def _clarify_handler(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return {"question": tool_input["question"]}


# --------------------------------------------------------------------------- #
# --- ticketing_visa tools ---                                                #
# --------------------------------------------------------------------------- #


SEARCH_FLIGHTS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["origin", "destination", "outbound_date", "passengers"],
    "properties": {
        "origin": {"type": "string", "pattern": r"^[A-Z0-9]{2,3}$"},
        "destination": {"type": "string", "pattern": r"^[A-Z0-9]{2,3}$"},
        "outbound_date": {"type": "string", "format": "date"},
        "return_date": {"type": "string", "format": "date"},
        "passengers": {
            "type": "object",
            "properties": {
                "adult": {"type": "integer", "minimum": 0},
                "child": {"type": "integer", "minimum": 0},
                "infant": {"type": "integer", "minimum": 0},
                "senior": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "cabin": {
            "type": "string",
            "enum": ["economy", "premium_economy", "business", "first"],
        },
        "direct_only": {"type": "boolean"},
    },
    "additionalProperties": False,
}


READ_PNR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["locator"],
    "properties": {"locator": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}


ISSUE_TICKET_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["pnr_id"],
    "properties": {"pnr_id": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}


DRIVER_REGISTRY_KEY = "driver_registry"


def _resolve_registry(ctx: ToolContext) -> Any:
    """Return the DriverRegistry attached to this context.

    We keep the import local to avoid a circular dependency between
    tools and drivers modules.
    """
    reg = ctx.extensions.get(DRIVER_REGISTRY_KEY)
    if reg is None:
        raise RuntimeError(
            "No driver registry on ToolContext.extensions "
            f"[{DRIVER_REGISTRY_KEY!r}]. Wire one before invoking tools."
        )
    return reg


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _passengers_from_input(raw: dict[str, int]) -> dict[PassengerType, int]:
    mapping: dict[str, PassengerType] = {
        "adult": PassengerType.ADULT,
        "child": PassengerType.CHILD,
        "infant": PassengerType.INFANT,
        "senior": PassengerType.SENIOR,
    }
    out: dict[PassengerType, int] = {}
    for k, v in (raw or {}).items():
        if v and v > 0 and k in mapping:
            out[mapping[k]] = int(v)
    if not out:
        out[PassengerType.ADULT] = 1
    return out


def _fare_summary(fare: Any) -> dict[str, Any]:
    """Compress a canonical Fare into the LLM-friendly summary."""
    total = getattr(fare, "total", None)
    amount = str(total.amount) if total is not None else ""
    currency = getattr(total, "currency", "") if total is not None else ""
    return {
        "fare_id": getattr(fare, "id", None),
        "source": getattr(fare, "source", None),
        "source_ref": getattr(fare, "source_ref", None),
        "price": f"{currency} {amount}".strip(),
        "valid_until": (
            fare.valid_until.isoformat() if getattr(fare, "valid_until", None) else None
        ),
    }


@tool(
    name="search_flights",
    description=(
        "Shop for flight fares. Read-only. Returns compact fare summaries "
        "(price, carrier source, validity). Use this before quoting."
    ),
    domain="ticketing_visa",
    input_schema=SEARCH_FLIGHTS_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def search_flights(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Handler for ``search_flights``.

    Wraps a :class:`FareSearchDriver` by constructing a
    :class:`FareSearchCriteria` from the LLM-friendly JSON payload.
    """
    registry = _resolve_registry(ctx)
    driver = registry.get("FareSearchDriver")

    criteria = FareSearchCriteria(
        passengers=_passengers_from_input(tool_input.get("passengers") or {}),
        origin=tool_input["origin"],
        destination=tool_input["destination"],
        outbound_date=_parse_date(tool_input["outbound_date"]),
        return_date=(
            _parse_date(tool_input["return_date"]) if tool_input.get("return_date") else None
        ),
        cabin=CabinClass(tool_input.get("cabin", "economy")),
        direct_only=bool(tool_input.get("direct_only", False)),
    )
    fares = await driver.search(criteria)
    summaries = [_fare_summary(f) for f in fares[:20]]
    return {"count": len(fares), "fares": summaries}


@tool(
    name="read_pnr",
    description=(
        "Fetch a reservation by vendor locator / order id. Read-only. "
        "Returns a compact structured summary."
    ),
    domain="ticketing_visa",
    input_schema=READ_PNR_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def read_pnr(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Handler for ``read_pnr``."""
    registry = _resolve_registry(ctx)
    driver = registry.get("PNRDriver")
    pnr = await driver.read(tool_input["locator"])
    return {
        "pnr_id": getattr(pnr, "id", None),
        "locator": getattr(pnr, "locator", None),
        "source": getattr(pnr, "source", None),
        "status": getattr(pnr, "status", None),
        "passenger_count": len(getattr(pnr, "passenger_ids", []) or []),
        "segment_count": len(getattr(pnr, "segment_ids", []) or []),
        "fare_count": len(getattr(pnr, "fare_ids", []) or []),
    }


@tool(
    name="issue_ticket",
    description=(
        "Issue e-tickets for a PNR. Irreversible, side-effect-bearing. "
        "Always requires explicit human approval."
    ),
    domain="ticketing_visa",
    input_schema=ISSUE_TICKET_SCHEMA,
    side_effect=True,
    reversible=False,
    approval_required=True,
    approval_roles=["agency_admin", "ticketing_lead"],
)
async def issue_ticket(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Handler for ``issue_ticket``.

    The v0 Amadeus driver declares this capability ``not_supported``. We
    catch :class:`CapabilityNotSupportedError` and surface a clear
    explanation rather than propagating the raw exception, so the agent
    can explain the limitation to the user.
    """
    registry = _resolve_registry(ctx)
    driver = registry.get("PNRDriver")
    try:
        tickets = await driver.issue_ticket(tool_input["pnr_id"])
    except CapabilityNotSupportedError as exc:
        return {
            "issued": False,
            "reason": "capability_not_supported",
            "detail": exc.message,
        }
    return {
        "issued": True,
        "tickets": [
            {
                "ticket_id": getattr(t, "id", None),
                "number": getattr(t, "number", None),
                "status": getattr(t, "status", None),
            }
            for t in (tickets or [])
        ],
    }


# --------------------------------------------------------------------------- #
# Bootstrap — register orchestrator tools                                     #
# --------------------------------------------------------------------------- #


def _register_orchestrator_tools() -> None:
    """Register the orchestrator-only tools (handoff, clarify).

    These are kept outside the ``@tool`` decorator block because they
    aren't exported as individual python symbols — the orchestrator
    references them by name.
    """
    if "handoff" not in _REGISTRY:
        register_tool(
            ToolSpec(
                name="handoff",
                description=(
                    "Hand off to a domain agent for the rest of this turn. "
                    "Use when the user's intent clearly belongs to one of "
                    "ticketing_visa / hotels_holidays / accounting."
                ),
                input_schema=_HANDOFF_SCHEMA,
                side_effect=False,
                reversible=True,
                approval_required=False,
                domain="cross_cutting",
            ),
            _handoff_handler,
        )
    if "clarify" not in _REGISTRY:
        register_tool(
            ToolSpec(
                name="clarify",
                description=(
                    "Ask the user one short clarifying question. Use only "
                    "when routing is ambiguous."
                ),
                input_schema=_CLARIFY_SCHEMA,
                side_effect=False,
                reversible=True,
                approval_required=False,
                domain="cross_cutting",
            ),
            _clarify_handler,
        )


_register_orchestrator_tools()


ORCHESTRATOR_TOOL_NAMES: list[str] = ["handoff", "clarify"]
TICKETING_VISA_TOOL_NAMES: list[str] = ["search_flights", "read_pnr", "issue_ticket"]


__all__ = [
    "AuditSink",
    "InMemoryAuditSink",
    "ORCHESTRATOR_TOOL_NAMES",
    "TICKETING_VISA_TOOL_NAMES",
    "Tool",
    "ToolContext",
    "ToolDomain",
    "ToolHandler",
    "ToolInvocationOutcome",
    "ToolSpec",
    "anthropic_tool_defs",
    "clear_registry",
    "get_tool",
    "invoke_tool",
    "list_tools",
    "register_tool",
    "tool",
    "DRIVER_REGISTRY_KEY",
]
