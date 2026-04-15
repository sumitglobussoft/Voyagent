"""pending_approvals: payload + resolved_by_user_id columns

Revision ID: 0011_approvals_payload
Revises: 0010_totp_and_api_keys
Create Date: 2026-04-14

Adds two columns to ``pending_approvals`` so the /approvals HTTP
surface can faithfully return the raw tool-call args + the user who
resolved the row:

* ``payload``           JSONB NOT NULL DEFAULT '{}'
* ``resolved_by_user_id`` UUID NULL FK -> users(id)

Existing rows are backfilled with ``payload = '{}'`` and
``resolved_by_user_id = NULL``. The agent runtime will populate
``payload`` on write once its own code path lands — the API side
simply plumbs whatever is stored.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011_approvals_payload"
down_revision: str | None = "0010_totp_and_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pending_approvals",
        sa.Column(
            "payload",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "pending_approvals",
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pending_approvals", "resolved_by_user_id")
    op.drop_column("pending_approvals", "payload")
