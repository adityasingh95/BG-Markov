"""add hypo_rescue_log — the independent INV-7 ledger

Revision ID: a1b2c3d4e5f6
Revises: 952724218c0f
Create Date: 2026-07-15 16:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '952724218c0f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # meal_id is deliberately a plain column, NOT a ForeignKey: the ledger must
    # survive a meal-row deletion so INV-7 can reconcile against it (S-305).
    op.create_table(
        'hypo_rescue_log',
        sa.Column('rescue_id', sa.Integer(), nullable=False),
        sa.Column('meal_id', sa.Integer(), nullable=False),
        sa.Column('grams', sa.Float(), nullable=True),
        sa.Column('logged_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('rescue_id'),
    )


def downgrade() -> None:
    op.drop_table('hypo_rescue_log')
