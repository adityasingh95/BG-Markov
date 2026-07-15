"""The restore drill — proving the backup can actually be restored (REQ-051).

An untested backup is not a backup. This restores a snapshot and checks it is a
valid, faithful copy of the source.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cli.backup import backup


@dataclass(frozen=True)
class DrillResult:
    ok: bool
    integrity_ok: bool
    identical: bool
    tables: dict[str, int]


def _dump_hash(db_path: str | Path) -> str:
    """A content hash of the whole DB via its canonical SQL dump."""
    conn = sqlite3.connect(str(db_path))
    try:
        digest = hashlib.sha256()
        for line in conn.iterdump():
            digest.update(line.encode("utf-8"))
        return digest.hexdigest()
    finally:
        conn.close()


def _row_counts(db_path: str | Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        names = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        ).fetchall()
        return {n[0]: conn.execute(f'SELECT count(*) FROM "{n[0]}"').fetchone()[0] for n in names}
    finally:
        conn.close()


def run_restore_drill(db_path: str, scratch_dir: str) -> DrillResult:
    """Snapshot the DB, restore it to scratch, and verify the restore is faithful.

    Checks: the restored DB passes ``integrity_check``; the restored file is
    byte-identical to the snapshot; and the restored data dump equals the source.
    """
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)

    snapshot = backup(db_path, str(scratch / "snap.db"))
    restored = scratch / "restored.db"
    shutil.copyfile(snapshot, restored)

    conn = sqlite3.connect(str(restored))
    try:
        integrity_ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()

    identical = (
        snapshot.read_bytes() == restored.read_bytes()
        and _dump_hash(db_path) == _dump_hash(restored)
    )
    return DrillResult(
        ok=integrity_ok and identical,
        integrity_ok=integrity_ok,
        identical=identical,
        tables=_row_counts(restored),
    )
