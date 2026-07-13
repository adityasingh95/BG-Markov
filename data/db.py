"""Engine / session helpers for the SQLite database.

SQLite in WAL mode (06 §5): a single-file DB whose ``.backup`` snapshot is a
consistent point-in-time copy — which is what makes durability solvable.
Foreign-key enforcement is enabled per connection (SQLite defaults it off).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from data.tables import Base


def make_engine(url: str, *, wal: bool = True) -> Engine:
    """Create an engine. For SQLite, enable WAL and foreign-key enforcement."""
    engine = create_engine(url)

    if wal and url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_all(engine: Engine) -> None:
    """Create every table. Alembic owns production schema; this is for tests
    and first-run bootstrap."""
    Base.metadata.create_all(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
