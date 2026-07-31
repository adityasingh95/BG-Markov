"""Bring a local database to the current schema (S-1024).

Usage:  python -m scripts.migrate_db sqlite:///./bgapp-dev.db

★ **Bash orchestrates; Python does the work.** The first version of this lived in
`dev.sh` and shelled out to the `sqlite3` CLI to ask whether a database had migration
history. That binary is not installed everywhere — it was not installed on the first
machine this ran on — so the check silently answered "no", the stamp never happened, and
`alembic upgrade` died with `table audit_log already exists` and forty lines of traceback.
The operator's **first command** failed with a wall of SQL.

A shell script that reasons about a database depends on whatever binaries happen to be
present, and fails in a way that reads as a broken migration rather than a missing tool.
The venv's Python is already a hard requirement here; `sqlite3` never was.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from data.db import make_engine

_ROOT = Path(__file__).resolve().parents[1]

#: Any table that exists only if the schema was already built. `alembic_version` is
#: deliberately not in this set — its ABSENCE is the whole signal.
_SCHEMA_MARKER = "meal_event"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def ensure_schema(url: str) -> str:
    """Bring ``url`` to head, and say what had to be done.

    Three cases, and the middle one is why this function exists:

    1. **No file / no tables** — a plain ``upgrade`` builds everything.
    2. **★ Tables but no `alembic_version`** — the database was built by ``create_all()``,
       which `api/deps.py` calls on the first request and `seed_demo_db` calls directly.
       ``upgrade`` alone fails with *"table already exists"*, which looks like a broken
       migration and is not one: the schema **is** at head, it was simply never recorded as
       such. Stamping first is the honest repair.
    3. **Both present** — ``upgrade`` is a no-op or applies what is new.
    """
    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    cfg = _alembic_config(url)
    note = "upgraded"
    if _SCHEMA_MARKER in tables and "alembic_version" not in tables:
        # Built by create_all: record the history it already has, then move it forward.
        command.stamp(cfg, "head")
        note = "stamped (built by create_all), then upgraded"
    command.upgrade(cfg, "head")
    return note


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m scripts.migrate_db <sqlalchemy-url>", file=sys.stderr)
        return 2
    print(f"  schema: {ensure_schema(args[0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
