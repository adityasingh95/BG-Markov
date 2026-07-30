"""s1014 fitted_model on model_artifact

Revision ID: 779c8215c0b3
Revises: b2c3d4e5f6a7
Create Date: 2026-07-30 11:21:19.312322
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '779c8215c0b3'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `model_artifact.fitted_model` (S-1014).

    Nullable, and it stays nullable: every artifact written before this story has no stored
    model, and those rows are real history. `load_fitted_model` returns None for them and
    the caller serves the clinical baseline — the same thing it already does when nothing is
    promoted. A NOT NULL with a default would fabricate a model for old rows.
    """
    op.add_column("model_artifact", sa.Column("fitted_model", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_artifact", "fitted_model")

