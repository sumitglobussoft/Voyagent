"""Hotels-holidays tool handler tests — exercise them directly against a stub.

Uses the same fake-driver + invoke_tool pattern as test_ticketing_visa,
so the test does not require a real TBO account.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from schemas.canonical import (
    ActorKind,
    BoardBasis,
    HotelBooking,
    HotelBookingStatus,
    HotelProperty,
    HotelRate,
    HotelRoom,
    HotelSearchResult,
    Money,
)

from voyagent_agent_runtime.drivers import DriverRegistry
from voyagent_agent_runtime.tools import (
    DRIVER_REGISTRY_KEY,
    InMemoryAuditSink,
    ToolContext,
    invoke_tool,
)

pytestmark = pytest.mark.asyncio


def _uuid7_like() -> str:
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


class StubHotelDriver:
    """Implements HotelSearchDriver + HotelBookingDriver structurally.

    Satisfies :func:`search_results` (preferred by the tool layer)
    and :func:`check_rate`. ``book`` is configurable: by default it
    raises :class:`CapabilityNotSupportedError` to match the v0 TBO
    driver, which is what the agent surfaces to the user.
    """

    name = "stub_tbo"
    version = "0.0.1"

    def __init__(self) -> None:
        self.search_calls: list[Any] = []
        self.check_rate_calls: list[str] = []
        self.book_calls: list[tuple[str, Any]] = []
        self.cancel_calls: list[str] = []
        self.read_calls: list[str] = []
        self.book_should_succeed: bool = True

    def manifest(self) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def search_results(self, criteria: Any) -> list[HotelSearchResult]:
        self.search_calls.append(criteria)
        room = HotelRoom(
            code="DLX",
            name="Deluxe King",
            board_basis=BoardBasis.BB,
            max_occupancy=2,
            bed_type="king",
        )
        rate = HotelRate(
            room=room,
            price=Money(amount=Decimal("12500.00"), currency="INR"),
            is_refundable=True,
            rate_key="rk-abc-123",
        )
        prop = HotelProperty(
            id="tbo-1001",
            name="Taj Palace",
            city="DEL",
            country="IN",
            star_rating=5,
        )
        return [
            HotelSearchResult(
                property=prop,
                rates=[rate],
                check_in=criteria.check_in,
                check_out=criteria.check_out,
                guest_count=criteria.guest_count,
            )
        ]

    async def search(self, criteria: Any) -> list[Any]:  # pragma: no cover
        return []

    async def check_rate(self, rate_key: str) -> HotelRate:
        self.check_rate_calls.append(rate_key)
        room = HotelRoom(
            code="DLX",
            name="Deluxe King",
            board_basis=BoardBasis.BB,
            max_occupancy=2,
        )
        return HotelRate(
            room=room,
            price=Money(amount=Decimal("12750.00"), currency="INR"),
            is_refundable=True,
            rate_key=rate_key,
        )

    async def book(self, offer_ref: str, stay: Any) -> HotelBooking:
        self.book_calls.append((offer_ref, stay))
        if not self.book_should_succeed:
            from drivers._contracts.errors import CapabilityNotSupportedError

            raise CapabilityNotSupportedError(
                self.name, "Stub driver booking disabled for this test."
            )
        now = datetime.now(timezone.utc)
        return HotelBooking(
            id=_uuid7_like(),
            tenant_id=_uuid7_like(),
            stay_id=_uuid7_like(),
            supplier=self.name,
            supplier_ref="TBO-CONF-42",
            status=HotelBookingStatus.CONFIRMED,
            cost=Money(amount=Decimal("12750.00"), currency="INR"),
            currency="INR",
            selected_rate_key=offer_ref,
            created_at=now,
            updated_at=now,
        )

    async def cancel(self, booking_id: str) -> HotelBooking:  # pragma: no cover
        self.cancel_calls.append(booking_id)
        now = datetime.now(timezone.utc)
        return HotelBooking(
            id=booking_id,
            tenant_id=_uuid7_like(),
            stay_id=_uuid7_like(),
            supplier=self.name,
            supplier_ref="TBO-CONF-42",
            status=HotelBookingStatus.CANCELLED,
            cost=Money(amount=Decimal("12750.00"), currency="INR"),
            currency="INR",
            created_at=now,
            updated_at=now,
        )

    async def read(self, booking_id: str) -> HotelBooking:  # pragma: no cover
        self.read_calls.append(booking_id)
        now = datetime.now(timezone.utc)
        return HotelBooking(
            id=booking_id,
            tenant_id=_uuid7_like(),
            stay_id=_uuid7_like(),
            supplier=self.name,
            supplier_ref="TBO-CONF-42",
            status=HotelBookingStatus.CONFIRMED,
            cost=Money(amount=Decimal("12750.00"), currency="INR"),
            currency="INR",
            created_at=now,
            updated_at=now,
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def stub_hotel() -> StubHotelDriver:
    return StubHotelDriver()


@pytest.fixture
def hotel_tool_context(stub_hotel: StubHotelDriver) -> ToolContext:
    registry = DriverRegistry()
    registry.register("HotelSearchDriver", stub_hotel)
    registry.register("HotelBookingDriver", stub_hotel)
    return ToolContext(
        tenant_id=_uuid7_like(),
        actor_id=_uuid7_like(),
        actor_kind=ActorKind.HUMAN,
        session_id=_uuid7_like(),
        turn_id="t-hoteltest0",
        actor_role="agency_admin",
        approvals={},
        extensions={DRIVER_REGISTRY_KEY: registry},
    )


# --------------------------------------------------------------------------- #
# search_hotels                                                               #
# --------------------------------------------------------------------------- #


async def test_search_hotels_produces_compact_summaries(
    hotel_tool_context: ToolContext, stub_hotel: StubHotelDriver
) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "search_hotels",
        {
            "country": "IN",
            "city": "DEL",
            "check_in": "2026-05-10",
            "check_out": "2026-05-12",
            "guests": 2,
        },
        hotel_tool_context,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    assert outcome.output is not None
    assert outcome.output["count"] == 1
    result = outcome.output["results"][0]
    assert result["name"] == "Taj Palace"
    assert result["rate_keys"][0] == "rk-abc-123"
    assert sink.events == []  # read-only
    assert len(stub_hotel.search_calls) == 1


# --------------------------------------------------------------------------- #
# check_hotel_rate                                                            #
# --------------------------------------------------------------------------- #


async def test_check_hotel_rate_reprices_rate(
    hotel_tool_context: ToolContext, stub_hotel: StubHotelDriver
) -> None:
    sink = InMemoryAuditSink()
    outcome = await invoke_tool(
        "check_hotel_rate",
        {"rate_key": "rk-abc-123"},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert outcome.kind == "success"
    assert outcome.output["checked"] is True
    assert outcome.output["rate_key"] == "rk-abc-123"
    assert "INR" in outcome.output["price"]
    assert stub_hotel.check_rate_calls == ["rk-abc-123"]


# --------------------------------------------------------------------------- #
# book_hotel — approval gating                                                #
# --------------------------------------------------------------------------- #


async def test_book_hotel_is_gated_by_approval(
    hotel_tool_context: ToolContext, stub_hotel: StubHotelDriver
) -> None:
    sink = InMemoryAuditSink()
    first = await invoke_tool(
        "book_hotel",
        {"rate_key": "rk-abc-123", "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert first.kind == "approval_needed"
    # Handler was never called without approval.
    assert stub_hotel.book_calls == []


async def test_book_hotel_rejected_approval_does_not_book(
    hotel_tool_context: ToolContext, stub_hotel: StubHotelDriver
) -> None:
    sink = InMemoryAuditSink()
    first = await invoke_tool(
        "book_hotel",
        {"rate_key": "rk-abc-123", "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    hotel_tool_context.approvals = {first.approval_id: False}
    second = await invoke_tool(
        "book_hotel",
        {"rate_key": "rk-abc-123", "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert second.kind == "error"
    assert "Approval denied" in (second.error_message or "")
    assert stub_hotel.book_calls == []


async def test_book_hotel_after_approval_surfaces_not_supported(
    hotel_tool_context: ToolContext, stub_hotel: StubHotelDriver
) -> None:
    """With the v0 TBO driver, ``book`` raises CapabilityNotSupportedError;
    the tool layer surfaces it as a structured result rather than crashing."""
    stub_hotel.book_should_succeed = False
    sink = InMemoryAuditSink()
    first = await invoke_tool(
        "book_hotel",
        {"rate_key": "rk-abc-123", "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    hotel_tool_context.approvals = {first.approval_id: True}
    second = await invoke_tool(
        "book_hotel",
        {"rate_key": "rk-abc-123", "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert second.kind == "success"
    assert second.output["booked"] is False
    assert second.output["reason"] == "capability_not_supported"


# --------------------------------------------------------------------------- #
# end-to-end: search → check_rate → book                                      #
# --------------------------------------------------------------------------- #


async def test_full_search_check_book_flow_in_order(
    hotel_tool_context: ToolContext, stub_hotel: StubHotelDriver
) -> None:
    sink = InMemoryAuditSink()

    search_out = await invoke_tool(
        "search_hotels",
        {
            "country": "IN",
            "city": "DEL",
            "check_in": "2026-05-10",
            "check_out": "2026-05-12",
            "guests": 2,
        },
        hotel_tool_context,
        audit_sink=sink,
    )
    assert search_out.kind == "success"
    rate_key = search_out.output["results"][0]["rate_keys"][0]

    check_out = await invoke_tool(
        "check_hotel_rate",
        {"rate_key": rate_key},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert check_out.kind == "success"

    approval_req = await invoke_tool(
        "book_hotel",
        {"rate_key": rate_key, "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert approval_req.kind == "approval_needed"

    hotel_tool_context.approvals = {approval_req.approval_id: True}
    booked = await invoke_tool(
        "book_hotel",
        {"rate_key": rate_key, "passenger_ids": ["pax-1"]},
        hotel_tool_context,
        audit_sink=sink,
    )
    assert booked.kind == "success"
    assert booked.output["booked"] is True
    assert booked.output["status"] == HotelBookingStatus.CONFIRMED
    assert len(stub_hotel.search_calls) == 1
    assert stub_hotel.check_rate_calls == [rate_key]
    assert len(stub_hotel.book_calls) == 1
