"""s1016 meal idempotency key

Revision ID: 4fc9946a6a7a
Revises: 779c8215c0b3
Create Date: 2026-07-30 14:49:02.314699
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '4fc9946a6a7a'
down_revision: str | None = '779c8215c0b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `meal_event.idempotency_key`, UNIQUE and nullable (S-1016, DL-055).

    Nullable on purpose: every meal recorded before this story has no key, and backfilling
    invented ones would fabricate provenance. SQLite (like the SQL standard) treats NULLs as
    distinct in a UNIQUE index, so any number of historical rows coexist.

    UNIQUE at the database rather than checked in Python, because a read-then-insert races —
    and one submission producing two rows also produces two BOLUS rows, which corrupts IOB
    for hours and makes the calculator under-dose her.
    """
    op.add_column("meal_event", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_index(
        "ix_meal_event_idempotency_key", "meal_event", ["idempotency_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_meal_event_idempotency_key", table_name="meal_event")
    op.drop_column("meal_event", "idempotency_key")

