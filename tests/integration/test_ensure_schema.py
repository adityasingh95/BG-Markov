"""S-1024 (SDET) — `dev.sh` brings any local database to head. RED first.

★ Found by running it. `dev.sh migrate` shelled out to the **`sqlite3` CLI** to ask whether
a database had migration history. That binary is not installed everywhere — it is not
installed here — so the check silently answered "no tables", the stamp never ran, and
`alembic upgrade` died with `table audit_log already exists` and forty lines of traceback.

The operator's **first command** failed with a wall of SQL, which is the precise experience
`docs/RUNBOOK.md` exists to prevent.

The lesson is structural, not incidental: **bash orchestrates, Python does the work.** A
shell script that reasons about a database depends on whatever binaries happen to be on the
machine, and it fails in a way that reads as a broken migration rather than a missing tool.
The venv's Python is already a hard requirement; `sqlite3` never was.
"""

from __future__ import annotations

import pathlib

from sqlalchemy import inspect

from data.db import create_all, make_engine
from scripts.migrate_db import ensure_schema


def test_a_brand_new_file_is_created_at_head(tmp_path: pathlib.Path) -> None:
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    ensure_schema(url)

    names = set(inspect(make_engine(url)).get_table_names())
    assert "meal_event" in names
    assert "data_provenance" in names, "the newest migration did not run"
    assert "alembic_version" in names, "no migration history was recorded"


def test_a_database_made_by_create_all_is_stamped_then_upgraded(
    tmp_path: pathlib.Path,
) -> None:
    """★ The case that broke, reproduced exactly.

    `api/deps.py` calls `create_all()` on the first request, and `seed_demo_db` calls it
    directly — so a database can have every table and **no `alembic_version`**. Plain
    `alembic upgrade` then fails with "table already exists", which looks like a broken
    migration and is not one: the schema IS at head, it was simply never recorded as such.
    """
    url = f"sqlite:///{tmp_path / 'created.db'}"
    create_all(make_engine(url))
    names = set(inspect(make_engine(url)).get_table_names())
    assert "meal_event" in names and "alembic_version" not in names, names

    ensure_schema(url)  # must not raise

    names = set(inspect(make_engine(url)).get_table_names())
    assert "alembic_version" in names


def test_it_is_idempotent(tmp_path: pathlib.Path) -> None:
    """`dev.sh serve` runs it on every start."""
    url = f"sqlite:///{tmp_path / 'twice.db'}"
    ensure_schema(url)
    ensure_schema(url)
    assert "alembic_version" in set(inspect(make_engine(url)).get_table_names())


def test_dev_sh_does_not_depend_on_the_sqlite3_cli() -> None:
    """★ The guard for the class.

    Any shell-level reasoning about the database reintroduces a dependency on a binary that
    may not exist, and the failure surfaces as a broken migration rather than a missing
    tool — which sends the reader looking in entirely the wrong place.
    """
    script = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev.sh").read_text()
    offenders = [
        line.strip()
        for line in script.splitlines()
        if "sqlite3 " in line and not line.strip().startswith("#")
    ]
    assert not offenders, f"dev.sh shells out to the sqlite3 CLI: {offenders}"
