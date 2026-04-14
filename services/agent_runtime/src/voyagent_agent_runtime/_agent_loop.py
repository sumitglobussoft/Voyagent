"""Shared Anthropic agent loop.

The orchestrator and each domain agent share the same pattern:

  1. Send the accumulated messages to Anthropic with a tool list.
  2. Stream response deltas; emit TEXT_DELTA events as text comes in.
  3. When the model stops with ``tool_use``, validate + run each tool,
     emit TOOL_USE / TOOL_RESULT / APPROVAL_REQUEST events, and loop
     back with the tool results appended.
  4. Bail out on APPROVAL_REQUEST (the turn pauses until the human
     responds) or on a natural ``end_turn`` stop.

Everything that varies between agents — system prompt, tool subset,
handoff handling — is handled by the caller via the ``tool_router``
callback and ``on_tool_use`` hook.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from .anthropic_client import AnthropicClient
from .events import AgentEvent, AgentEventKind
from .tools import (
    AuditSink,
    ToolContext,
    ToolInvocationOutcome,
    anthropic_tool_defs,
    invoke_tool,
)

logger = logging.getLogger(__name__)


MAX_TOOL_LOOPS = 8
"""Upper bound on tool-use rounds per agent turn. Defensive cap against
runaway loops when the model re-asks for the same tool indefinitely."""


# Retry schedules for upstream Anthropic failures. Expressed as the
# delays between successive attempts — so RATE_LIMIT_BACKOFF_SECONDS=(1,2)
# means 3 total attempts (initial + 1s wait + retry + 2s wait + retry).
# Module constants so tests can monkeypatch to zero-delay without
# reaching into the retry loop.
RATE_LIMIT_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0)
CONNECTION_BACKOFF_SECONDS: tuple[float, ...] = (1.0,)


async def _sleep(seconds: float) -> None:
    """Indirection so tests can patch to a no-op without touching asyncio."""
    await asyncio.sleep(seconds)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Best-effort match for ``anthropic.RateLimitError``.

    We avoid importing the SDK at module scope so tests (and environments
    without the wheel) stay light. We match by MRO name so any subclass
    the SDK ships — or a test double named ``RateLimitError`` — is
    caught without the wrapper needing to be changed.
    """
    try:
        import anthropic  # type: ignore[import-not-found]

        if isinstance(exc, anthropic.RateLimitError):
            return True
    except Exception:  # noqa: BLE001 — SDK not installed or not this version
        pass
    for klass in type(exc).__mro__:
        if klass.__name__ == "RateLimitError":
            return True
    return False


def _is_connection_error(exc: BaseException) -> bool:
    """Best-effort match for ``anthropic.APIConnectionError``."""
    try:
        import anthropic  # type: ignore[import-not-found]

        if isinstance(exc, anthropic.APIConnectionError):
            return True
    except Exception:  # noqa: BLE001
        pass
    for klass in type(exc).__mro__:
        if klass.__name__ == "APIConnectionError":
            return True
    return False


def _is_permanent_anthropic_error(exc: BaseException) -> bool:
    """AuthenticationError / BadRequestError — do not retry."""
    try:
        import anthropic  # type: ignore[import-not-found]

        permanent = (
            getattr(anthropic, "AuthenticationError", ()),
            getattr(anthropic, "BadRequestError", ()),
        )
        if any(p for p in permanent if isinstance(exc, p)):
            return True
    except Exception:  # noqa: BLE001
        pass
    for klass in type(exc).__mro__:
        if klass.__name__ in {"AuthenticationError", "BadRequestError"}:
            return True
    return False


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Extract a Retry-After hint from an Anthropic error, if present."""
    for attr in ("retry_after", "retry_after_seconds"):
        val = getattr(exc, attr, None)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers is not None:
            try:
                raw = headers.get("retry-after") or headers.get("Retry-After")
            except Exception:  # noqa: BLE001
                raw = None
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    return None
    return None


ToolRouter = Callable[[str, dict[str, Any], ToolContext], Awaitable[ToolInvocationOutcome]]
"""Pluggable dispatcher — lets the orchestrator intercept ``handoff`` before
the default registry runs it."""


async def default_tool_router(
    name: str, tool_input: dict[str, Any], ctx: ToolContext, *, audit_sink: AuditSink
) -> ToolInvocationOutcome:
    """The default dispatcher — invokes a registered tool through
    :func:`invoke_tool` with the supplied audit sink."""
    return await invoke_tool(name, tool_input, ctx, audit_sink=audit_sink)


def _extract_text_delta(event: Any) -> str | None:
    """Pull text out of an Anthropic stream event, regardless of exact SDK shape.

    The SDK yields ``RawContentBlockDeltaEvent`` objects with ``delta.text``
    for text deltas. We do duck-typing rather than importing SDK types to
    keep the fake Anthropic stub simple.
    """
    ev_type = getattr(event, "type", None)
    if ev_type != "content_block_delta":
        return None
    delta = getattr(event, "delta", None)
    if delta is None:
        return None
    dtype = getattr(delta, "type", None)
    if dtype == "text_delta":
        return getattr(delta, "text", None)
    return None


def _extract_message_stop(event: Any) -> Any | None:
    """Return the final message object from a stream if ``event`` is the stop.

    Different SDK versions expose the finalized message either on a
    ``message_stop`` event or via a ``get_final_message()`` coroutine on
    the stream object. The caller falls back to the latter.
    """
    ev_type = getattr(event, "type", None)
    if ev_type == "message_stop":
        return getattr(event, "message", None)
    return None


async def run_agent_turn(
    *,
    client: AnthropicClient,
    audit_sink: AuditSink,
    session_id: str,
    turn_id: str,
    system_prompt: str,
    tool_names: list[str],
    messages: list[dict[str, Any]],
    tool_context: ToolContext,
    tool_router: ToolRouter | None = None,
    on_tool_use: Callable[[str, dict[str, Any]], Awaitable[list[AgentEvent] | None]] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run one full agent turn and stream :class:`AgentEvent`.

    This is a generator; callers consume events as they come. The ``messages``
    list is mutated in place with assistant + tool-result turns so the
    caller can persist the final transcript after the loop ends.
    """
    tool_defs = anthropic_tool_defs(names=tool_names)

    for loop_idx in range(MAX_TOOL_LOOPS):
        final_message: Any = None
        stream_exc: BaseException | None = None
        rate_limit_attempt = 0
        connection_attempt = 0
        # Retry upstream transients. We buffer TEXT_DELTA events per
        # attempt and only yield them once the attempt reaches its
        # natural end — otherwise a retry after a mid-stream failure
        # would emit duplicated deltas.
        while True:
            buffered_deltas: list[AgentEvent] = []
            stream_exc = None
            final_message = None
            try:
                async for ev in client.stream_messages(
                    system=system_prompt,
                    messages=messages,
                    tools=tool_defs,
                ):
                    delta_text = _extract_text_delta(ev)
                    if delta_text:
                        buffered_deltas.append(
                            AgentEvent(
                                kind=AgentEventKind.TEXT_DELTA,
                                session_id=session_id,
                                turn_id=turn_id,
                                text=delta_text,
                            )
                        )
                    maybe_stop = _extract_message_stop(ev)
                    if maybe_stop is not None:
                        final_message = maybe_stop
            except Exception as exc:  # noqa: BLE001
                stream_exc = exc

            if stream_exc is None:
                for ev in buffered_deltas:
                    yield ev
                break

            if _is_permanent_anthropic_error(stream_exc):
                break
            if _is_rate_limit_error(stream_exc) and rate_limit_attempt < len(
                RATE_LIMIT_BACKOFF_SECONDS
            ):
                hinted = _retry_after_seconds(stream_exc)
                delay = (
                    hinted
                    if hinted is not None
                    else RATE_LIMIT_BACKOFF_SECONDS[rate_limit_attempt]
                )
                rate_limit_attempt += 1
                logger.warning(
                    "anthropic rate-limited; retry %d in %.2fs",
                    rate_limit_attempt,
                    delay,
                )
                await _sleep(delay)
                continue
            if _is_connection_error(stream_exc) and connection_attempt < len(
                CONNECTION_BACKOFF_SECONDS
            ):
                delay = CONNECTION_BACKOFF_SECONDS[connection_attempt]
                connection_attempt += 1
                logger.warning(
                    "anthropic connection error; retry %d in %.2fs",
                    connection_attempt,
                    delay,
                )
                await _sleep(delay)
                continue
            break

        if stream_exc is not None:
            logger.warning(
                "anthropic stream failed: %s: %s",
                type(stream_exc).__name__,
                stream_exc,
            )
            if _is_rate_limit_error(stream_exc):
                msg = (
                    "model is rate-limited, please try again in a moment "
                    f"({type(stream_exc).__name__}: {stream_exc})"
                )
            else:
                msg = f"{type(stream_exc).__name__}: {stream_exc}"
            yield AgentEvent(
                kind=AgentEventKind.ERROR,
                session_id=session_id,
                turn_id=turn_id,
                error_message=msg,
            )
            return

        # If the stream didn't expose the final message via event, pull it
        # from the stream-helper surface. This is optional — the fake
        # streams in tests embed the message directly on ``message_stop``.
        if final_message is None:
            final_message = getattr(client, "_last_final_message", None)

        if final_message is None:
            # Degenerate stream; exit.
            return

        stop_reason = getattr(final_message, "stop_reason", None)
        content_blocks = list(getattr(final_message, "content", []) or [])

        # Record the assistant turn on the transcript.
        messages.append(
            {
                "role": "assistant",
                "content": [_block_to_dict(b) for b in content_blocks],
            }
        )

        if stop_reason != "tool_use":
            # End of turn.
            return

        # Dispatch every tool_use block in order; collect tool_result content.
        tool_results: list[dict[str, Any]] = []
        approval_pending = False
        for block in content_blocks:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_name = getattr(block, "name", "")
            tool_input = dict(getattr(block, "input", {}) or {})
            tool_call_id = getattr(block, "id", "")

            yield AgentEvent(
                kind=AgentEventKind.TOOL_USE,
                session_id=session_id,
                turn_id=turn_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_call_id=tool_call_id,
            )

            # Let the caller intercept (e.g. orchestrator handling handoff).
            if on_tool_use is not None:
                override = await on_tool_use(tool_name, tool_input)
                if override is not None:
                    for ev in override:
                        yield ev
                    # Hand back a short ack as tool_result so the model knows
                    # dispatch happened, then end the turn.
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": "handled",
                        }
                    )
                    messages.append({"role": "user", "content": tool_results})
                    return

            router = tool_router or (
                lambda n, i, c: default_tool_router(n, i, c, audit_sink=audit_sink)
            )
            outcome = await router(tool_name, tool_input, tool_context)

            if outcome.kind == "approval_needed":
                yield AgentEvent(
                    kind=AgentEventKind.APPROVAL_REQUEST,
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    approval_id=outcome.approval_id,
                    approval_summary=outcome.approval_summary,
                )
                approval_pending = True
                # Record a placeholder tool_result so the transcript stays
                # well-formed when the turn resumes in a follow-up.
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": f"approval_pending:{outcome.approval_id}",
                    }
                )
                continue

            if outcome.kind == "permission_denied":
                payload: dict[str, Any] = {
                    "error": "permission_denied",
                    "detail": outcome.message
                    or outcome.error_message
                    or "role not permitted",
                }
                yield AgentEvent(
                    kind=AgentEventKind.TOOL_RESULT,
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    tool_output=payload,
                    tool_call_id=tool_call_id,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": _compact_json(payload),
                        "is_error": True,
                    }
                )
                continue

            payload = outcome.output or {
                "error": outcome.error_message or "unknown tool error"
            }
            yield AgentEvent(
                kind=AgentEventKind.TOOL_RESULT,
                session_id=session_id,
                turn_id=turn_id,
                tool_name=tool_name,
                tool_output=payload,
                tool_call_id=tool_call_id,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": _compact_json(payload),
                    "is_error": outcome.kind == "error",
                }
            )

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if approval_pending:
            # Pause the turn — caller will resume with approvals populated.
            return

    logger.warning("agent turn hit MAX_TOOL_LOOPS=%d", MAX_TOOL_LOOPS)


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an Anthropic content block into the dict shape the API
    expects on a subsequent turn."""
    if isinstance(block, dict):
        return block
    btype = getattr(block, "type", "text")
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": dict(getattr(block, "input", {}) or {}),
        }
    # Unknown block type — pass through defensively.
    return {"type": btype}


def _compact_json(payload: dict[str, Any]) -> str:
    """Render a tool result as a compact JSON string for the model."""
    import json

    def _default(o: Any) -> Any:
        return str(o)

    return json.dumps(payload, default=_default, separators=(",", ":"))


__all__ = [
    "MAX_TOOL_LOOPS",
    "ToolRouter",
    "default_tool_router",
    "run_agent_turn",
]
