"""BG-Markov — the launcher a non-technical tester double-clicks (S-1026).

★ **This module imports only the standard library, and there is a test that says so.**

It runs *before anything is installed* — that is its whole job. One third-party import at
module level makes it crash on exactly the machine it exists to set up, and the crash is a
traceback, which is the thing this file exists to eliminate. Anything from the project is
imported inside the function that needs it, after the environment has been built.

Usage (normally reached by double-clicking a .cmd file, not typed):

    python run.py start            check, install if needed, seed, serve, open the browser
    python run.py restore-demo     rebuild the synthetic database from the seed
    python run.py reset            delete the synthetic database
    python run.py preflight        report what this machine is missing, and stop

★ `06 §7` — whatever this starts binds to 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import socket
import sqlite3
import subprocess
import sys
import time
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
VENV = ROOT / ".venv"
DEMO_DB_NAME = "bgapp-demo.db"
DEV_DB_NAME = "bgapp-dev.db"

#: How `data/provenance.py` marks a synthetic database: a row in `data_provenance` whose
#: `kind` is exactly this. **The `note` column is not part of the test** — `mark_demo_database`
#: leaves it NULL unless a caller passes one, so keying on the banner text would answer "not
#: demo" for every database the seeder actually produces. See `is_demo_database` below.
DEMO_KIND = "demo"

WIDTH = 68


# --- Talking to someone who is not a programmer ----------------------------------------


def say(message: str = "") -> None:
    print(message, flush=True)


def heading(message: str) -> None:
    say()
    say(message)
    say("-" * min(len(message), WIDTH))


def problem(what: str, do_this: str) -> None:
    """A failure is a sentence and an instruction. Never a traceback."""
    say()
    say("=" * WIDTH)
    say("  Something needs your attention")
    say("=" * WIDTH)
    say()
    say(f"  {what}")
    say()
    say(f"  What to do:  {do_this}")
    say()


def wait_for_a_keypress() -> None:
    """A double-clicked window closes instantly on exit, taking the message with it."""
    if os.environ.get("BGAPP_ASSUME_TTY") == "0" or not sys.stdin or not sys.stdin.isatty():
        return
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        input("  Press Enter to close this window. ")


# --- Finding a Python ---------------------------------------------------------------------


def venv_python() -> pathlib.Path:
    """`Scripts` on Windows, `bin` everywhere else — the defect that broke Git Bash."""
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _is_3_12(command: list[str]) -> bool:
    try:
        out = subprocess.run(
            [*command, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.strip() == "3.12"


def find_python_312() -> list[str] | None:
    """`py -3.12` first on Windows: `python` is whatever was installed last, often not 3.12."""
    candidates: list[list[str]] = [[sys.executable]]
    if os.name == "nt":
        candidates.append(["py", "-3.12"])
    candidates += [["python3.12"], ["python3"], ["python"]]
    for candidate in candidates:
        if _is_3_12(candidate):
            return candidate
    return None


def install_python_command() -> list[str] | None:
    """Windows only, per the operator's decision. Others are told where to look."""
    if os.name != "nt":
        return None
    return [
        "winget", "install", "--id", "Python.Python.3.12", "-e", "--source", "winget",
        "--accept-source-agreements", "--accept-package-agreements",
    ]


def offer_to_install_python() -> bool:
    """★ Same rule as bootstrap.sh: the exact command is shown, and nothing runs until the
    operator types YES. A double-click that silently installs software is worse than a
    terminal, not better, because nothing was read."""
    command = install_python_command()
    if command is None:
        problem(
            "BG-Markov needs Python 3.12, and it is not on this computer.",
            "Install it from https://www.python.org/downloads/ and run this again.",
        )
        return False

    say()
    say("  BG-Markov needs Python 3.12. It is not installed on this computer.")
    say()
    say("  I can install it for you, by running exactly this:")
    say()
    say("      " + " ".join(command))
    say()
    say("  This ADDS Python 3.12. It does not remove, replace or change any")
    say("  other program on this computer.")
    say()
    try:
        reply = input("  Type YES to install it, or just close this window:  ").strip()
    except (EOFError, KeyboardInterrupt):
        reply = ""

    if reply != "YES":
        say()
        say("  Nothing was installed.")
        return False

    say()
    say("  Installing. This takes a few minutes.")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        problem(
            "The installer did not finish successfully.",
            "Install Python 3.12 from https://www.python.org/downloads/ instead.",
        )
        return False

    say()
    say("  Python 3.12 is installed.")
    say()
    say("  ★ Now CLOSE this window and start BG-Markov again.")
    say("    Windows only notices a new program when a window opens, so this")
    say("    window cannot see it yet.")
    return False  # deliberately: the caller must not continue in this process


# --- Building the environment --------------------------------------------------------------


def ensure_venv() -> bool:
    python = find_python_312()
    if python is None:
        return offer_to_install_python()

    if not venv_python().exists():
        heading("Setting up. This happens once, and takes a few minutes.")
        say("  Creating a private copy of Python for BG-Markov...")
        if subprocess.run([*python, "-m", "venv", str(VENV)], check=False).returncode != 0:
            problem("Could not create the environment.", "Send this window to the operator.")
            return False

    marker = subprocess.run(
        [str(venv_python()), "-c", "import fastapi, sqlalchemy, alembic"],
        capture_output=True,
        check=False,
    )
    if marker.returncode != 0:
        say("  Downloading what BG-Markov needs (about 500 MB — this is the slow part).")
        say("  Nothing will be printed while this runs. It has not stopped.")
        installed = subprocess.run(
            [str(venv_python()), "-m", "pip", "install", "-e", ".", "--quiet"],
            cwd=ROOT,
            check=False,
        )
        if installed.returncode != 0:
            problem(
                "The download did not finish. This is usually the internet connection.",
                "Check you are online and start BG-Markov again.",
            )
            return False
    return True


def ensure_schema(db_name: str) -> bool:
    result = subprocess.run(
        [str(venv_python()), "-m", "scripts.migrate_db", f"sqlite:///{db_name}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        problem("Could not prepare the database.", "Send this window to the operator.")
        return False
    return True


def seed_demo(db_name: str) -> bool:
    say("  Creating 240 days of pretend data...")
    result = subprocess.run(
        [str(venv_python()), "-m", "scripts.seed_demo_db",
         "--db", db_name, "--days", "240", "--seed", "7"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        problem("Could not create the demonstration data.", "Send this window to the operator.")
        return False
    return True


# --- Is this database safe to delete? -------------------------------------------------------


def is_demo_database(db: pathlib.Path) -> bool:
    """Is this file marked as demonstration data, and therefore safe to delete?

    ★ **Opened strictly read-only** (`mode=ro`), and that is a safety property, not tidiness.

    The first version asked the project — `data.provenance.is_demo_database` through a
    SQLAlchemy session. It gave the right answer and it **modified the file while doing so**:
    SQLAlchemy opens read-write, the connection switched the database to WAL, and byte 18 of
    the header (the write-version flag) changed from 1 to 2. On the refusal path that means
    the launcher wrote to the one file it exists to protect — *her records* — before declining
    to delete it. A guard that alters what it is guarding is not a guard.

    The cost is a second reading of the mark, separate from `data/provenance.py`.
    `tests/integration/test_user_launcher.py` pins the two together by asserting they agree on
    both a marked and an unmarked database, so the duplication cannot drift silently.

    **Fails closed.** Unreadable, missing table, wrong shape ⇒ ``False`` ⇒ not deletable.
    """
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM data_provenance WHERE kind = ? LIMIT 1", (DEMO_KIND,)
        ).fetchone()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return row is not None


# --- Commands ---------------------------------------------------------------------------------


def _unlink_database(db: pathlib.Path) -> None:
    """Delete the database **and its write-ahead sidecars**.

    ★ SQLite in WAL mode keeps `-wal` and `-shm` beside the database, and removing only the
    `.db` leaves them behind. The next `Restore demo data` creates a fresh file with the same
    name, and SQLite treats the orphaned `-wal` as a log belonging to it and attempts
    recovery — so the "clean slate" is not one. Found by listing the directory after a reset
    rather than by trusting that one `unlink` was the whole job.
    """
    for path in (db, db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
        path.unlink(missing_ok=True)


def cmd_reset(db: pathlib.Path, assume_yes: bool) -> int:
    """★ Refuses outright to touch a database that is not marked as demonstration data.

    The guard is NOT the confirmation. A confirmation is what a person clicking through a task
    clicks through, and `bgapp-dev.db` is the real-capture path: her records, no seed, no way
    back. The mark is read BEFORE anything is unlinked.
    """
    if not db.exists():
        say()
        say(f"  There is no {db.name} to clear. Nothing to do.")
        return 0

    if not is_demo_database(db):
        problem(
            f"{db.name} is NOT marked as demonstration data, so it is being "
            "treated as real records. It has not been touched.",
            "If you meant to clear the practice data, use 'Reset to empty' which "
            "works on bgapp-demo.db. If you really meant this file, ask the operator.",
        )
        return 2

    if not assume_yes:
        say()
        say(f"  This deletes all the practice data in {db.name}.")
        say("  You can put it back afterwards with 'Restore demo data'.")
        say()
        try:
            reply = input("  Type YES to clear it, or just close this window:  ").strip()
        except (EOFError, KeyboardInterrupt):
            reply = ""
        if reply != "YES":
            say()
            say("  Nothing was deleted.")
            return 1

    _unlink_database(db)
    say()
    say(f"  Cleared. {db.name} is gone.")
    say("  'Restore demo data' will build it again.")
    return 0


def cmd_restore_demo() -> int:
    if not ensure_venv():
        return 1
    db = ROOT / DEMO_DB_NAME
    if db.exists():
        if not is_demo_database(db):
            problem(
                f"{db.name} exists but is not marked as demonstration data. "
                "It has not been touched.",
                "Ask the operator before going further.",
            )
            return 2
        _unlink_database(db)
    if not seed_demo(DEMO_DB_NAME) or not ensure_schema(DEMO_DB_NAME):
        return 1
    say()
    say("  Done. The demonstration data is back.")
    say("  Start BG-Markov to look at it.")
    return 0


def cmd_preflight() -> int:
    heading("Checking this computer")
    python = find_python_312()
    say(f"  Python 3.12       {'found' if python else 'NOT FOUND'}")
    say(f"  Set up            {'yes' if venv_python().exists() else 'not yet'}")
    say(f"  Practice data     {'yes' if (ROOT / DEMO_DB_NAME).exists() else 'not yet'}")
    return 0 if python else 1


def _port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _wait_until_serving(port: int, timeout: float = 90.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(1.0)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def cmd_start(port: int) -> int:
    if not ensure_venv():
        return 1

    db_name = DEMO_DB_NAME
    if not (ROOT / db_name).exists():
        heading("Setting up the practice data")
        if not seed_demo(db_name):
            return 1
    if not ensure_schema(db_name):
        return 1

    if not _port_is_free(port):
        problem(
            f"Something else on this computer is already using port {port}. "
            "BG-Markov may already be running in another window.",
            "Close the other BG-Markov window, then try again.",
        )
        return 1

    heading("Starting BG-Markov")
    say("  Your browser will open by itself in a moment.")
    say()
    say("  ★ LEAVE THIS WINDOW OPEN while you are using BG-Markov.")
    say("    Closing this window stops it. That is how you stop it.")
    say()

    environment = dict(os.environ)
    environment["BGAPP_DB_URL"] = f"sqlite:///{db_name}"
    server = subprocess.Popen(
        [str(venv_python()), "-m", "uvicorn", "api.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=environment,
    )
    try:
        if _wait_until_serving(port):
            webbrowser.open(f"http://127.0.0.1:{port}")
        else:
            say(f"  If your browser did not open, go to:  http://127.0.0.1:{port}")
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.terminate()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start")
    start.add_argument("--port", type=int, default=int(os.environ.get("BGAPP_PORT", "8000")))

    reset = sub.add_parser("reset")
    reset.add_argument("--db", default=str(ROOT / DEMO_DB_NAME))
    reset.add_argument("--yes", action="store_true")

    sub.add_parser("restore-demo")
    sub.add_parser("preflight")

    args = parser.parse_args(argv)
    command = args.command or "start"

    if command == "reset":
        return cmd_reset(pathlib.Path(args.db), assume_yes=args.yes)
    if command == "restore-demo":
        return cmd_restore_demo()
    if command == "preflight":
        return cmd_preflight()
    return cmd_start(args.port)


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:  # noqa: BLE001 - a traceback is the failure this file prevents
        problem(
            f"BG-Markov stopped unexpectedly: {type(exc).__name__}: {exc}",
            "Send this window to the operator.",
        )
        code = 1
    if code != 0:
        wait_for_a_keypress()
    sys.exit(code)
