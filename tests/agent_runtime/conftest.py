"""Shared fixtures for agent-runtime tests.

These fakes deliberately avoid any network I/O. The Anthropic client is
faked via a small stub that implements just the ``messages.stream``
surface the runtime calls; the Amadeus driver is stubbed through the
``FareSearchDriver`` / ``PNRDriver`` protocols.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from schemas.canonical import (
    ActorKind,
    CabinClass,
    Fare,
    Money,
    PNR,
    PNRStatus,
)

from voyagent_agent_runtime.anthropic_client import AnthropicClient
from voyagent_agent_runtime.drivers import DriverRegistry
from voyagent_agent_runtime.session import InMemorySessionStore, Session
from voyagent_agent_runtime.tools import (
    DRIVER_REGISTRY_KEY,
    InMemoryAuditSink,
    ToolContext,
)


# --------------------------------------------------------------------------- #
# Ids                                                                         #
# --------------------------------------------------------------------------- #


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


@pytest.fixture
def new_id() -> Callable[[], str]:
    return _uuid7_like


# --------------------------------------------------------------------------- #
# Anthropic stream fakes                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class FakeTextDelta:
    text: str
    type: str = "text_delta"


@dataclass
class FakeContentBlockDelta:
    delta: FakeTextDelta
    type: str = "content_block_delta"
    index: int = 0


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class FakeFinalMessage:
    stop_reason: str
    content: list[Any] = field(default_factory=list)


@dataclass
class FakeMessageStop:
    message: FakeFinalMessage
    type: str = "message_stop"


class FakeStream:
    """Async context manager yielding a pre-scripted sequence of events."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[Any]:
        for ev in self._events:
            yield ev


class FakeMessages:
    """Stand-in for ``anthropic.AsyncAnthropic().messages``."""

    def __init__(self, scripts: list[list[Any]]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        if not self._scripts:
            raise AssertionError("FakeMessages: no more scripted streams.")
        script = self._scripts.pop(0)
        return FakeStream(script)


class FakeAnthropic:
    """Plugs into :class:`AnthropicClient` in place of ``AsyncAnthropic``."""

    def __init__(self, scripts: list[list[Any]]) -> None:
        self.messages = FakeMessages(scripts)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def make_script_text_then_stop(text: str) -> list[Any]:
    """One assistant turn: emit ``text``, stop with ``end_turn``."""
    msg = FakeFinalMessage(
        stop_reason="end_turn",
        content=[FakeTextBlock(text=text)],
    )
    return [
        FakeContentBlockDelta(delta=FakeTextDelta(text=text)),
        FakeMessageStop(message=msg),
    ]


def make_script_tool_use(
    tool_name: str, tool_input: dict[str, Any], *, tool_id: str = "toolu_1"
) -> list[Any]:
    """One assistant turn that ends with a single tool_use block."""
    msg = FakeFinalMessage(
        stop_reason="tool_use",
        content=[FakeToolUseBlock(id=tool_id, name=tool_name, input=dict(tool_input))],
    )
    return [FakeMessageStop(message=msg)]


@pytest.fixture
def fake_anthropic_factory() -> Callable[[list[list[Any]]], AnthropicClient]:
    """Build an :class:`AnthropicClient` pre-loaded with scripted streams."""

    def _build(scripts: list[list[Any]]) -> AnthropicClient:
        fake = FakeAnthropic(scripts)
        # Inject a minimal settings object with no real API key.
        from voyagent_agent_runtime.anthropic_client import Settings

        settings = Settings(
            agent_model="claude-sonnet-4-5-test",
            agent_max_tokens=512,
        )
        return AnthropicClient(settings, client=fake)

    return _build


# --------------------------------------------------------------------------- #
# Audit                                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def memory_audit_sink() -> InMemoryAuditSink:
    return InMemoryAuditSink()


# --------------------------------------------------------------------------- #
# Session factory                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def make_session() -> Callable[..., Session]:
    def _factory(
        *,
        tenant_id: str | None = None,
        actor_id: str | None = None,
    ) -> Session:
        return Session(
            id=_uuid7_like(),
            tenant_id=tenant_id or _uuid7_like(),
            actor_id=actor_id or _uuid7_like(),
            actor_kind=ActorKind.HUMAN,
        )

    return _factory


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


# --------------------------------------------------------------------------- #
# Stub Amadeus-shaped driver                                                  #
# --------------------------------------------------------------------------- #


class StubAmadeus:
    """Implements :class:`FareSearchDriver` + :class:`PNRDriver` without network."""

    name = "stub_amadeus"
    version = "0.0.1"

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self.search_calls: list[Any] = []
        self.read_calls: list[str] = []
        self.issue_calls: list[str] = []

    def manifest(self) -> Any:  # pragma: no cover — unused in these tests
        raise NotImplementedError

    async def search(self, criteria: Any) -> list[Fare]:
        self.search_calls.append(criteria)
        now = datetime.now(timezone.utc)
        fare = Fare(
            id=_uuid7_like(),
            tenant_id=self._tenant_id,
            itinerary_id=_uuid7_like(),
            passenger_id=_uuid7_like(),
            base=Money(amount=Decimal("10000"), currency="INR"),
            total=Money(amount=Decimal("18500"), currency="INR"),
            source="stub_amadeus",
            source_ref="OFFER-42",
            valid_until=now,
        )
        return [fare]

    async def read(self, locator: str) -> PNR:
        self.read_calls.append(locator)
        now = datetime.now(timezone.utc)
        return PNR(
            id=_uuid7_like(),
            tenant_id=self._tenant_id,
            locator=locator,
            source="stub_amadeus",
            status=PNRStatus.CONFIRMED,
            passenger_ids=[_uuid7_like()],
            segment_ids=[_uuid7_like()],
            fare_ids=[_uuid7_like()],
            created_at=now,
            updated_at=now,
        )

    async def issue_ticket(self, pnr_id: str) -> list[Any]:
        from drivers._contracts.errors import CapabilityNotSupportedError

        self.issue_calls.append(pnr_id)
        raise CapabilityNotSupportedError(
            self.name,
            "Stub driver does not support ticket issuance.",
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def stub_amadeus(make_session: Callable[..., Session]) -> StubAmadeus:
    return StubAmadeus(tenant_id=_uuid7_like())


@pytest.fixture
def driver_registry(stub_amadeus: StubAmadeus) -> DriverRegistry:
    reg = DriverRegistry()
    reg.register("FareSearchDriver", stub_amadeus)
    reg.register("PNRDriver", stub_amadeus)
    return reg


@pytest.fixture
def tool_context(
    make_session: Callable[..., Session], driver_registry: DriverRegistry
) -> ToolContext:
    sess = make_session()
    return ToolContext(
        tenant_id=sess.tenant_id,
        actor_id=sess.actor_id,
        actor_kind=ActorKind.HUMAN,
        session_id=sess.id,
        turn_id="t-testturn000",
        approvals={},
        extensions={DRIVER_REGISTRY_KEY: driver_registry},
    )
