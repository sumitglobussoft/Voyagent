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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    # Optional Pydantic model used to validate the handler's *return*
    # value. When set, invoke_tool rejects non-matching output and drives
    # a single retry before surfacing a permanent tool_output_invalid.
    output_schema: type[BaseModel] | None = None
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
    actor_role: str = Field(
        default="agent",
        description=(
            "Coarse role of the acting principal. Cross-checked against "
            "ToolSpec.approval_roles in invoke_tool so a user who lacks "
            "the role cannot approve their own action."
        ),
    )
    approvals: dict[str, bool] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationOutcome(BaseModel):
    """Result of a single :func:`invoke_tool` call.

    ``kind`` distinguishes successful execution, an input/runtime error,
    and "approval needed" — the last short-circuits execution and asks
    the orchestrator to surface a human decision.
    """

    model_config = _runtime_config()

    kind: Literal["success", "error", "approval_needed", "permission_denied"]
    output: dict[str, Any] | None = None
    error_message: str | None = None
    message: str | None = None
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
    output_schema: type[BaseModel] | None = None,
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
            output_schema=output_schema,
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


_ApprovalSummaryFn = Callable[[dict[str, Any]], str]
_APPROVAL_SUMMARY_FNS: dict[str, _ApprovalSummaryFn] = {}


def register_approval_summary(tool_name: str, fn: _ApprovalSummaryFn) -> None:
    """Register a tool-specific approval-summary renderer.

    Side-effect tools that require approval can supply a richer summary
    than the default ``_summary_for`` produces. The caller passes a
    callable that receives the validated ``tool_input`` dict and returns
    a short plain-English sentence.
    """
    _APPROVAL_SUMMARY_FNS[tool_name] = fn


def _summary_for(tool_name: str, tool_input: dict[str, Any]) -> str:
    """One short sentence describing what the tool would do. Conservative."""
    specific = _APPROVAL_SUMMARY_FNS.get(tool_name)
    if specific is not None:
        try:
            return specific(tool_input)
        except Exception:  # noqa: BLE001 - never let summary crash the gate
            logger.debug("approval summary for %s raised; falling back", tool_name)
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

    # 2. RBAC — short-circuit BEFORE the approval gate so a user who
    # lacks the role can never self-approve their own action. Empty
    # approval_roles on an approval-required tool means "any
    # authenticated role may be the approver" and falls through to the
    # regular approval gate.
    if (
        spec.approval_required
        and spec.approval_roles
        and ctx.actor_role not in spec.approval_roles
    ):
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
            error=(
                f"permission_denied: role {ctx.actor_role!r} not in "
                f"approval_roles={list(spec.approval_roles)}"
            ),
        )
        await audit_sink.write(audit)
        return ToolInvocationOutcome(
            kind="permission_denied",
            message=(
                f"role {ctx.actor_role!r} not in "
                f"approval_roles={list(spec.approval_roles)}"
            ),
            error_message=(
                f"Role {ctx.actor_role!r} is not permitted to invoke "
                f"tool {name!r}."
            ),
            audit_id=audit.id,
        )

    # 3. approval gating
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

    # 4. run with audit
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

    # Execute with a one-shot retry when the spec declares an
    # output_schema and the first call returns a non-matching dict. The
    # retry uses the same audit row: a rejected shape is a transient
    # handler failure, not a new logical call.
    async def _invoke_handler_once() -> dict[str, Any]:
        return await _run_handler(entry.handler, tool_input, ctx)

    validation_attempts = 0
    max_validation_attempts = 2 if spec.output_schema is not None else 1
    last_validation_error: str | None = None

    try:
        while True:
            validation_attempts += 1
            output = await _invoke_handler_once()
            if spec.output_schema is None:
                break
            try:
                spec.output_schema.model_validate(output)
                last_validation_error = None
                break
            except ValidationError as verr:
                last_validation_error = str(verr)
                logger.warning(
                    "tool %s output failed %s validation (attempt %d/%d)",
                    name,
                    spec.output_schema.__name__,
                    validation_attempts,
                    max_validation_attempts,
                )
                if validation_attempts >= max_validation_attempts:
                    break
                # Nudge the handler via ctx.extensions so a retry-aware
                # handler can shape a better payload. The machinery works
                # even for handlers that ignore it.
                ctx.extensions["_last_output_validation_error"] = last_validation_error
                continue
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

    if last_validation_error is not None:
        # Both attempts produced output that failed schema validation.
        # Surface this as a regular tool-failure outcome so the agent
        # loop forwards an ``is_error`` tool_result to the model.
        if audit is not None:
            audit.status = AuditStatus.FAILED
            audit.error = f"tool_output_invalid: {last_validation_error}"
            audit.completed_at = datetime.now(timezone.utc)
            await audit_sink.write(audit)
        return ToolInvocationOutcome(
            kind="error",
            error_message=(
                f"tool_output_invalid: {name!r} returned a payload that did "
                f"not match {spec.output_schema.__name__!r} after "
                f"{validation_attempts} attempt(s): {last_validation_error}"
            ),
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
TENANT_REGISTRY_KEY = "tenant_registry"


async def _resolve_registry(ctx: ToolContext) -> Any:
    """Return the :class:`DriverRegistry` that owns this tenant's drivers.

    Resolution order:
      1. If the context carries a :class:`TenantRegistry` under
         :data:`TENANT_REGISTRY_KEY`, ask it to materialise (or return a
         cached) registry for ``ctx.tenant_id``. This is the multi-
         tenant path.
      2. Otherwise fall back to a legacy process-wide
         :class:`DriverRegistry` under :data:`DRIVER_REGISTRY_KEY` — this
         keeps pre-multi-tenant tests green during the migration.

    We keep the import local to avoid a circular dependency between
    tools and drivers modules.
    """
    tenant_reg = ctx.extensions.get(TENANT_REGISTRY_KEY)
    if tenant_reg is not None:
        return await tenant_reg.get(ctx.tenant_id)

    reg = ctx.extensions.get(DRIVER_REGISTRY_KEY)
    if reg is None:
        raise RuntimeError(
            "No tenant registry or driver registry on ToolContext.extensions "
            f"(looked for {TENANT_REGISTRY_KEY!r} / {DRIVER_REGISTRY_KEY!r}). "
            "Wire one before invoking tools."
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
    registry = await _resolve_registry(ctx)
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
    registry = await _resolve_registry(ctx)
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
    registry = await _resolve_registry(ctx)
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


# --------------------------------------------------------------------------- #
# --- accounting tools ---                                                    #
# --------------------------------------------------------------------------- #


LIST_LEDGER_ACCOUNTS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


POST_JOURNAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["entry"],
    "properties": {
        "entry": {
            "type": "object",
            "required": ["narration", "lines"],
            "properties": {
                "narration": {"type": "string", "minLength": 1},
                "entry_date": {"type": "string", "format": "date"},
                "source_event": {"type": "string"},
                "lines": {
                    "type": "array",
                    "minItems": 2,
                    "items": {
                        "type": "object",
                        "required": ["account_id", "currency"],
                        "properties": {
                            "account_id": {"type": "string", "minLength": 1},
                            "account_code": {"type": "string"},
                            "debit_amount": {"type": "string"},
                            "credit_amount": {"type": "string"},
                            "currency": {
                                "type": "string",
                                "pattern": r"^[A-Z]{3}$",
                            },
                            "narration": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        }
    },
    "additionalProperties": False,
}


CREATE_INVOICE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["invoice"],
    "properties": {
        "invoice": {
            "type": "object",
            "required": [
                "invoice_number",
                "client_id",
                "issue_date",
                "currency",
                "lines",
                "billing_address",
            ],
            "properties": {
                "invoice_number": {"type": "string", "minLength": 1},
                "series": {"type": "string"},
                "client_id": {"type": "string", "minLength": 1},
                "issue_date": {"type": "string", "format": "date"},
                "due_date": {"type": "string", "format": "date"},
                "currency": {"type": "string", "pattern": r"^[A-Z]{3}$"},
                "lines": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "object"},
                },
                "billing_address": {"type": "object"},
                "notes": {"type": "string"},
            },
            "additionalProperties": True,
        }
    },
    "additionalProperties": False,
}


DRAFT_INVOICE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["customer_name", "issue_date", "due_date", "line_items"],
    "properties": {
        "customer_name": {
            "type": "string",
            "minLength": 1,
            "description": "Customer / debtor name. Required.",
        },
        "party_reference": {
            "type": ["string", "null"],
            "description": "Optional passenger id / enquiry id / session id.",
        },
        "issue_date": {"type": "string", "format": "date"},
        "due_date": {"type": "string", "format": "date"},
        "line_items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["description", "quantity", "unit_price", "currency"],
                "properties": {
                    "description": {"type": "string", "minLength": 1},
                    "quantity": {"type": "integer", "minimum": 1},
                    "unit_price": {
                        "type": "string",
                        "description": 'Decimal string, e.g. "12500.00"',
                    },
                    "currency": {"type": "string", "pattern": r"^[A-Z]{3}$"},
                },
                "additionalProperties": False,
            },
        },
        "notes": {"type": ["string", "null"]},
        "number": {
            "type": ["string", "null"],
            "description": "Invoice number; auto-generated if omitted.",
        },
    },
    "additionalProperties": False,
}


FETCH_BSP_STATEMENT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["country", "period_start", "period_end"],
    "properties": {
        "country": {"type": "string", "pattern": r"^[A-Z]{2}$"},
        "period_start": {"type": "string", "format": "date"},
        "period_end": {"type": "string", "format": "date"},
    },
    "additionalProperties": False,
}


RECONCILE_BSP_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["report_id"],
    "properties": {
        "report_id": {"type": "string", "minLength": 1},
        "ticket_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": False,
}


READ_ACCOUNT_BALANCE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["account_id", "as_of"],
    "properties": {
        "account_id": {"type": "string", "minLength": 1},
        "as_of": {"type": "string", "format": "date"},
    },
    "additionalProperties": False,
}


# Keys used to stash per-runtime caches on ``ctx.extensions``.
BSP_REPORTS_CACHE_KEY = "bsp_reports_cache"
TICKETS_STORE_KEY = "tickets_store"
# An ``async_sessionmaker`` pointing at the runtime's primary DB. Tools
# that write directly to the storage schema (e.g. ``draft_invoice``)
# look up this key; tests inject an aiosqlite-backed sessionmaker, and
# production wires the API/runtime default sessionmaker here.
DB_SESSIONMAKER_KEY = "db_sessionmaker"


def _fmt_money(amount: Decimal, currency: str) -> str:
    """Render a Money-shaped pair as ``"CCY 1,234.56"``.

    Generic formatting only — no Indian lakh/crore formatting here.
    Localisation happens at the presentation layer (docs/DECISIONS.md#d8).
    """
    try:
        return f"{currency} {Decimal(amount):,.2f}"
    except Exception:  # pragma: no cover - defensive
        return f"{currency} {amount}"


@tool(
    name="list_ledger_accounts",
    description=(
        "List the tenant's chart of accounts. Read-only. Returns compact "
        "{id, code, name, type} entries. Always call this before posting "
        "a journal or creating an invoice."
    ),
    domain="accounting",
    input_schema=LIST_LEDGER_ACCOUNTS_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def list_ledger_accounts(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``list_ledger_accounts``."""
    del tool_input
    registry = await _resolve_registry(ctx)
    driver = registry.get("AccountingDriver")
    accounts = await driver.list_accounts()
    summaries: list[dict[str, Any]] = []
    for a in accounts[:200]:
        name_default = getattr(getattr(a, "name", None), "default", None) or ""
        summaries.append(
            {
                "id": getattr(a, "id", None),
                "code": getattr(a, "code", None),
                "name": name_default,
                "type": getattr(a, "type", None),
            }
        )
    return {"count": len(accounts), "accounts": summaries}


@tool(
    name="post_journal_entry",
    description=(
        "Post a double-entry journal voucher to the books. SIDE EFFECT, "
        "NOT REVERSIBLE. Always requires human approval. Provide narration "
        "and at least two lines; each line sets exactly one of "
        "debit_amount / credit_amount, plus currency."
    ),
    domain="accounting",
    input_schema=POST_JOURNAL_SCHEMA,
    side_effect=True,
    reversible=False,
    approval_required=True,
    approval_roles=["accountant", "admin"],
)
async def post_journal_entry(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``post_journal_entry``.

    Builds a canonical :class:`JournalEntry` from the LLM-friendly
    payload and forwards to the :class:`AccountingDriver`.
    """
    from schemas.canonical import JournalEntry, JournalLine, LocalizedText, Money

    registry = await _resolve_registry(ctx)
    driver = registry.get("AccountingDriver")

    entry_input = tool_input["entry"]
    lines_in = entry_input.get("lines") or []
    canonical_lines: list[JournalLine] = []
    for ln in lines_in:
        ccy = str(ln["currency"]).upper()
        debit = ln.get("debit_amount")
        credit = ln.get("credit_amount")
        if (debit is None) == (credit is None):
            return {
                "posted": False,
                "reason": "invalid_line",
                "detail": "Each line must set exactly one of debit_amount / credit_amount.",
            }
        canonical_lines.append(
            JournalLine(
                account_id=ln["account_id"],
                debit=Money(amount=Decimal(str(debit)), currency=ccy) if debit is not None else None,
                credit=Money(amount=Decimal(str(credit)), currency=ccy) if credit is not None else None,
                narration=ln.get("narration"),
            )
        )

    entry_date = (
        date.fromisoformat(entry_input["entry_date"])
        if entry_input.get("entry_date")
        else datetime.now(timezone.utc).date()
    )
    now = datetime.now(timezone.utc)

    try:
        entry = JournalEntry(
            id=_uuid7_like(),
            tenant_id=ctx.tenant_id,
            entry_date=entry_date,
            narration=LocalizedText(default=str(entry_input["narration"])),
            lines=canonical_lines,
            source_event=str(entry_input.get("source_event") or "manual.journal"),
            created_at=now,
            updated_at=now,
        )
    except Exception as exc:
        return {"posted": False, "reason": "validation_failed", "detail": str(exc)}

    journal_id = await driver.post_journal(entry)
    return {"posted": True, "journal_id": journal_id}


@tool(
    name="create_invoice",
    description=(
        "Create a customer invoice in the backing accounting system. "
        "SIDE EFFECT, reversible (supports cancellation / credit note). "
        "Always requires human approval."
    ),
    domain="accounting",
    input_schema=CREATE_INVOICE_SCHEMA,
    side_effect=True,
    reversible=True,
    approval_required=True,
    approval_roles=["accountant", "admin"],
)
async def create_invoice(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``create_invoice``.

    For v0 the canonical :class:`Invoice` is assumed to have been
    assembled upstream. This tool accepts a dict that already looks
    like :meth:`Invoice.model_dump` and hands it to the accounting
    driver.
    """
    from schemas.canonical import Invoice

    registry = await _resolve_registry(ctx)
    driver = registry.get("AccountingDriver")

    raw = dict(tool_input["invoice"])
    now = datetime.now(timezone.utc)
    raw.setdefault("id", _uuid7_like())
    raw.setdefault("tenant_id", ctx.tenant_id)
    raw.setdefault("created_at", now)
    raw.setdefault("updated_at", now)

    try:
        invoice = Invoice.model_validate(raw)
    except Exception as exc:
        return {"created": False, "reason": "validation_failed", "detail": str(exc)}

    invoice_id = await driver.create_invoice(invoice)
    return {
        "created": True,
        "invoice_id": invoice_id,
        "invoice_number": invoice.invoice_number,
    }


async def _draft_invoice_sessionmaker(ctx: ToolContext) -> Any:
    """Resolve the ``async_sessionmaker`` used by ``draft_invoice``.

    Preference: an explicit sessionmaker placed on ``ctx.extensions``
    under :data:`DB_SESSIONMAKER_KEY` (tests and multi-tenant wiring).
    Fallback: the API process-wide sessionmaker from
    :mod:`voyagent_api.db` (production single-tenant bootstrap).
    """
    sm = ctx.extensions.get(DB_SESSIONMAKER_KEY)
    if sm is not None:
        return sm
    from voyagent_api import db as _db  # local import: keep tools.py import light

    return _db.get_sessionmaker()


@tool(
    name="draft_invoice",
    description=(
        "Draft an invoice for a customer. Saved with status='draft'. Does "
        "NOT post to the ledger. Requires finance approval on first "
        "invocation."
    ),
    domain="accounting",
    input_schema=DRAFT_INVOICE_SCHEMA,
    side_effect=True,
    reversible=True,
    approval_required=True,
    approval_roles=["accountant", "admin"],
)
async def draft_invoice(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``draft_invoice``.

    Writes a ``draft`` row into the ``invoices`` storage table — the
    human-readable document layer. Does not touch the ledger. Errors
    are returned as structured payloads (``drafted=False`` +
    ``error_code``), not raised, so the agent can recover mid-turn.
    """
    import re as _re

    from sqlalchemy import func, select
    from sqlalchemy.exc import IntegrityError

    from schemas.storage.invoice import InvoiceRow, InvoiceStatusEnum

    line_items = tool_input.get("line_items") or []
    currencies = {str(li["currency"]).upper() for li in line_items}
    if len(currencies) > 1:
        return {
            "drafted": False,
            "error_code": "mixed_currency",
            "detail": (
                "All line items must share one currency; got "
                f"{sorted(currencies)}."
            ),
        }
    currency = currencies.pop()

    total = Decimal("0.00")
    for li in line_items:
        qty = int(li["quantity"])
        price = Decimal(str(li["unit_price"]))
        total = (total + (Decimal(qty) * price)).quantize(Decimal("0.01"))

    try:
        issue_d = date.fromisoformat(tool_input["issue_date"])
        due_d = date.fromisoformat(tool_input["due_date"])
    except ValueError as exc:
        return {
            "drafted": False,
            "error_code": "invalid_date",
            "detail": str(exc),
        }

    tenant_uuid = uuid.UUID(ctx.tenant_id)
    sessionmaker = await _draft_invoice_sessionmaker(ctx)

    explicit_number = tool_input.get("number")
    number: str

    async with sessionmaker() as s:
        if explicit_number:
            exists = (
                await s.execute(
                    select(InvoiceRow.id).where(
                        InvoiceRow.tenant_id == tenant_uuid,
                        InvoiceRow.number == explicit_number,
                    )
                )
            ).scalar_one_or_none()
            if exists is not None:
                return {
                    "drafted": False,
                    "error_code": "invoice_number_conflict",
                    "detail": (
                        f"Invoice number {explicit_number!r} already exists "
                        f"for this tenant."
                    ),
                }
            number = str(explicit_number)
        else:
            # Auto-generate: INV-<TENANT8>-<0001+>. Sequence is scoped
            # per-tenant by filtering on tenant_id; the regex makes sure
            # we only count rows that follow the auto-numbered shape for
            # *this* tenant so human-provided numbers can't pollute the
            # next sequence value.
            tenant_prefix = ctx.tenant_id.replace("-", "")[:8].upper()
            prefix = f"INV-{tenant_prefix}-"
            existing = (
                (
                    await s.execute(
                        select(InvoiceRow.number).where(
                            InvoiceRow.tenant_id == tenant_uuid,
                            InvoiceRow.number.like(f"{prefix}%"),
                        )
                    )
                )
                .scalars()
                .all()
            )
            pat = _re.compile(rf"^{_re.escape(prefix)}(\d+)$")
            max_seq = 0
            for n in existing:
                m = pat.match(n or "")
                if m:
                    try:
                        seq = int(m.group(1))
                    except ValueError:
                        continue
                    if seq > max_seq:
                        max_seq = seq
            number = f"{prefix}{max_seq + 1:04d}"

        row = InvoiceRow(
            tenant_id=tenant_uuid,
            number=number,
            party_name=str(tool_input["customer_name"]),
            party_reference=tool_input.get("party_reference"),
            issue_date=issue_d,
            due_date=due_d,
            total_amount=total,
            currency=currency,
            amount_paid=Decimal("0.00"),
            status=InvoiceStatusEnum.DRAFT,
        )
        s.add(row)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return {
                "drafted": False,
                "error_code": "invoice_number_conflict",
                "detail": (
                    f"Concurrent write — invoice number {number!r} was "
                    f"taken before this insert committed."
                ),
            }
        invoice_id = str(row.id)

    return {
        "drafted": True,
        "invoice_id": invoice_id,
        "number": number,
        "total_amount": str(total),
        "currency": currency,
        "status": "draft",
    }


@tool(
    name="fetch_bsp_statement",
    description=(
        "Fetch and parse a BSP settlement statement for a country + period. "
        "Read-only. Returns a compact summary (totals, transaction counts). "
        "The full canonical report is cached in the runtime under the "
        "returned report_id for later reconcile_bsp calls."
    ),
    domain="accounting",
    input_schema=FETCH_BSP_STATEMENT_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def fetch_bsp_statement(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``fetch_bsp_statement``."""
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from schemas.canonical import Period

    registry = await _resolve_registry(ctx)
    driver = registry.get("BSPDriver")

    start_d = date.fromisoformat(tool_input["period_start"])
    end_d = date.fromisoformat(tool_input["period_end"])
    period = Period(
        start=_dt(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc),
        end=_dt(end_d.year, end_d.month, end_d.day, tzinfo=timezone.utc) + _td(days=1),
    )
    report = await driver.fetch_statement(tool_input["country"], period)

    cache: dict[str, Any] = ctx.extensions.setdefault(BSP_REPORTS_CACHE_KEY, {})
    cache[report.id] = report

    return {
        "report_id": report.id,
        "country": report.country,
        "sales_total": _fmt_money(report.sales_total.amount, report.sales_total.currency),
        "refund_total": _fmt_money(report.refund_total.amount, report.refund_total.currency),
        "commission_total": _fmt_money(
            report.commission_total.amount, report.commission_total.currency
        ),
        "net_remittance": _fmt_money(
            report.net_remittance.amount, report.net_remittance.currency
        ),
        "transaction_count": len(report.transactions),
        "source_ref": report.source_ref,
    }


@tool(
    name="reconcile_bsp",
    description=(
        "Run deterministic reconciliation of a previously fetched BSP "
        "report against Voyagent tickets. Read-only. Returns a compact "
        "summary plus an issues list for the accountant to review. In v0 "
        "the optional ticket_ids argument selects from the runtime's in-"
        "memory tickets store; in production this will pull from the "
        "sales table."
    ),
    domain="accounting",
    input_schema=RECONCILE_BSP_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def reconcile_bsp(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``reconcile_bsp``."""
    # Local import — the tools module should stay importable without the
    # BSP India driver installed.
    from drivers.bsp_india.mapping import reconcile_bsp_against_tickets

    cache = ctx.extensions.get(BSP_REPORTS_CACHE_KEY) or {}
    report = cache.get(tool_input["report_id"])
    if report is None:
        return {
            "reconciled": False,
            "reason": "report_not_found",
            "detail": (
                f"No cached BSP report with id {tool_input['report_id']!r}. "
                "Call fetch_bsp_statement first."
            ),
        }

    tickets_store: dict[str, Any] = ctx.extensions.get(TICKETS_STORE_KEY) or {}
    ticket_ids = tool_input.get("ticket_ids")
    if ticket_ids:
        tickets = [tickets_store[t] for t in ticket_ids if t in tickets_store]
    else:
        tickets = list(tickets_store.values())

    reconciliation = reconcile_bsp_against_tickets(report, tickets)
    summary = reconciliation.summary
    issues: list[dict[str, Any]] = []
    for item in reconciliation.items:
        if item.outcome == "matched":
            continue
        delta = None
        if item.delta is not None:
            delta = _fmt_money(item.delta.amount, item.delta.currency)
        issues.append(
            {
                "outcome": item.outcome,
                "external_ref": item.external_ref,
                "internal_refs": item.internal_refs,
                "delta": delta,
                "evidence": (
                    item.evidence.default if item.evidence is not None else None
                ),
            }
        )
    return {
        "reconciled": True,
        "summary": {
            "matched": summary.matched_count,
            "matched_amount": (
                _fmt_money(
                    summary.matched_amount.amount, summary.matched_amount.currency
                )
                if summary.matched_amount is not None
                else None
            ),
            "unmatched_external": summary.unmatched_external_count,
            "unmatched_internal": summary.unmatched_internal_count,
            "discrepancy": summary.discrepancy_count,
            "tentative": summary.tentative_count,
        },
        "issues": issues[:50],
        "reconciliation_id": reconciliation.id,
    }


@tool(
    name="read_account_balance",
    description=(
        "Read a ledger account balance as of a date. Read-only. Some "
        "backends (e.g. desktop accounting) do not support this; in that "
        "case the tool returns a structured not-supported result rather "
        "than failing the run."
    ),
    domain="accounting",
    input_schema=READ_ACCOUNT_BALANCE_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def read_account_balance(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``read_account_balance``.

    The underlying :class:`AccountingDriver.read_account_balance` may
    raise :class:`CapabilityNotSupportedError` (Tally's v0 driver does).
    We catch it and surface a structured not-supported response so the
    agent can explain the limitation plainly without the runtime
    classifying the whole call as a hard failure.
    """
    registry = await _resolve_registry(ctx)
    driver = registry.get("AccountingDriver")
    as_of = date.fromisoformat(tool_input["as_of"])
    try:
        balance = await driver.read_account_balance(tool_input["account_id"], as_of)
    except CapabilityNotSupportedError as exc:
        return {
            "read": False,
            "reason": "capability_not_supported",
            "detail": exc.message,
        }
    return {
        "read": True,
        "balance": _fmt_money(balance.amount, balance.currency),
        "currency": balance.currency,
    }


def _post_journal_summary(tool_input: dict[str, Any]) -> str:
    """Approval summary for ``post_journal_entry``.

    Example output:
        "Post INR 18,500.00 journal to narration 'Daily cash sale' across
        2 lines. Not reversible."
    """
    entry = tool_input.get("entry") or {}
    narration = entry.get("narration") or "(no narration)"
    lines = entry.get("lines") or []
    debit_by_ccy: dict[str, Decimal] = {}
    for ln in lines:
        ccy = str(ln.get("currency") or "").upper()
        if not ccy:
            continue
        if ln.get("debit_amount") is not None:
            try:
                debit_by_ccy[ccy] = debit_by_ccy.get(ccy, Decimal("0")) + Decimal(
                    str(ln["debit_amount"])
                )
            except Exception:  # noqa: BLE001
                continue
    if debit_by_ccy:
        totals = ", ".join(f"{k} {v:,.2f}" for k, v in debit_by_ccy.items())
    else:
        totals = "(amount unknown)"
    return (
        f"Post {totals} journal: {narration} across {len(lines)} lines. "
        "Not reversible."
    )


def _create_invoice_summary(tool_input: dict[str, Any]) -> str:
    """Approval summary for ``create_invoice``."""
    inv = tool_input.get("invoice") or {}
    number = inv.get("invoice_number") or "(no number)"
    ccy = str(inv.get("currency") or "").upper()
    total_raw: Any = None
    for key in ("grand_total", "total", "amount"):
        if key in inv:
            candidate = inv[key]
            if isinstance(candidate, dict) and "amount" in candidate:
                total_raw = candidate["amount"]
                break
            if isinstance(candidate, (int, str)):
                total_raw = candidate
                break
    if total_raw is not None and ccy:
        try:
            return f"Create invoice {number} for {ccy} {Decimal(str(total_raw)):,.2f}. Reversible via cancellation."
        except Exception:  # noqa: BLE001
            pass
    return f"Create invoice {number}. Reversible via cancellation."


register_approval_summary("post_journal_entry", _post_journal_summary)
register_approval_summary("create_invoice", _create_invoice_summary)


# --------------------------------------------------------------------------- #
# --- hotels_holidays tools ---                                               #
# --------------------------------------------------------------------------- #


SEARCH_HOTELS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["country", "city", "check_in", "check_out", "guests"],
    "properties": {
        "country": {"type": "string", "pattern": r"^[A-Z]{2}$"},
        "city": {"type": "string", "minLength": 1},
        "check_in": {"type": "string", "format": "date"},
        "check_out": {"type": "string", "format": "date"},
        "guests": {"type": "integer", "minimum": 1},
        "currency": {"type": "string", "pattern": r"^[A-Z]{3}$"},
        "budget_max": {"type": "string"},
    },
    "additionalProperties": False,
}


CHECK_HOTEL_RATE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["rate_key"],
    "properties": {"rate_key": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}


BOOK_HOTEL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["rate_key", "passenger_ids"],
    "properties": {
        "rate_key": {"type": "string", "minLength": 1},
        "passenger_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "buyer_reference": {"type": "string"},
    },
    "additionalProperties": False,
}


CANCEL_HOTEL_BOOKING_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["booking_id"],
    "properties": {"booking_id": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}


READ_HOTEL_BOOKING_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["booking_id"],
    "properties": {"booking_id": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}


async def _resolve_hotel_search_driver(ctx: ToolContext) -> Any:
    """Return the tenant's HotelSearchDriver or raise a clear domain error.

    A missing driver means the tenant has no TBO credentials (or no
    hotel driver at all). We surface that as a structured tool result
    rather than an exception so the agent can relay it plainly — same
    failure mode ticketing_visa has when Amadeus credentials are
    missing.
    """
    registry = await _resolve_registry(ctx)
    try:
        return registry.get("HotelSearchDriver")
    except KeyError as exc:
        raise RuntimeError(
            "no hotel driver configured for this tenant"
        ) from exc


async def _resolve_hotel_booking_driver(ctx: ToolContext) -> Any:
    registry = await _resolve_registry(ctx)
    try:
        return registry.get("HotelBookingDriver")
    except KeyError as exc:
        raise RuntimeError(
            "no hotel driver configured for this tenant"
        ) from exc


def _hotel_result_summary(result: Any) -> dict[str, Any]:
    """Compress a canonical :class:`HotelSearchResult` into an LLM summary."""
    prop = getattr(result, "property", None)
    rates = getattr(result, "rates", []) or []
    cheapest = None
    for r in rates:
        price = getattr(r, "price", None)
        if price is None:
            continue
        if cheapest is None or price.amount < cheapest.amount:
            cheapest = price
    return {
        "property_id": getattr(prop, "id", None),
        "name": getattr(prop, "name", None),
        "city": getattr(prop, "city", None),
        "country": getattr(prop, "country", None),
        "star_rating": getattr(prop, "star_rating", None),
        "rate_count": len(rates),
        "from_price": (
            f"{cheapest.currency} {cheapest.amount}" if cheapest is not None else None
        ),
        "rate_keys": [getattr(r, "rate_key", None) for r in rates[:5]],
    }


@tool(
    name="search_hotels",
    description=(
        "Shop hotel availability. Read-only. Returns compact property "
        "summaries with rate keys the agent can pass to check_hotel_rate "
        "or book_hotel. Always call this before quoting a hotel."
    ),
    domain="hotels_holidays",
    input_schema=SEARCH_HOTELS_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def search_hotels(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Handler for ``search_hotels``."""
    from drivers._contracts.hotel_search import HotelSearchCriteria
    from schemas.canonical import Money as _Money

    driver = await _resolve_hotel_search_driver(ctx)

    budget_max = None
    if tool_input.get("budget_max") and tool_input.get("currency"):
        try:
            budget_max = _Money(
                amount=Decimal(str(tool_input["budget_max"])),
                currency=str(tool_input["currency"]).upper(),
            )
        except Exception:
            budget_max = None

    criteria = HotelSearchCriteria(
        destination_country=str(tool_input["country"]).upper(),
        destination_city=str(tool_input["city"]),
        check_in=_parse_date(tool_input["check_in"]),
        check_out=_parse_date(tool_input["check_out"]),
        guest_count=int(tool_input["guests"]),
        budget_max=budget_max,
    )

    # Drivers that expose the canonical search_results shape are preferred;
    # we fall back to the driver-layer HotelOffer list for older drivers.
    results_fn = getattr(driver, "search_results", None)
    if callable(results_fn):
        results = await results_fn(criteria)
        summaries = [_hotel_result_summary(r) for r in list(results)[:20]]
        return {"count": len(results), "results": summaries}

    offers = await driver.search(criteria)
    summaries = [
        {
            "property_name": getattr(o, "property_name", None),
            "property_ref": getattr(o, "property_ref", None),
            "country": getattr(o, "address_country", None),
            "price": f"{getattr(o.cost, 'currency', '')} {getattr(o.cost, 'amount', '')}".strip(),
            "board": getattr(o, "board_type", None),
            "offer_ref": getattr(o, "offer_ref", None),
        }
        for o in list(offers)[:20]
    ]
    return {"count": len(offers), "offers": summaries}


@tool(
    name="check_hotel_rate",
    description=(
        "Re-price a shopped hotel rate before booking. Read-only. "
        "Returns the current price and a (possibly refreshed) rate key. "
        "ALWAYS call this immediately before book_hotel."
    ),
    domain="hotels_holidays",
    input_schema=CHECK_HOTEL_RATE_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def check_hotel_rate(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``check_hotel_rate``."""
    driver = await _resolve_hotel_search_driver(ctx)
    check_fn = getattr(driver, "check_rate", None)
    if not callable(check_fn):
        return {
            "checked": False,
            "reason": "capability_not_supported",
            "detail": "Hotel driver does not expose check_rate.",
        }
    try:
        rate = await check_fn(tool_input["rate_key"])
    except CapabilityNotSupportedError as exc:
        return {
            "checked": False,
            "reason": "capability_not_supported",
            "detail": exc.message,
        }
    price = getattr(rate, "price", None)
    return {
        "checked": True,
        "rate_key": getattr(rate, "rate_key", None),
        "price": (
            f"{price.currency} {price.amount}" if price is not None else None
        ),
        "is_refundable": bool(getattr(rate, "is_refundable", False)),
        "board_basis": getattr(getattr(rate, "room", None), "board_basis", None),
    }


@tool(
    name="book_hotel",
    description=(
        "Confirm a hotel booking at the supplier. SIDE EFFECT, reversible "
        "(via cancel_hotel_booking subject to supplier rules). Always "
        "requires human approval. Supply the rate_key from a recent "
        "check_hotel_rate call and the canonical passenger ids."
    ),
    domain="hotels_holidays",
    input_schema=BOOK_HOTEL_SCHEMA,
    side_effect=True,
    reversible=True,
    approval_required=True,
    approval_roles=["agency_admin", "hotels_lead"],
)
async def book_hotel(tool_input: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Handler for ``book_hotel``.

    The v0 TBO driver declares this capability ``not_supported``; we
    catch :class:`CapabilityNotSupportedError` and surface a clear
    explanation instead of propagating the raw exception.
    """
    driver = await _resolve_hotel_booking_driver(ctx)
    try:
        booking = await driver.book(
            tool_input["rate_key"],
            # v0 drivers that support book() receive a canonical HotelStay
            # assembled upstream; the scaffold TBO driver raises before it
            # reaches this branch.
            None,  # type: ignore[arg-type]
        )
    except CapabilityNotSupportedError as exc:
        return {
            "booked": False,
            "reason": "capability_not_supported",
            "detail": exc.message,
        }
    return {
        "booked": True,
        "booking_id": getattr(booking, "id", None),
        "supplier": getattr(booking, "supplier", None),
        "supplier_ref": getattr(booking, "supplier_ref", None),
        "status": getattr(booking, "status", None),
    }


@tool(
    name="cancel_hotel_booking",
    description=(
        "Cancel a confirmed hotel booking at the supplier. SIDE EFFECT. "
        "Always requires human approval. Refund rules depend on the "
        "original cancellation policy."
    ),
    domain="hotels_holidays",
    input_schema=CANCEL_HOTEL_BOOKING_SCHEMA,
    side_effect=True,
    reversible=False,
    approval_required=True,
    approval_roles=["agency_admin", "hotels_lead"],
)
async def cancel_hotel_booking(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``cancel_hotel_booking``."""
    driver = await _resolve_hotel_booking_driver(ctx)
    try:
        booking = await driver.cancel(tool_input["booking_id"])
    except CapabilityNotSupportedError as exc:
        return {
            "cancelled": False,
            "reason": "capability_not_supported",
            "detail": exc.message,
        }
    return {
        "cancelled": True,
        "booking_id": getattr(booking, "id", None),
        "status": getattr(booking, "status", None),
    }


@tool(
    name="read_hotel_booking",
    description=(
        "Fetch a hotel booking from the supplier by id. Read-only. "
        "Returns a compact structured summary."
    ),
    domain="hotels_holidays",
    input_schema=READ_HOTEL_BOOKING_SCHEMA,
    side_effect=False,
    reversible=True,
    approval_required=False,
)
async def read_hotel_booking(
    tool_input: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Handler for ``read_hotel_booking``."""
    driver = await _resolve_hotel_booking_driver(ctx)
    try:
        booking = await driver.read(tool_input["booking_id"])
    except CapabilityNotSupportedError as exc:
        return {
            "read": False,
            "reason": "capability_not_supported",
            "detail": exc.message,
        }
    return {
        "read": True,
        "booking_id": getattr(booking, "id", None),
        "supplier": getattr(booking, "supplier", None),
        "supplier_ref": getattr(booking, "supplier_ref", None),
        "status": getattr(booking, "status", None),
    }


def _book_hotel_summary(tool_input: dict[str, Any]) -> str:
    rate = tool_input.get("rate_key") or "(no rate_key)"
    pax = len(tool_input.get("passenger_ids") or [])
    return (
        f"Confirm hotel booking on rate_key {rate!r} for {pax} guest(s). "
        "Reversible via cancel_hotel_booking subject to supplier rules."
    )


def _cancel_hotel_summary(tool_input: dict[str, Any]) -> str:
    return (
        f"Cancel hotel booking {tool_input.get('booking_id')!r}. "
        "Refund depends on original cancellation policy."
    )


register_approval_summary("book_hotel", _book_hotel_summary)
register_approval_summary("cancel_hotel_booking", _cancel_hotel_summary)


ORCHESTRATOR_TOOL_NAMES: list[str] = ["handoff", "clarify"]
TICKETING_VISA_TOOL_NAMES: list[str] = ["search_flights", "read_pnr", "issue_ticket"]
HOTELS_HOLIDAYS_TOOL_NAMES: list[str] = [
    "search_hotels",
    "check_hotel_rate",
    "book_hotel",
    "cancel_hotel_booking",
    "read_hotel_booking",
]
ACCOUNTING_TOOL_NAMES: list[str] = [
    "list_ledger_accounts",
    "post_journal_entry",
    "create_invoice",
    "draft_invoice",
    "fetch_bsp_statement",
    "reconcile_bsp",
    "read_account_balance",
]


__all__ = [
    "ACCOUNTING_TOOL_NAMES",
    "AuditSink",
    "BSP_REPORTS_CACHE_KEY",
    "DB_SESSIONMAKER_KEY",
    "DRIVER_REGISTRY_KEY",
    "HOTELS_HOLIDAYS_TOOL_NAMES",
    "InMemoryAuditSink",
    "ORCHESTRATOR_TOOL_NAMES",
    "TENANT_REGISTRY_KEY",
    "TICKETING_VISA_TOOL_NAMES",
    "TICKETS_STORE_KEY",
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
]
