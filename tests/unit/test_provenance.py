"""S-1024 (SDET) — the database records what kind of data it holds. RED first."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory
from data.provenance import is_demo_database, mark_demo_database


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'prov.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


def test_a_fresh_database_is_not_demo(session: Session) -> None:
    """Absence of a mark means *not marked* — it does not mean *demo*.

    The alternative, defaulting to "demo", would stamp DEMO across her real records on the
    first day of capture, which teaches her to ignore the banner.
    """
    assert is_demo_database(session) is False


def test_marking_makes_it_demo(session: Session) -> None:
    mark_demo_database(session, note="synthetic, 240 days, seed 7")
    session.commit()
    assert is_demo_database(session) is True


def test_marking_twice_is_idempotent(session: Session) -> None:
    """Re-seeding an existing file must not accumulate rows; the answer is a fact about the
    database, not a count of how many times somebody said it."""
    mark_demo_database(session, note="first")
    mark_demo_database(session, note="second")
    session.commit()
    assert is_demo_database(session) is True

    from sqlalchemy import func, select

    from data.tables import DataProvenance

    n = session.scalar(select(func.count()).select_from(DataProvenance)) or 0
    assert n == 1, f"marking twice left {n} rows"


def test_the_note_is_kept(session: Session) -> None:
    """*Which* synthetic data — days, seed — is what makes a stale demo file diagnosable
    six weeks later."""
    from sqlalchemy import select

    from data.tables import DataProvenance

    mark_demo_database(session, note="synthetic, 240 days, seed 7")
    session.commit()
    row = session.scalars(select(DataProvenance)).one()
    assert "seed 7" in (row.note or "")
    assert row.created_at is not None


def test_it_survives_a_reopen(tmp_path: pathlib.Path) -> None:
    """★ The point of putting it in the database rather than the environment: close the
    process, reopen the file, and it still says what it is."""
    url = f"sqlite:///{tmp_path / 'reopen.db'}"
    engine = make_engine(url)
    create_all(engine)
    with session_factory(engine)() as s:
        mark_demo_database(s, note="synthetic")
        s.commit()

    with session_factory(make_engine(url))() as s2:
        assert is_demo_database(s2) is True
