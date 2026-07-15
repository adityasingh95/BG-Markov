"""S-306 — correction-only event capture (SDET, written RED first).

A correction bolus with NO food is the only unconfounded read on ISF — the most
dangerous number in the system. This captures it in two phases (log now, +4 h
follow-up later), logs the injection to bolus_log (REQ-006), and exposes the
`07` §6 clean-signal accessor. `iob_at_start` is deferred to S-401 (nullable,
NULL now) — a NULL must never be admitted to the clean set.

RED: the endpoints, `record_correction_event`, `get_clean_correction_events`, and
the nullable columns do not exist yet.
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
from data.repositories import get_clean_correction_events
from data.tables import BolusLog, BolusType, CorrectionEvent, LoggedBy


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = make_engine(f"sqlite:///{tmp_path / 'corr.db'}")
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
    engine = make_engine(f"sqlite:///{tmp_path / 'corr_repo.db'}")
    create_all(engine)
    sess = session_factory(engine)()
    try:
        yield sess
    finally:
        sess.close()


def _event(**overrides: object) -> CorrectionEvent:
    """A directly-built correction event; iob_at_start defaults to NULL (deferred)."""
    fields: dict[str, object] = {
        "datetime": datetime(2026, 7, 13, 10, 15),
        "logged_at": datetime(2026, 7, 13, 14, 30),
        "bg_before": 210,
        "bg_after": 150,
        "bg_after_time": datetime(2026, 7, 13, 14, 15),
        "units": 2.0,
        "iob_at_start": None,
        "food_in_window": False,
    }
    fields.update(overrides)
    return CorrectionEvent(**fields)


# --- API: create ------------------------------------------------------------


def test_post_correction_event_persists_and_logs_the_bolus(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    resp = api.post("/api/correction-events", json={
        "datetime": "2026-07-13T10:15:00", "bg_before": 210, "units": 2.0,
        "food_in_window": False, "logged_by": "patient",
    })
    assert resp.status_code == 200, resp.text
    event_id = int(resp.json()["event_id"])

    with factory() as s:
        ev = s.get(CorrectionEvent, event_id)
        assert ev is not None
        assert ev.bg_before == 210
        assert ev.units == 2.0
        assert ev.iob_at_start is None  # deferred to S-401
        # REQ-006: the injection is in bolus_log as a correction, no meal.
        boluses = s.query(BolusLog).all()
        assert len(boluses) == 1
        assert boluses[0].bolus_type == BolusType.correction
        assert boluses[0].meal_id is None
        assert boluses[0].units == 2.0


def test_no_food_prompts_followup_at_reported_time_plus_4h(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """food_in_window False ⇒ +4 h prompt; alarm = REPORTED datetime + 4 h
    (10:15 → 14:15), never logged_at + 4 h (ADR-8)."""
    api, _ = client
    resp = api.post("/api/correction-events", json={
        "datetime": "2026-07-13T10:15:00", "bg_before": 210, "units": 2.0,
        "food_in_window": False, "logged_by": "patient",
    })
    body = resp.json()
    assert body["prompt_followup"] is True
    assert body["followup_at"].startswith("2026-07-13T14:15:00")
    assert "2:15" in body["message"]


def test_eating_soon_does_not_prompt_followup(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """food_in_window True ⇒ confounded, not an ISF signal ⇒ no +4 h prompt."""
    api, _ = client
    resp = api.post("/api/correction-events", json={
        "datetime": "2026-07-13T10:15:00", "bg_before": 210, "units": 2.0,
        "food_in_window": True, "logged_by": "patient",
    })
    assert resp.json()["prompt_followup"] is False


# --- API: follow-up ---------------------------------------------------------


def test_followup_stores_reported_after_reading(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    event_id = int(api.post("/api/correction-events", json={
        "datetime": "2026-07-13T10:15:00", "bg_before": 210, "units": 2.0,
        "food_in_window": False, "logged_by": "patient",
    }).json()["event_id"])

    resp = api.patch(f"/api/correction-events/{event_id}/followup", json={
        "bg_after": 150, "bg_after_time": "2026-07-13T14:20:00", "food_in_window": False,
    })
    assert resp.status_code == 200, resp.text
    with factory() as s:
        ev = s.get(CorrectionEvent, event_id)
        assert ev is not None
        assert ev.bg_after == 150
        assert ev.bg_after_time == datetime(2026, 7, 13, 14, 20)  # reported


def test_followup_on_unknown_event_is_404(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, _ = client
    resp = api.patch("/api/correction-events/999999/followup", json={
        "bg_after": 150, "bg_after_time": "2026-07-13T14:20:00", "food_in_window": False,
    })
    assert resp.status_code == 404


# --- ★ the clean-signal accessor (07 §6) ------------------------------------


def test_clean_events_exclude_food_in_window_and_unknown_iob(session: Session) -> None:
    """★ 07 §6: a clean ISF event has food_in_window == False AND a KNOWN
    iob_at_start < 0.5. A NULL IOB (deferred) is NOT clean — it must be excluded,
    or the deferral would silently poison ISF."""
    clean = _event(food_in_window=False, iob_at_start=0.2)     # the only clean one
    confounded_food = _event(food_in_window=True, iob_at_start=0.1)
    confounded_iob = _event(food_in_window=False, iob_at_start=0.8)
    pending_iob = _event(food_in_window=False, iob_at_start=None)  # deferred → not clean
    session.add_all([clean, confounded_food, confounded_iob, pending_iob])
    session.commit()

    events = get_clean_correction_events(session)
    assert [e.event_id for e in events] == [clean.event_id]


def test_clean_events_empty_before_iob_backfill(session: Session) -> None:
    """Realistic pre-S-401 state: every captured event has iob_at_start NULL, so
    the clean set is empty — no ISF can be derived yet, and that is correct."""
    session.add_all([
        _event(food_in_window=False, iob_at_start=None),
        _event(food_in_window=False, iob_at_start=None),
    ])
    session.commit()
    assert get_clean_correction_events(session) == []


def test_reported_datetime_is_not_the_log_time(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """ADR-8: the stored event datetime is the reported value, distinct from the
    system-clock logged_at."""
    api, factory = client
    event_id = int(api.post("/api/correction-events", json={
        "datetime": "2026-07-13T10:15:00", "bg_before": 210, "units": 2.0,
        "food_in_window": False, "logged_by": "patient",
    }).json()["event_id"])
    with factory() as s:
        ev = s.get(CorrectionEvent, event_id)
        assert ev is not None
        assert ev.datetime == datetime(2026, 7, 13, 10, 15)
        assert ev.logged_at != ev.datetime  # logged_at is the system clock
        # logged_by lives on the bolus_log row (the injection), not the event.
        assert s.query(BolusLog).one().logged_by == LoggedBy.patient
