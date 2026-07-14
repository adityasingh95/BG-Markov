"""App database wiring: a lazily-created engine and a per-request session.

The URL comes from ``BGAPP_DB_URL`` (tests override the ``get_session``
dependency; production runs Alembic). ``create_all`` here is a dev convenience so
the app runs out of the box on a fresh machine.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ.get("BGAPP_DB_URL", "sqlite:///./bgapp-dev.db")
        _engine = make_engine(url)
        create_all(_engine)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session, committed/closed per request."""
    factory = session_factory(_get_engine())
    with factory() as session:
        yield session
