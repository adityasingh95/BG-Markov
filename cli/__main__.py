"""``python -m cli <command>`` — backup, export, restore-drill, refit (05 §8).

Paths come from the environment so a real patient DB path never lives in the
repo:
  BGAPP_DB_URL      sqlite:///... (the live DB; must NOT be a synced folder)
  BGAPP_BACKUP_DIR  where snapshots + CSV exports are written (may be synced)
"""

from __future__ import annotations

import argparse
import os
import tempfile

from cli.backup import backup, export_csv
from cli.refit import refit
from cli.restore_drill import run_restore_drill


def _db_url() -> str:
    return os.environ.get("BGAPP_DB_URL", "sqlite:///./bgapp-dev.db")


def _db_path() -> str:
    url = _db_url()
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    raise SystemExit(f"only sqlite URLs are supported, got: {url}")


def _backup_dir() -> str:
    return os.environ.get("BGAPP_BACKUP_DIR", "./backups")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cli", description="BG-Markov operations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup", help="consistent snapshot -> BGAPP_BACKUP_DIR/snap.db")
    sub.add_parser("export", help="CSV of every table -> BGAPP_BACKUP_DIR")
    sub.add_parser("restore-drill", help="restore a snapshot and verify it is faithful")
    # ★ No --promote flag, and there will not be one: promotion is an operator act taken
    # on the shadow dashboard after looking at the evidence (S-1001b AST guard).
    sub.add_parser("refit", help="monthly refit -> a new UNPROMOTED model artifact")
    args = parser.parse_args(argv)

    db = _db_path()
    if args.command == "backup":
        dest = backup(db, os.path.join(_backup_dir(), "snap.db"))
        print(f"backup ok -> {dest}")
        return 0
    if args.command == "export":
        written = export_csv(db, _backup_dir())
        print(f"exported {len(written)} table(s) -> {_backup_dir()}")
        return 0
    if args.command == "restore-drill":
        with tempfile.TemporaryDirectory(prefix="bg-drill-") as scratch:
            result = run_restore_drill(db, scratch)
        print(
            "restore-drill: "
            f"ok={result.ok} integrity_ok={result.integrity_ok} "
            f"identical={result.identical} tables={result.tables}"
        )
        return 0 if result.ok else 1
    if args.command == "refit":
        outcome = refit(_db_url())
        recall = "undefined (no lows in the window)" if outcome.hypo_recall is None else (
            f"{outcome.hypo_recall:.3f}"
        )
        print(
            f"refit ok -> {outcome.version} "
            f"(rows={outcome.n_rows}, hypo_recall={recall}, "
            f"dropped={len(outcome.dropped_features)})"
        )
        # Said in words, not implied by omission: a command that prints a version and stops
        # reads like a deployment.
        print("This artifact is NOT PROMOTED. Promote it on the operator shadow dashboard.")
        return 0
    return 2  # pragma: no cover - argparse enforces a valid command


if __name__ == "__main__":
    raise SystemExit(main())
