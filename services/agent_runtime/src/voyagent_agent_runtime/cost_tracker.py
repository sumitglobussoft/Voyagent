"""Per-turn cost accounting.

The Anthropic SDK exposes ``response.usage.input_tokens`` +
``output_tokens`` on the final message of a stream. We fold each turn
into a :class:`TurnCost` record and persist it; the orchestrator
calls :meth:`CostTracker.record` after the agent loop returns and
:meth:`total_for_tenant_today` before starting the next turn so the
daily-budget enforcement path runs in O(1) tenant day-window scans.

Pricing is hardcoded per-model in :data:`MODEL_PRICING` (USD per
1M tokens). Unknown models resolve to zero cost with a warning — the
record still lands so token counts remain auditable.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# USD per 1,000,000 tokens. Approximate Anthropic pricing as of 2026-04.
# (input, output) pairs.
MODEL_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-4-5": (Decimal("3"), Decimal("15")),
    "claude-opus-4-6": (Decimal("15"), Decimal("75")),
    "claude-haiku-4-5-20251001": (Decimal("0.80"), Decimal("4")),
}


_ONE_MILLION = Decimal("1000000")


class DailyBudgetExceededError(Exception):
    """Raised when a tenant's daily token spend exceeds the configured cap."""

    def __init__(self, tenant_id: str, limit: int, used: int) -> None:
        super().__init__(
            f"daily_budget_exceeded: tenant={tenant_id} limit={limit} used={used}"
        )
        self.tenant_id = tenant_id
        self.limit = limit
        self.used = used


@dataclass(frozen=True)
class TurnCost:
    """One persisted cost record for a single agent turn."""

    session_id: str
    turn_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    created_at: datetime
    tenant_id: str = ""


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> Decimal:
    """Compute USD cost from per-million pricing.

    Unknown models log a warning and resolve to ``Decimal("0")`` — the
    caller still records the turn so token accounting remains intact.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning(
            "cost_tracker: unknown model %s — resolving to $0", model
        )
        return Decimal("0")
    in_rate, out_rate = pricing
    cost = (
        Decimal(input_tokens) * in_rate + Decimal(output_tokens) * out_rate
    ) / _ONE_MILLION
    # Quantise to 8 decimals to match the storage Numeric(14,8) column.
    return cost.quantize(Decimal("0.00000001"))


def build_turn_cost(
    *,
    tenant_id: str,
    session_id: str,
    turn_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    created_at: datetime | None = None,
) -> TurnCost:
    """Factory that computes ``cost_usd`` via :func:`estimate_cost_usd`."""
    return TurnCost(
        tenant_id=tenant_id,
        session_id=session_id,
        turn_id=turn_id,
        model=model,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
        created_at=created_at or datetime.now(timezone.utc),
    )


class CostTracker(Protocol):
    async def record(self, cost: TurnCost) -> None: ...
    async def total_for_session(self, session_id: str) -> Decimal: ...
    async def total_for_tenant_today(self, tenant_id: str) -> Decimal: ...
    async def tokens_for_tenant_today(self, tenant_id: str) -> int: ...


class InMemoryCostTracker:
    """Process-local tracker for tests and single-process dev loops."""

    def __init__(self, *, clock=None) -> None:
        self._rows: list[TurnCost] = []
        self._lock = asyncio.Lock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def record(self, cost: TurnCost) -> None:
        async with self._lock:
            self._rows.append(cost)

    async def total_for_session(self, session_id: str) -> Decimal:
        async with self._lock:
            return sum(
                (r.cost_usd for r in self._rows if r.session_id == session_id),
                Decimal("0"),
            )

    def _today(self) -> date:
        return self._clock().astimezone(timezone.utc).date()

    async def total_for_tenant_today(self, tenant_id: str) -> Decimal:
        today = self._today()
        async with self._lock:
            return sum(
                (
                    r.cost_usd
                    for r in self._rows
                    if r.tenant_id == tenant_id
                    and r.created_at.astimezone(timezone.utc).date() == today
                ),
                Decimal("0"),
            )

    async def tokens_for_tenant_today(self, tenant_id: str) -> int:
        today = self._today()
        async with self._lock:
            return sum(
                (r.input_tokens + r.output_tokens)
                for r in self._rows
                if r.tenant_id == tenant_id
                and r.created_at.astimezone(timezone.utc).date() == today
            )

    def all_rows(self) -> list[TurnCost]:
        """Test helper — a snapshot of the in-memory ledger."""
        return list(self._rows)


class StorageCostTracker:
    """SQLAlchemy-backed tracker that writes to ``session_costs``."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def record(self, cost: TurnCost) -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from schemas.storage import SessionCostRow

        sm = async_sessionmaker(self._engine, expire_on_commit=False)
        async with sm() as db:
            async with db.begin():
                db.add(
                    SessionCostRow(
                        tenant_id=uuid.UUID(cost.tenant_id),
                        session_id=uuid.UUID(cost.session_id),
                        turn_id=cost.turn_id,
                        model=cost.model,
                        input_tokens=cost.input_tokens,
                        output_tokens=cost.output_tokens,
                        total_tokens=cost.input_tokens + cost.output_tokens,
                        cost_usd=cost.cost_usd,
                        created_at=cost.created_at,
                    )
                )

    async def total_for_session(self, session_id: str) -> Decimal:
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from schemas.storage import SessionCostRow

        sm = async_sessionmaker(self._engine, expire_on_commit=False)
        async with sm() as db:
            total = (
                await db.execute(
                    select(func.coalesce(func.sum(SessionCostRow.cost_usd), 0))
                    .where(SessionCostRow.session_id == uuid.UUID(session_id))
                )
            ).scalar_one()
        return Decimal(str(total or 0))

    async def total_for_tenant_today(self, tenant_id: str) -> Decimal:
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from schemas.storage import SessionCostRow

        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sm = async_sessionmaker(self._engine, expire_on_commit=False)
        async with sm() as db:
            total = (
                await db.execute(
                    select(func.coalesce(func.sum(SessionCostRow.cost_usd), 0))
                    .where(SessionCostRow.tenant_id == uuid.UUID(tenant_id))
                    .where(SessionCostRow.created_at >= start)
                )
            ).scalar_one()
        return Decimal(str(total or 0))

    async def tokens_for_tenant_today(self, tenant_id: str) -> int:
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from schemas.storage import SessionCostRow

        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sm = async_sessionmaker(self._engine, expire_on_commit=False)
        async with sm() as db:
            total = (
                await db.execute(
                    select(func.coalesce(func.sum(SessionCostRow.total_tokens), 0))
                    .where(SessionCostRow.tenant_id == uuid.UUID(tenant_id))
                    .where(SessionCostRow.created_at >= start)
                )
            ).scalar_one()
        return int(total or 0)


async def enforce_daily_budget(
    tracker: CostTracker,
    tenant_id: str,
    budget_tokens: int | None,
) -> None:
    """Raise :class:`DailyBudgetExceededError` when already over quota."""
    if budget_tokens is None or budget_tokens <= 0:
        return
    used = await tracker.tokens_for_tenant_today(tenant_id)
    if used >= budget_tokens:
        raise DailyBudgetExceededError(tenant_id, budget_tokens, used)


__all__ = [
    "CostTracker",
    "DailyBudgetExceededError",
    "InMemoryCostTracker",
    "MODEL_PRICING",
    "StorageCostTracker",
    "TurnCost",
    "build_turn_cost",
    "enforce_daily_budget",
    "estimate_cost_usd",
]
