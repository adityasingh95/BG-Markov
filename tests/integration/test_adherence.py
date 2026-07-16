"""S-307 — operator adherence dashboard metrics (SDET, written RED first).

Adherence is the bottleneck: Gate 1 needs 150 valid meals. This dashboard is the
operator's early-warning cockpit. The ★ metric — median(logged_at − datetime) —
must come from the two DISTINCT columns (the ADR-8 payoff); a fabricated value
would hide the recall-bias climb it exists to surface.

RED: data/adherence.py, GET /api/adherence, and GET /operator do not exist yet.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from api.app import app
from api.deps import get_session
from data.adherence import GATE1_VALID_MEALS, adherence_metrics
from data.db import create_all, make_engine, session_factory
from data.tables import LoggedBy, MealEvent, MealType

_BASE = datetime(2026, 1, 1, 8, 0)


def _meal(
    day: int,
    *,
    lag_min: int = 30,
    is_valid: bool = True,
    exclusion_reasons: str | None = None,
    has_outcome: bool = True,
) -> MealEvent:
    """A meal whose logged_at is `lag_min` after the reported datetime."""
    when = _BASE + timedelta(days=day)
    return MealEvent(
        datetime=when,
        logged_at=when + timedelta(minutes=lag_min),  # the transcription lag
        logged_by=LoggedBy.patient,
        meal_type=MealType.breakfast,
        pre_bg=120,
        pre_bg_time=when,
        meal_bolus_units=5.0,
        bolus_offset_min=-10,
        carbs_g=40.0,
        post_bg=(140 if has_outcome else None),
        post_bg_time=(when + timedelta(minutes=120) if has_outcome else None),
        elapsed_min=(120 if has_outcome else None),
        is_valid=is_valid,
        exclusion_reasons=exclusion_reasons,
    )


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'adh.db'}")
    create_all(engine)
    sess = session_factory(engine)()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = make_engine(f"sqlite:///{tmp_path / 'adh_api.db'}")
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


# --- counts / gate countdown ------------------------------------------------


def test_valid_meals_and_gate1_countdown(session: Session) -> None:
    session.add_all([
        _meal(0), _meal(1), _meal(2),                       # 3 valid
        _meal(3, is_valid=False, exclusion_reasons="missing_outcome"),
        _meal(4, is_valid=False, exclusion_reasons="outside_window"),
    ])
    session.commit()
    m = adherence_metrics(session, now=_BASE + timedelta(days=10))
    assert m.valid_meals == 3
    assert m.meals_to_gate1 == GATE1_VALID_MEALS - 3
    assert GATE1_VALID_MEALS == 150


def test_exclusions_by_reason_counts_every_reason(session: Session) -> None:
    session.add_all([
        _meal(0),  # valid — contributes to no reason
        _meal(1, is_valid=False, exclusion_reasons="outside_window"),
        _meal(2, is_valid=False, exclusion_reasons="outside_window,low_confidence"),
    ])
    session.commit()
    m = adherence_metrics(session, now=_BASE + timedelta(days=10))
    assert m.exclusions_by_reason.get("outside_window") == 2
    assert m.exclusions_by_reason.get("low_confidence") == 1
    assert "missing_outcome" not in m.exclusions_by_reason


def test_in_window_rate_over_meals_with_outcome(session: Session) -> None:
    """4 outcomes, 1 outside_window ⇒ 3/4 in window."""
    session.add_all([
        _meal(0),
        _meal(1),
        _meal(2),
        _meal(3, is_valid=False, exclusion_reasons="outside_window"),
        _meal(4, has_outcome=False),  # no outcome yet — not counted in the rate
    ])
    session.commit()
    m = adherence_metrics(session, now=_BASE + timedelta(days=10))
    assert m.in_window_rate == pytest.approx(0.75)


def test_days_since_last_log_uses_injected_now(session: Session) -> None:
    session.add_all([_meal(0), _meal(5)])  # latest logged_at is day 5 + 30 min
    session.commit()
    now = _BASE + timedelta(days=8, hours=4)
    m = adherence_metrics(session, now=now)
    assert m.days_since_last_log == 3  # day 5 -> day 8 (whole days)


# --- ★ the transcription-lag metric ----------------------------------------


def test_median_lag_is_from_the_two_distinct_columns(session: Session) -> None:
    """★ median(logged_at − datetime) over lags {10, 40, 70} ⇒ 40, and it must
    NOT be 0 — a fabricated value (one column minus itself, or now−logged_at) is
    the exact bug this metric exists to catch."""
    session.add_all([_meal(0, lag_min=10), _meal(1, lag_min=40), _meal(2, lag_min=70)])
    session.commit()
    m = adherence_metrics(session, now=_BASE + timedelta(days=10))
    assert m.median_lag_min == 40
    assert m.median_lag_min != 0  # the columns differ; a 0 means fabricated


def test_empty_db_is_safe(session: Session) -> None:
    m = adherence_metrics(session, now=_BASE)
    assert m.valid_meals == 0
    assert m.meals_to_gate1 == GATE1_VALID_MEALS
    assert m.in_window_rate is None
    assert m.days_since_last_log is None
    assert m.median_lag_min is None
    assert m.exclusions_by_reason == {}


# --- API + dashboard --------------------------------------------------------


def test_api_adherence_returns_metrics(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    with factory() as s:
        s.add_all([_meal(0, lag_min=10), _meal(1, lag_min=40), _meal(2, lag_min=70)])
        s.commit()
    resp = api.get("/api/adherence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid_meals"] == 3
    assert body["meals_to_gate1"] == GATE1_VALID_MEALS - 3
    assert body["median_lag_min"] == 40


def test_operator_dashboard_renders(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    with factory() as s:
        s.add_all([_meal(0, lag_min=40)])
        s.commit()
    resp = api.get("/operator")
    assert resp.status_code == 200
    assert "to Gate 1" in resp.text
    assert "150" in resp.text  # the countdown target is visible
