"""S-304 follow-up (audit N3) — smoke-test the `python -m cli` command surface.

The library functions (cli.backup / cli.restore_drill) are unit-tested and the
drill was run for real, but `cli/__main__.py` — the argparse dispatch the operator
actually types for the monthly drill — had 0% coverage. An arg-parsing regression
must not be able to silently break the restore drill. This drives all three
subcommands end-to-end against a temp DB.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from cli.__main__ import main
from data.db import create_all, make_engine, session_factory
from data.tables import LoggedBy, MealEvent, MealType


def _make_db(path: Path, n: int = 3) -> None:
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


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    db = tmp_path / "bgapp" / "app.db"
    db.parent.mkdir(parents=True)
    _make_db(db, n=3)
    backups = tmp_path / "backups"
    monkeypatch.setenv("BGAPP_DB_URL", f"sqlite:///{db}")
    monkeypatch.setenv("BGAPP_BACKUP_DIR", str(backups))
    return db, backups


def test_cli_backup_subcommand(
    cli_env: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, backups = cli_env
    assert main(["backup"]) == 0
    assert (backups / "snap.db").exists()
    assert "backup ok" in capsys.readouterr().out


def test_cli_export_subcommand(
    cli_env: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, backups = cli_env
    assert main(["export"]) == 0
    assert list(backups.glob("*.csv")), "export wrote no CSVs"
    assert "exported" in capsys.readouterr().out


def test_cli_restore_drill_subcommand(
    cli_env: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["restore-drill"]) == 0
    out = capsys.readouterr().out
    assert "ok=True" in out and "integrity_ok=True" in out


def test_cli_rejects_non_sqlite_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BGAPP_DB_URL", "postgres://nope")
    with pytest.raises(SystemExit):
        main(["backup"])
