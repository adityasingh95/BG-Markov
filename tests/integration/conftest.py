"""Shared fixtures for data-layer integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    create_all(engine)
    sess = session_factory(engine)()
    try:
        yield sess
    finally:
        sess.close()
