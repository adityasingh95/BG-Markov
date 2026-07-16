"""S-502 [SAFETY] — ISF derivation reads only the clean, followed-up events.

The estimator must see only correction events that are unconfounded (no food, low
prior IOB) AND have their +4 h reading. This test drives the data accessor that
bridges get_clean_correction_events to the pure estimator. SDET, RED first.

RED: `derive_isf_from_correction_events` does not exist yet.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory
from data.repositories import derive_isf_from_correction_events
from data.tables import CorrectionEvent

_BASE = datetime(2026, 5, 1, 10, 0)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'isf.db'}")
    create_all(engine)
    sess = session_factory(engine)()
    try:
        yield sess
    finally:
        sess.close()


def _event(
    i: int,
    *,
    bg_before: int = 250,
    bg_after: int | None = 100,
    units: float = 5.0,
    iob: float | None = 0.1,
    food: bool = False,
) -> CorrectionEvent:
    when = _BASE + timedelta(days=i)
    return CorrectionEvent(
        datetime=when, logged_at=when, bg_before=bg_before,
        bg_after=bg_after, bg_after_time=(when + timedelta(hours=4) if bg_after else None),
        units=units, iob_at_start=iob, food_in_window=food,
    )


def test_five_clean_followed_up_events_apply(session: Session) -> None:
    session.add_all([_event(i) for i in range(5)])  # all clean, ISF (250-100)/5 = 30
    session.commit()
    r = derive_isf_from_correction_events(session, current_isf=45.0, current_source="default")
    assert r.n_clean == 5
    assert r.applied is True
    assert r.derived_isf == pytest.approx(30.0)
    assert r.isf_source == "derived"


def test_confounded_and_pending_events_are_excluded(session: Session) -> None:
    """Only food-free, low-IOB, followed-up events count — everything else drops,
    so the qualifying set stays below the gate and the default is retained."""
    session.add_all([
        _event(0),                       # clean
        _event(1),                       # clean
        _event(2, food=True),            # confounded by food -> excluded
        _event(3, iob=0.8),              # high prior IOB -> excluded
        _event(4, iob=None),             # IOB unknown (deferred) -> excluded
        _event(5, bg_after=None),        # +4 h reading pending -> excluded
    ])
    session.commit()
    r = derive_isf_from_correction_events(session, current_isf=30.0, current_source="default")
    assert r.n_clean == 2          # only the two fully-clean, followed-up events
    assert r.applied is False      # below the 5-event gate
    assert r.isf == 30.0
