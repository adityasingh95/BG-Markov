"""s1024 data provenance

Revision ID: d3a7c1f8b204
Revises: c7e1a09b4d22
Create Date: 2026-07-31 19:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd3a7c1f8b204'
down_revision: str | None = 'c7e1a09b4d22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `data_provenance` — what kind of data this database holds (S-1024).

    ★ In the DATABASE rather than the environment, because an env var can be forgotten,
    inherited or left over from a previous run, and the mistake is silent in both
    directions. A row travels with the file.

    Nothing is backfilled. An existing database is not asserted to be either kind: absence
    means *not marked*, and inventing a claim about data this migration has never seen is
    exactly the fabricated provenance S-1016 and S-1019 refused to write.
    """
    op.create_table(
        "data_provenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("data_provenance")
