"""correction_event: defer iob_at_start + two-phase +4h reading (nullable)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 16:45:00.000000

iob_at_start is derived by S-401's iob_at() (deferred); bg_after / bg_after_time
arrive at the +4 h follow-up. All three become nullable. SQLite cannot ALTER a
column in place, so this uses Alembic's batch mode (table recreate).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLS = [
    ("iob_at_start", sa.Float()),
    ("bg_after", sa.Integer()),
    ("bg_after_time", sa.DateTime()),
]


def upgrade() -> None:
    with op.batch_alter_table("correction_event") as batch_op:
        for name, type_ in _COLS:
            batch_op.alter_column(name, existing_type=type_, nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("correction_event") as batch_op:
        for name, type_ in _COLS:
            batch_op.alter_column(name, existing_type=type_, nullable=False)
