"""S-1026 (SDET) — the launcher a non-technical tester double-clicks. RED first.

Two properties carry real weight here and both are asserted structurally rather than by
reading messages.

★ **`run.py` imports only the standard library.** It runs *before anything is installed* —
that is its entire job — so one third-party import at module level makes it crash on exactly
the machine it exists to set up, and the crash is a traceback, which is the thing this story
exists to eliminate. Proven by parsing the AST, because a grep for `import fastapi` passes a
file that imports `pandas`.

★ **Reset refuses a database that is not demo-marked.** `bgapp-dev.db` is the real-capture
path: her records, no seed, no way back. Once `Reset to empty.cmd` sits in a folder beside
`Start BG-Markov.cmd`, the three filters that made `dev.sh reset` safe — a terminal, a path,
and typing DELETE — are all gone. The assertion is that **the file still exists**, never that
a refusal was printed: a script that prints a refusal and unlinks anyway prints the same words.
"""

from __future__ import annotations

import ast
import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RUN_PY = _ROOT / "run.py"

_CMD_FILES = (
    "Start BG-Markov.cmd",
    "Reset to empty.cmd",
    "Restore demo data.cmd",
)


# --- The launcher must survive a machine with nothing installed ------------------------


def test_run_py_exists() -> None:
    assert _RUN_PY.exists(), "run.py does not exist"


def test_run_py_imports_only_the_standard_library() -> None:
    """★ It runs before the venv exists. A third-party import is a traceback on first use."""
    tree = ast.parse(_RUN_PY.read_text(encoding="utf-8"), filename=str(_RUN_PY))

    offenders: list[str] = []
    for node in tree.body:  # module level ONLY — a lazy import inside a function is fine
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            root = name.split(".")[0]
            if root not in sys.stdlib_module_names:
                offenders.append(name)

    assert not offenders, (
        "run.py imports non-stdlib modules at module level: "
        f"{offenders}. It runs BEFORE the venv exists — this is a traceback on the "
        "operator's first double-click. Import it inside the function that needs it, or "
        "subprocess into the venv's Python."
    )


# --- Windows batch files ----------------------------------------------------------------


@pytest.mark.parametrize("name", _CMD_FILES)
def test_cmd_file_exists(name: str) -> None:
    assert (_ROOT / name).exists(), f"{name} does not exist"


@pytest.mark.parametrize("name", _CMD_FILES)
def test_cmd_files_use_crlf_line_endings(name: str) -> None:
    """A .cmd with Unix line endings fails on its first label or `goto`.

    cmd.exe reads a batch file line by line by byte offset; an LF-only file misaligns it, and
    the failure surfaces as `The system cannot find the batch label specified` — which reads
    as a corrupt download rather than as a text-encoding problem. Editors and git filters
    normalise line endings silently, so this needs a test rather than a convention.
    """
    raw = (_ROOT / name).read_bytes()
    lone_lf = raw.replace(b"\r\n", b"").count(b"\n")
    assert lone_lf == 0, f"{name} has {lone_lf} LF-only line endings; cmd.exe needs CRLF"


@pytest.mark.parametrize("name", _CMD_FILES)
def test_cmd_files_do_not_assume_python_is_3_12(name: str) -> None:
    """The tester's machine is the operator's machine, which had 3.11 on `python`."""
    text = (_ROOT / name).read_text(encoding="utf-8", errors="replace")
    assert "py -3.12" in text, (
        f"{name} does not try the `py -3.12` launcher, which is how a specific Python is "
        "reached on Windows when `python` is some other version"
    )


# --- ★ Reset, and the database it must not touch ----------------------------------------


def _make_db(path: pathlib.Path, *, demo_marked: bool) -> None:
    """A database shaped just enough for the marker check, built with stdlib sqlite3."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE data_provenance ("
        " id INTEGER PRIMARY KEY, kind TEXT NOT NULL, note TEXT, created_at TEXT)"
    )
    if demo_marked:
        conn.execute(
            "INSERT INTO data_provenance (kind, note, created_at) VALUES (?, ?, ?)",
            ("demo", "DEMO DATA — not her records", "2026-08-06T00:00:00"),
        )
    conn.commit()
    conn.close()


def _uninstrumented_env() -> dict[str, str]:
    """A subprocess environment with pytest-cov's hooks stripped out.

    ★ `pytest-cov.pth` is installed in site-packages, so **every** Python subprocess started
    during a test run silently joins the coverage session and writes its own `.coverage.*`
    file. Those children record statement-only data; the parent runs with `branch = true`;
    and combining them at report time aborts the whole run with

        INTERNALERROR> coverage.exceptions.DataError:
            Can't combine statement coverage data with branch data

    — after every test has already passed, which makes it read like a coverage-tool bug
    rather than something a test did. `run.py` is not in the measured set anyway; these
    children are being driven for their behaviour, not their coverage.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE", "COVERAGE_"))
    } | {"BGAPP_ASSUME_TTY": "0"}


def _reset(cwd: pathlib.Path, db: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_ROOT / "run.py"), "reset", "--db", str(db), "--yes"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_uninstrumented_env(),
    )


def test_reset_refuses_a_database_that_is_not_demo_marked(tmp_path: pathlib.Path) -> None:
    """★ The one that matters. An unmarked database is treated as her real records.

    Asserts the FILE SURVIVES, not that a refusal was printed. A reset that prints a refusal
    and unlinks anyway prints exactly the same words, and `--yes` is passed deliberately: the
    guard must not be the confirmation, because a confirmation is what a person clicking
    through a task clicks through.
    """
    db = tmp_path / "bgapp-dev.db"
    _make_db(db, demo_marked=False)

    result = _reset(tmp_path, db)

    assert db.exists(), (
        "run.py reset DELETED an unmarked database. That path is her real capture; "
        "there is no seed to rebuild it from."
    )
    assert result.returncode != 0, "refusing must not report success"


def test_reset_does_delete_a_demo_marked_database(tmp_path: pathlib.Path) -> None:
    """The guard must be a guard, not a broken feature.

    Without this, a `reset` that never deletes anything satisfies the test above perfectly.
    """
    db = tmp_path / "bgapp-demo.db"
    _make_db(db, demo_marked=True)

    result = _reset(tmp_path, db)

    assert not db.exists(), f"marked demo database was not deleted:\n{result.stdout}"
    assert result.returncode == 0


def test_reset_leaves_no_write_ahead_sidecars_behind(tmp_path: pathlib.Path) -> None:
    """★ "Cleared" must mean cleared.

    SQLite in WAL mode keeps `<name>-wal` and `<name>-shm` beside the database. Deleting only
    the `.db` leaves them, and the next `Restore demo data` creates a fresh file with the same
    name that SQLite then tries to recover from the orphaned log. Found by listing the
    directory after a real reset, not by assuming one unlink was the whole job.
    """
    db = tmp_path / "bgapp-demo.db"
    _make_db(db, demo_marked=True)
    for suffix in ("-wal", "-shm"):
        db.with_name(db.name + suffix).write_bytes(b"stale")

    _reset(tmp_path, db)

    survivors = sorted(p.name for p in tmp_path.iterdir())
    assert not survivors, f"reset left files behind: {survivors}"


def test_reset_checks_the_mark_before_it_unlinks(tmp_path: pathlib.Path) -> None:
    """A reset that unlinks first and reads the mark afterwards passes both tests above
    for the demo case and destroys the real one. Read-only sanity: the refusal must leave the
    file byte-identical, not merely present."""
    db = tmp_path / "bgapp-dev.db"
    _make_db(db, demo_marked=False)
    before = db.read_bytes()

    _reset(tmp_path, db)

    assert db.read_bytes() == before, "the unmarked database was modified, not just spared"


@pytest.mark.parametrize(
    ("marked", "note"),
    [
        # ★ The note is NULL for every database the seeder actually makes — `seed_demo_db`
        # calls `mark_demo_database(session)` with no note. The first version of run.py keyed
        # on the banner text and therefore answered "not demo" for all of them, which would
        # have made "Reset to empty" silently do nothing. This case is the regression guard.
        pytest.param(True, None, id="marked-no-note"),
        pytest.param(True, "seeded by hand", id="marked-with-note"),
        pytest.param(False, None, id="unmarked"),
    ],
)
def test_the_launchers_marker_check_agrees_with_the_projects(
    tmp_path: pathlib.Path, marked: bool, note: str | None
) -> None:
    """★ `run.py` reads the demo mark itself, with stdlib sqlite3 in READ-ONLY mode.

    It does not call `data.provenance.is_demo_database`, and that is deliberate: going
    through SQLAlchemy opens the file read-write, and the connection flipped the database
    into WAL mode — byte 18 of the header changed — so the refusal path *wrote to the file it
    was refusing to delete*. On `bgapp-dev.db` that is her records.

    The cost of a read-only reimplementation is two readings of the same fact. This test is
    what stops them drifting: both are asked about the same file and must give the same
    answer. If someone changes the mark, the table, or the column, this fails rather than the
    guard quietly answering "not demo — refuse" (harmless) or "demo — delete it" (not).
    """
    import importlib.util

    from data.db import make_engine, session_factory
    from data.provenance import is_demo_database, mark_demo_database
    from data.tables import Base

    db = tmp_path / ("marked.db" if marked else "unmarked.db")
    engine = make_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as session:
        if marked:
            mark_demo_database(session, note=note)
        session.commit()
        project_says = bool(is_demo_database(session))
    engine.dispose()

    spec = importlib.util.spec_from_file_location("bgapp_run", _RUN_PY)
    assert spec and spec.loader
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    assert launcher.is_demo_database(db) == project_says == marked, (
        "run.py and data/provenance.py disagree about whether this database is demo data"
    )


# --- No tracebacks ----------------------------------------------------------------------


def test_a_missing_database_is_a_sentence_not_a_traceback(tmp_path: pathlib.Path) -> None:
    result = _reset(tmp_path, tmp_path / "not-there.db")
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined, f"raw traceback shown to a non-technical user:\n{combined}"
