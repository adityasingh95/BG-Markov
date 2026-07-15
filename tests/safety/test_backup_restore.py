"""S-304 [SAFETY] — backup + restore drill (SDET, written RED first).

Data loss is the top failure mode. An untested backup is not a backup: these
prove the live DB stays out of the sync path, the snapshot is consistent even
during a write, and the restore is faithful.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from cli.backup import SyncedFolderError, backup, export_csv, is_synced_folder
from cli.restore_drill import run_restore_drill
from data.db import create_all, make_engine, session_factory
from data.tables import LoggedBy, MealEvent, MealType


def _make_db(path: Path, n: int = 3) -> None:
    """A real app.db with `n` committed meals."""
    engine = make_engine(f"sqlite:///{path}")
    create_all(engine)
    factory = session_factory(engine)
    with factory() as s:
        for i in range(n):
            when = dt.datetime(2026, 2, 1, 8, 0) + dt.timedelta(days=i)
            s.add(MealEvent(
                datetime=when, logged_at=when, logged_by=LoggedBy.patient,
                meal_type=MealType.breakfast, pre_bg=120, pre_bg_time=when,
                meal_bolus_units=5.0, bolus_offset_min=-10, carbs_g=40.0,
            ))
        s.commit()
    engine.dispose()


def test_live_db_in_a_synced_folder_is_rejected(tmp_path: Path) -> None:
    """REQ-050: app.db must never live in a cloud-synced folder."""
    assert is_synced_folder(str(tmp_path / "Dropbox" / "app.db")) is True
    assert is_synced_folder(str(tmp_path / "Google Drive" / "app.db")) is True
    assert is_synced_folder(str(tmp_path / "bgapp" / "app.db")) is False

    synced = tmp_path / "Dropbox" / "app.db"
    synced.parent.mkdir(parents=True)
    _make_db(synced)
    with pytest.raises(SyncedFolderError):
        backup(str(synced), str(tmp_path / "snap.db"))


def test_backup_during_an_active_write_is_valid(tmp_path: Path) -> None:
    """REQ-050: the online backup takes a consistent, valid snapshot while a
    writer holds an open (uncommitted) transaction."""
    db = tmp_path / "bgapp" / "app.db"
    db.parent.mkdir(parents=True)
    _make_db(db, n=3)

    engine = make_engine(f"sqlite:///{db}")
    factory = session_factory(engine)
    writer = factory()
    when = dt.datetime(2026, 3, 1, 8, 0)
    writer.add(MealEvent(
        datetime=when, logged_at=when, logged_by=LoggedBy.patient,
        meal_type=MealType.lunch, pre_bg=130, pre_bg_time=when,
        meal_bolus_units=6.0, bolus_offset_min=-15, carbs_g=50.0,
    ))
    writer.flush()  # sends the INSERT, holds a write transaction — NOT committed

    snap = tmp_path / "backup" / "snap.db"
    backup(str(db), str(snap))

    writer.rollback()
    writer.close()
    engine.dispose()

    conn = sqlite3.connect(snap)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # the uncommitted 4th meal is NOT in the consistent snapshot
        assert conn.execute("SELECT count(*) FROM meal_event").fetchone()[0] == 3
    finally:
        conn.close()


def test_restore_drill_is_ok_and_faithful(tmp_path: Path) -> None:
    """The restore is valid, byte-identical to the snapshot, and data-identical
    to the source."""
    db = tmp_path / "bgapp" / "app.db"
    db.parent.mkdir(parents=True)
    _make_db(db, n=5)

    result = run_restore_drill(str(db), str(tmp_path / "drill"))
    assert result.integrity_ok is True
    assert result.identical is True
    assert result.ok is True
    assert result.tables["meal_event"] == 5


def test_export_writes_a_csv_per_table_with_headers(tmp_path: Path) -> None:
    """REQ-052: nightly CSV — one file per table, header + rows."""
    db = tmp_path / "bgapp" / "app.db"
    db.parent.mkdir(parents=True)
    _make_db(db, n=2)

    out = tmp_path / "export"
    written = export_csv(str(db), str(out))
    names = {p.name for p in written}
    assert "meal_event.csv" in names

    lines = (out / "meal_event.csv").read_text(encoding="utf-8").splitlines()
    assert "meal_id" in lines[0]  # header
    assert len(lines) == 3  # header + 2 rows
