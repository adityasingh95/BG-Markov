"""S-301 — POST /api/meals (SDET, written RED first).

The server stamps `logged_at`, never substitutes now() for a clinical timestamp,
requires `bolus_offset_min`, and returns test_at = reported datetime + 120 min.
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
from data.tables import BolusLog, MealEvent


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    create_all(engine)
    testing_session = session_factory(engine)

    def _override() -> Iterator[Session]:
        with testing_session() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "idempotency_key": "11111111-1111-1111-1111-111111111111",
        "datetime": "2026-07-13T08:00:00",
        "meal_type": "breakfast",
        "pre_bg": 142,
        "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 48.0,
        "protein_g": 14.0,
        "fat_g": 9.0,
        "fiber_g": 6.0,
        "macro_confidence": 95,
        "meal_bolus_units": 6.0,
        "correction_bolus_units": 0.5,
        "bolus_offset_min": -10,
        "logged_by": "patient",
    }
    payload.update(overrides)
    return payload


def test_missing_bolus_offset_is_rejected(client: tuple[TestClient, object]) -> None:
    """REQ-003: bolus_offset_min cannot be skipped -> 422."""
    api, _ = client
    payload = _payload()
    del payload["bolus_offset_min"]
    resp = api.post("/api/meals", json=payload)
    assert resp.status_code == 422


def test_logs_a_meal_and_returns_test_at(client: tuple[TestClient, sessionmaker[Session]]) -> None:
    api, testing_session = client
    resp = api.post("/api/meals", json=_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # test_at = reported datetime (08:00) + 120 min = 10:00, NEVER logged_at + 120
    assert body["test_at"].startswith("2026-07-13T10:00:00")
    assert "meal_id" in body

    with testing_session() as s:
        meal = s.query(MealEvent).one()
        assert meal.datetime == datetime(2026, 7, 13, 8, 0)      # reported
        assert meal.logged_at != meal.datetime                   # stamped separately
        assert meal.bolus_offset_min == -10
        assert meal.net_carbs_g == 42.0                          # 48 - 6, DB-computed


def test_writes_a_bolus_log_row_per_component(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    """REQ-006: meal bolus + correction bolus each land in bolus_log."""
    api, testing_session = client
    api.post("/api/meals", json=_payload(meal_bolus_units=6.0, correction_bolus_units=0.5))
    with testing_session() as s:
        boluses = s.query(BolusLog).all()
        units = sorted(b.units for b in boluses)
        assert units == [0.5, 6.0]
        assert all(b.logged_at is not None for b in boluses)
