"""S-306b — iob_at_start computed from the IOB engine (discharges DL-020). RED first.

S-306 left correction_event.iob_at_start NULL, deferring it to S-401's iob_at().
Now the engine exists: iob_at_start = IOB from PRIOR insulin at the correction
moment (excludes the correction bolus itself), the confounder that decides whether
a correction is a clean ISF signal (07 §6: clean iff iob_at_start < 0.5).

RED: iob_at_start_at / boluses_before / backfill_correction_iob do not exist, and
the endpoint leaves iob_at_start NULL.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.repositories import (
    backfill_correction_iob,
    get_clean_correction_events,
    iob_at_start_at,
)
from data.tables import BolusLog, BolusType, CorrectionEvent, LoggedBy
from features.iob import iob_fraction


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = make_engine(f"sqlite:///{tmp_path / 'corr_iob.db'}")
    create_all(engine)
    factory = session_factory(engine)

    def _override() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app), factory
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'corr_iob_repo.db'}")
    create_all(engine)
    sess = session_factory(engine)()
    try:
        yield sess
    finally:
        sess.close()


def _prior_bolus(s: Session, when: datetime, units: float) -> None:
    s.add(BolusLog(
        datetime=when, logged_at=when, units=units,
        bolus_type=BolusType.meal, meal_id=None, logged_by=LoggedBy.patient,
    ))


def _post_correction(api: TestClient, when: str, units: float, food: bool = False) -> int:
    return int(api.post("/api/correction-events", json={
        "datetime": when, "bg_before": 210, "units": units,
        "food_in_window": food, "logged_by": "patient",
    }).json()["event_id"])


# --- capture-time computation ----------------------------------------------


def test_capture_computes_iob_from_prior_bolus_only(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """A 6 U meal bolus 30 min before ⇒ iob_at_start ≈ 6·iob_fraction(30); the
    correction bolus itself (same instant) is NOT counted."""
    api, factory = client
    with factory() as s:
        _prior_bolus(s, datetime(2026, 7, 13, 9, 30), 6.0)  # 30 min before 10:00
        s.commit()

    event_id = _post_correction(api, "2026-07-13T10:00:00", units=2.0)

    with factory() as s:
        ev = s.get(CorrectionEvent, event_id)
        assert ev is not None
        assert ev.iob_at_start is not None
        assert ev.iob_at_start == pytest.approx(6.0 * iob_fraction(30.0), abs=1e-6)
        # the correction's own 2 U (age 0, fraction 1.0) must NOT be included —
        # if it were, iob_at_start would be 6·f(30) + 2·1.0.
        included = 6.0 * iob_fraction(30.0) + 2.0
        assert ev.iob_at_start != pytest.approx(included, abs=1e-6)


def test_capture_with_no_prior_insulin_is_zero(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    event_id = _post_correction(api, "2026-07-13T10:00:00", units=2.0)
    with factory() as s:
        ev = s.get(CorrectionEvent, event_id)
        assert ev is not None
        assert ev.iob_at_start == pytest.approx(0.0, abs=1e-9)


# --- the bridge accessor ----------------------------------------------------


def test_iob_at_start_at_sums_prior_boluses(session: Session) -> None:
    _prior_bolus(session, datetime(2026, 7, 13, 9, 0), 6.0)   # 60 min before
    _prior_bolus(session, datetime(2026, 7, 13, 9, 30), 4.0)  # 30 min before
    _prior_bolus(session, datetime(2026, 7, 13, 10, 0), 2.0)  # AT the moment — excluded
    session.commit()
    at = datetime(2026, 7, 13, 10, 0)
    expected = 6.0 * iob_fraction(60.0) + 4.0 * iob_fraction(30.0)
    assert iob_at_start_at(session, at) == pytest.approx(expected, abs=1e-9)


# --- end-to-end: the value now drives the 07 §6 clean filter ----------------


def test_high_prior_iob_excludes_event_from_clean_set(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """A large bolus moments before ⇒ iob_at_start ≥ 0.5 ⇒ NOT a clean ISF event."""
    api, factory = client
    with factory() as s:
        _prior_bolus(s, datetime(2026, 7, 13, 9, 55), 8.0)  # 5 min before, big
        s.commit()
    _post_correction(api, "2026-07-13T10:00:00", units=2.0, food=False)
    with factory() as s:
        assert get_clean_correction_events(s) == []  # confounded by IOB


def test_low_prior_iob_keeps_event_in_clean_set(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """No meaningful prior insulin + no food ⇒ iob_at_start < 0.5 ⇒ clean."""
    api, factory = client
    event_id = _post_correction(api, "2026-07-13T10:00:00", units=2.0, food=False)
    with factory() as s:
        clean = get_clean_correction_events(s)
        assert [e.event_id for e in clean] == [event_id]


# --- backfill for events captured before the engine existed -----------------


def test_backfill_fills_null_iob_at_start(session: Session) -> None:
    _prior_bolus(session, datetime(2026, 7, 13, 9, 30), 6.0)
    # An event stored the S-306 way: iob_at_start left NULL.
    session.add(CorrectionEvent(
        datetime=datetime(2026, 7, 13, 10, 0),
        logged_at=datetime(2026, 7, 13, 10, 5),
        bg_before=210, units=2.0, food_in_window=False,
    ))
    session.commit()

    n = backfill_correction_iob(session)
    assert n == 1
    ev = session.query(CorrectionEvent).one()
    assert ev.iob_at_start == pytest.approx(6.0 * iob_fraction(30.0), abs=1e-6)
    # idempotent: nothing left to fill
    assert backfill_correction_iob(session) == 0
