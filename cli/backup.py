"""Hourly consistent snapshot + nightly CSV export (06 §5).

The live ``app.db`` must never live in a cloud-synced folder — syncing a file
mid-write corrupts SQLite. Only the consistent ``.backup`` snapshot goes there.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

# Folder-name markers of cloud sync clients. The LIVE db must not sit under any.
_SYNCED_MARKERS = (
    "dropbox",
    "google drive",
    "googledrive",
    "onedrive",
    "icloud",
    "icloud drive",
    "pcloud",
    "nextcloud",
    "box sync",
)


class SyncedFolderError(RuntimeError):
    """The live app.db is inside a cloud-synced folder (REQ-050)."""


def is_synced_folder(path: str) -> bool:
    """True if any path component looks like a cloud-sync folder."""
    parts = [part.lower() for part in Path(path).resolve().parts]
    return any(marker in part for part in parts for marker in _SYNCED_MARKERS)


def _assert_live_db_not_synced(db_path: str) -> None:
    if is_synced_folder(db_path):
        raise SyncedFolderError(
            f"app.db must NOT live in a cloud-synced folder (only the snapshot "
            f"may): {db_path}"
        )


def backup(db_path: str, snapshot_path: str) -> Path:
    """Take a transaction-consistent snapshot via SQLite's online backup API.

    Safe to run while a writer is active. The live DB is refused if it is inside
    a synced folder; the snapshot destination (a synced folder) is fine.
    """
    _assert_live_db_not_synced(db_path)
    snapshot = Path(snapshot_path)
    snapshot.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(str(snapshot))
        try:
            source.backup(dest)  # online backup — consistent even during writes
        finally:
            dest.close()
    finally:
        source.close()
    return snapshot


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def export_csv(db_path: str, out_dir: str) -> list[Path]:
    """Write one CSV per table (header + rows). Format-rot insurance (REQ-052)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    conn = sqlite3.connect(db_path)
    try:
        for table in _table_names(conn):
            # table name comes from sqlite_master (trusted), quoted as an identifier
            cursor = conn.execute(f'SELECT * FROM "{table}"')
            columns = [d[0] for d in cursor.description]
            path = out / f"{table}.csv"
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
            written.append(path)
    finally:
        conn.close()
    return written
