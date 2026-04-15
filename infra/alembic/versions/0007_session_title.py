"""sessions.title column

Revision ID: 0007_session_title
Revises: 0006_enquiries
Create Date: 2026-04-14

Adds a nullable ``title`` column to the ``sessions`` table. The API
populates it from the first user message in a session (first 60 chars).
Pre-existing sessions keep ``NULL`` and the web sidebar renders a
"New chat" fallback.

Idempotent + reversible.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_session_title"
down_revision: str | None = "0006_enquiries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(
    bind: sa.engine.Connection, table: str, column: str
) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "sessions", "title"):
        op.add_column(
            "sessions",
            sa.Column("title", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "sessions", "title"):
        op.drop_column("sessions", "title")
