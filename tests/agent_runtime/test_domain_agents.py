"""Static contract tests for the three domain agents.

We assert each agent's ``tools`` attribute exactly — regressions that
quietly drop a tool or leak a tool into the wrong domain are the bug
these tests defend against. The sets must also be disjoint: each tool
belongs to exactly one domain agent in v0.
"""

from __future__ import annotations

from voyagent_agent_runtime.domain_agents import (
    AccountingAgent,
    HotelsHolidaysAgent,
    TicketingVisaAgent,
)
from voyagent_agent_runtime.tools import (
    ACCOUNTING_TOOL_NAMES,
    HOTELS_HOLIDAYS_TOOL_NAMES,
    TICKETING_VISA_TOOL_NAMES,
)


def test_ticketing_visa_tool_set_is_exact() -> None:
    assert TicketingVisaAgent.tools == TICKETING_VISA_TOOL_NAMES
    assert set(TicketingVisaAgent.tools) == {
        "search_flights",
        "read_pnr",
        "issue_ticket",
    }
    assert TicketingVisaAgent.name == "ticketing_visa"


def test_accounting_tool_set_is_exact() -> None:
    assert AccountingAgent.tools == ACCOUNTING_TOOL_NAMES
    assert set(AccountingAgent.tools) == {
        "list_ledger_accounts",
        "post_journal_entry",
        "create_invoice",
        "fetch_bsp_statement",
        "reconcile_bsp",
        "read_account_balance",
    }
    assert AccountingAgent.name == "accounting"


def test_hotels_holidays_tool_set_is_exact() -> None:
    assert HotelsHolidaysAgent.tools == HOTELS_HOLIDAYS_TOOL_NAMES
    assert set(HotelsHolidaysAgent.tools) == {
        "search_hotels",
        "check_hotel_rate",
        "book_hotel",
        "cancel_hotel_booking",
        "read_hotel_booking",
    }
    assert HotelsHolidaysAgent.name == "hotels_holidays"


def test_domain_agent_tool_sets_are_pairwise_disjoint() -> None:
    tv = set(TicketingVisaAgent.tools)
    acc = set(AccountingAgent.tools)
    hh = set(HotelsHolidaysAgent.tools)

    assert tv.isdisjoint(acc), tv & acc
    assert tv.isdisjoint(hh), tv & hh
    assert acc.isdisjoint(hh), acc & hh


def test_every_domain_tool_belongs_to_the_right_registry_domain() -> None:
    """The tool registry's ``domain`` metadata must line up with the
    agent that claims the tool. Prevents a tool from being placed on an
    agent but tagged with another domain in the registry."""
    from voyagent_agent_runtime.tools import get_tool

    for name in TicketingVisaAgent.tools:
        assert get_tool(name).spec.domain == "ticketing_visa", name
    for name in AccountingAgent.tools:
        assert get_tool(name).spec.domain == "accounting", name
    for name in HotelsHolidaysAgent.tools:
        assert get_tool(name).spec.domain == "hotels_holidays", name
