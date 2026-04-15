"""Per-turn Anthropic usage + cost record.

One row per chat turn. Enables day-windowed tenant cost rollups for the
daily-budget enforcement path and session-level totals for the UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index, Integer, Numeric, String, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDType, tenant_id_fk, uuid_pk


class SessionCostRow(Base):
    """Cost + token usage for a single agent turn.

    ``tenant_id`` is stored directly on the row (not just via session FK)
    so the per-day tenant rollup is a single indexed scan — avoids a
    join on every turn-start budget check.
    """

    __tablename__ = "session_costs"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_id_fk()
    session_id: Mapped[uuid.UUID] = mapped_column(UUIDType(), nullable=False)
    turn_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 8), nullable=False, default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_session_costs_tenant_created", "tenant_id", "created_at"),
        Index("ix_session_costs_session_id", "session_id"),
    )


__all__ = ["SessionCostRow"]
