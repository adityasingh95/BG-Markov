"""S-306 — correction_event nullability for two-phase capture + deferred IOB.

`iob_at_start` is deferred to S-401 (backfilled by iob_at()); `bg_after` /
`bg_after_time` arrive at the +4 h follow-up, not at create. All three become
nullable. Written RED first — they are non-null in the S-201 schema.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect

from data.db import create_all, make_engine, session_factory
from data.tables import CorrectionEvent

_NULLABLE_NOW = ["iob_at_start", "bg_after", "bg_after_time"]


def test_deferred_columns_are_nullable_in_orm() -> None:
    for name in _NULLABLE_NOW:
        col = CorrectionEvent.__table__.c[name]
        assert col.nullable, f"correction_event.{name} must be nullable (S-306)"


def test_event_persists_with_deferred_columns_null(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'corr_schema.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        s.add(CorrectionEvent(
            datetime=datetime(2026, 7, 13, 10, 15),
            logged_at=datetime(2026, 7, 13, 14, 30),
            bg_before=210,
            units=2.0,
            food_in_window=False,
            # bg_after / bg_after_time / iob_at_start intentionally omitted (NULL)
        ))
        s.commit()
        ev = s.query(CorrectionEvent).one()
        assert ev.bg_after is None
        assert ev.bg_after_time is None
        assert ev.iob_at_start is None


def test_alembic_migration_makes_deferred_columns_nullable(tmp_path: Path) -> None:
    """The production DB is migrated: after `head`, the three columns are nullable."""
    from alembic.config import Config

    from alembic import command

    repo_root = Path(__file__).resolve().parents[2]
    db_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    cols = {c["name"]: c for c in inspect(make_engine(db_url)).get_columns("correction_event")}
    for name in _NULLABLE_NOW:
        assert cols[name]["nullable"], f"migration must make correction_event.{name} nullable"
