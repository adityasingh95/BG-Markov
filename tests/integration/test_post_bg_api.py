"""S-303 — PATCH /api/meals/{id}/post-bg + test-time prompt (SDET, RED first).

post_bg_time is reported (required); elapsed_min is computed from reported times;
the record is stored regardless of validity; the test-time prompt is reported
mealtime + 120 (never logged_at + 120).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.tables import MealEvent


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = make_engine(f"sqlite:///{tmp_path / 'postbg.db'}")
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


def _log_meal(api: TestClient, **overrides: object) -> int:
    payload: dict[str, object] = {
        "idempotency_key": "33333333-3333-3333-3333-333333333333",
        "datetime": "2026-07-13T08:00:00",
        "meal_type": "breakfast",
        "pre_bg": 142,
        "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 45.0,
        "meal_bolus_units": 6.0,
        "bolus_offset_min": -15,
        "logged_by": "patient",
    }
    payload.update(overrides)
    resp = api.post("/api/meals", json=payload)
    assert resp.status_code == 200, resp.text
    return int(resp.json()["meal_id"])


def test_test_time_prompt_is_reported_mealtime_plus_120(client: tuple[TestClient, object]) -> None:
    """REQ-014: log at any time for an 08:00 meal ⇒ test_at 10:00, not 11:40."""
    api, _ = client
    resp = api.post("/api/meals", json={
        "idempotency_key": "44444444-4444-4444-4444-444444444444",
        "datetime": "2026-07-13T08:00:00", "meal_type": "breakfast",
        "pre_bg": 142, "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 45.0, "meal_bolus_units": 6.0, "bolus_offset_min": -15,
        "logged_by": "patient",
    })
    body = resp.json()
    assert body["test_at"].startswith("2026-07-13T10:00:00")
    assert "10:00" in body["message"]


def test_post_bg_computes_elapsed_from_reported_time(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, _ = client
    meal_id = _log_meal(api)  # reported mealtime 08:00
    resp = api.patch(f"/api/meals/{meal_id}/post-bg", json={
        "post_bg": 168, "post_bg_time": "2026-07-13T10:05:00",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["elapsed_min"] == 125  # 08:00 -> 10:05, from reported times
    assert body["is_valid"] is True
    assert body["exclusion_reasons"] == []


def test_post_bg_time_is_required(client: tuple[TestClient, object]) -> None:
    api, _ = client
    meal_id = _log_meal(api)
    resp = api.patch(f"/api/meals/{meal_id}/post-bg", json={"post_bg": 168})
    assert resp.status_code == 422  # never assumed


def test_out_of_window_reading_is_stored_regardless(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    meal_id = _log_meal(api)  # 08:00
    resp = api.patch(f"/api/meals/{meal_id}/post-bg", json={
        "post_bg": 168, "post_bg_time": "2026-07-13T11:40:00",  # elapsed 220
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is False
    assert "outside_window" in body["exclusion_reasons"]
    # ...and the record is KEPT (adherence cannot be diagnosed from discarded data)
    with factory() as s:
        meal = s.get(MealEvent, meal_id)
        assert meal is not None
        assert meal.post_bg == 168
        assert meal.elapsed_min == 220


def test_post_bg_on_unknown_meal_is_404(client: tuple[TestClient, object]) -> None:
    api, _ = client
    resp = api.patch("/api/meals/999999/post-bg", json={
        "post_bg": 168, "post_bg_time": "2026-07-13T10:05:00",
    })
    assert resp.status_code == 404
