"""s1019 correction event idempotency key

Revision ID: c7e1a09b4d22
Revises: 4fc9946a6a7a
Create Date: 2026-07-30 19:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7e1a09b4d22'
down_revision: str | None = '4fc9946a6a7a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `correction_event.idempotency_key`, UNIQUE and nullable (S-1019).

    The same shape as S-1016's meal key, for the same reason: a correction writes a
    `bolus_log` row, `bolus_log` is the sole source of IOB, and the calculator subtracts
    IOB. A duplicated correction under-doses her hours later with no error anywhere.

    Nullable because corrections recorded before this story have no key, and backfilling
    invented ones would fabricate provenance. NULLs are distinct in a UNIQUE index, so any
    number of historical rows coexist.
    """
    op.add_column(
        "correction_event", sa.Column("idempotency_key", sa.String(), nullable=True)
    )
    op.create_index(
        "ix_correction_event_idempotency_key",
        "correction_event",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_correction_event_idempotency_key", table_name="correction_event")
    op.drop_column("correction_event", "idempotency_key")
