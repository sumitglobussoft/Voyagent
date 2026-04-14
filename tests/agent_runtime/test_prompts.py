"""Static checks on the agent system prompts.

The prompts are plain Python constants exported from
:mod:`voyagent_agent_runtime.prompts`. These tests guard against three
classes of regression:

  * A prompt is accidentally emptied (e.g. a refactor collapses to "").
  * A domain-specific prompt forgets to mention its domain.
  * A stale prompt references vendors we've explicitly moved away from
    (Clerk auth, Temporal workflows) or carries ``TODO``/``FIXME``
    markers into production.
"""

from __future__ import annotations

import pytest

from voyagent_agent_runtime.prompts import (
    ACCOUNTING_SYSTEM_PROMPT,
    HOTELS_HOLIDAYS_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    TICKETING_VISA_SYSTEM_PROMPT,
)


_ALL_PROMPTS = {
    "orchestrator": ORCHESTRATOR_SYSTEM_PROMPT,
    "ticketing_visa": TICKETING_VISA_SYSTEM_PROMPT,
    "hotels_holidays": HOTELS_HOLIDAYS_SYSTEM_PROMPT,
    "accounting": ACCOUNTING_SYSTEM_PROMPT,
}


@pytest.mark.parametrize("name,prompt", list(_ALL_PROMPTS.items()))
def test_prompt_is_non_empty(name: str, prompt: str) -> None:
    assert prompt is not None
    assert prompt.strip() != "", f"{name} prompt is blank"
    assert len(prompt) > 50, f"{name} prompt suspiciously short ({len(prompt)} chars)"


def test_ticketing_prompt_mentions_flight_domain() -> None:
    lower = TICKETING_VISA_SYSTEM_PROMPT.lower()
    assert "flight" in lower or "ticket" in lower
    assert "pnr" in lower


def test_hotels_prompt_mentions_hotel_domain() -> None:
    assert "hotel" in HOTELS_HOLIDAYS_SYSTEM_PROMPT.lower()


def test_accounting_prompt_mentions_accounting_domain() -> None:
    lower = ACCOUNTING_SYSTEM_PROMPT.lower()
    assert "accounting" in lower or "ledger" in lower or "invoice" in lower


@pytest.mark.parametrize("name,prompt", list(_ALL_PROMPTS.items()))
def test_prompt_has_no_todo_or_fixme_markers(name: str, prompt: str) -> None:
    upper = prompt.upper()
    assert "TODO" not in upper, f"{name} prompt leaks a TODO marker"
    assert "FIXME" not in upper, f"{name} prompt leaks a FIXME marker"
    assert "XXX" not in upper, f"{name} prompt leaks an XXX marker"


@pytest.mark.parametrize("name,prompt", list(_ALL_PROMPTS.items()))
def test_prompt_does_not_reference_removed_vendors(name: str, prompt: str) -> None:
    """Voyagent moved off Clerk (auth) and Temporal (workflow) — a
    stale prompt mentioning either is almost certainly a drift bug."""
    lower = prompt.lower()
    assert "clerk" not in lower, f"{name} prompt still mentions Clerk"
    assert "temporal" not in lower, f"{name} prompt still mentions Temporal"


@pytest.mark.parametrize("name,prompt", list(_ALL_PROMPTS.items()))
def test_prompt_avoids_naming_specific_gds_vendors(name: str, prompt: str) -> None:
    """Prompts must stay driver-agnostic per the project rules."""
    lower = prompt.lower()
    for vendor in ("amadeus", "sabre", "galileo", "travelport", "tally"):
        assert vendor not in lower, (
            f"{name} prompt references vendor {vendor!r} — must stay agnostic"
        )
