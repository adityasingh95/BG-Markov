"""S-1018 (SDET) — the API refuses an offset on any reported clinical timestamp. RED first.

The server half of the fix. Fixing only the JS would leave the endpoint happy to accept an
offset from any other client — a cached script, a curl, a future shortcut — and the
corruption would return without a code change.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'tz.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()

_MEAL = {
    "idempotency_key": "aaaaaaaa-0000-0000-0000-00000000tz01",
    "datetime": "2026-07-30T08:00:00",
    "meal_type": "breakfast",
    "pre_bg": 142,
    "pre_bg_time": "2026-07-30T07:55:00",
    "carbs_g": 45.0,
    "meal_bolus_units": 6.0,
    "bolus_offset_min": -10,
    "logged_by": "patient",
}


def _meal(**overrides: object) -> dict[str, object]:
    payload = dict(_MEAL)
    payload.update(overrides)
    return payload


def test_a_naive_meal_payload_still_works(client: TestClient) -> None:
    """The regression a blunt fix causes: refusing everything refuses her too."""
    resp = client.post("/api/meals", json=_meal())
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("suffix", ["Z", "+05:30", "+00:00", "-07:00"])
def test_an_offset_on_the_meal_datetime_is_a_422(client: TestClient, suffix: str) -> None:
    resp = client.post("/api/meals", json=_meal(
        idempotency_key=f"bbbbbbbb-0000-0000-0000-{abs(hash(suffix)) % 10**12:012d}",
        datetime=f"2026-07-30T08:00:00{suffix}",
    ))
    assert resp.status_code == 422, resp.text
    assert "datetime" in resp.text


def test_an_offset_on_pre_bg_time_is_a_422(client: TestClient) -> None:
    resp = client.post("/api/meals", json=_meal(
        idempotency_key="cccccccc-0000-0000-0000-000000000001",
        pre_bg_time="2026-07-30T07:55:00Z",
    ))
    assert resp.status_code == 422, resp.text
    assert "pre_bg_time" in resp.text


def test_an_offset_on_the_post_bg_time_is_a_422_not_a_500(client: TestClient) -> None:
    """★ The exact request the browser was sending, and the exact 500 it produced.

    A 422 is a refusal she can be told about. A 500 is a lost reading and a toast that says
    "try again" forever.
    """
    created = client.post("/api/meals", json=_meal(
        idempotency_key="dddddddd-0000-0000-0000-000000000001"))
    assert created.status_code == 200, created.text
    meal_id = created.json()["meal_id"]

    resp = client.patch(f"/api/meals/{meal_id}/post-bg", json={
        "post_bg": 168, "post_bg_time": "2026-07-30T10:00:00.000Z",
    })
    assert resp.status_code == 422, resp.text
    assert "post_bg_time" in resp.text


def test_a_naive_post_bg_still_saves(client: TestClient) -> None:
    created = client.post("/api/meals", json=_meal(
        idempotency_key="eeeeeeee-0000-0000-0000-000000000001"))
    meal_id = created.json()["meal_id"]
    resp = client.patch(f"/api/meals/{meal_id}/post-bg", json={
        "post_bg": 168, "post_bg_time": "2026-07-30T10:00:00",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["elapsed_min"] == 120


def test_an_offset_on_a_correction_is_a_422(client: TestClient) -> None:
    resp = client.post("/api/correction-events", json={
        "datetime": "2026-07-30T14:00:00+05:30",
        "bg_before": 244, "units": 2.0, "food_in_window": False,
    })
    assert resp.status_code == 422, resp.text
    assert "datetime" in resp.text


def test_a_naive_correction_still_works(client: TestClient) -> None:
    resp = client.post("/api/correction-events", json={
        "datetime": "2026-07-30T14:00:00",
        "bg_before": 244, "units": 2.0, "food_in_window": False,
    })
    assert resp.status_code == 200, resp.text


def test_an_offset_on_a_correction_followup_is_a_422(client: TestClient) -> None:
    created = client.post("/api/correction-events", json={
        "datetime": "2026-07-30T15:00:00",
        "bg_before": 250, "units": 2.0, "food_in_window": False,
    })
    event_id = created.json()["event_id"]
    resp = client.patch(f"/api/correction-events/{event_id}/followup", json={
        "bg_after": 150, "bg_after_time": "2026-07-30T19:00:00Z", "food_in_window": False,
    })
    assert resp.status_code == 422, resp.text
    assert "bg_after_time" in resp.text


def test_logged_at_is_not_touched_by_this_rule(client: TestClient, db: Session) -> None:
    """★ `logged_at` is a SYSTEM timestamp and none of this story's business.

    It is bound to the injected clock (S-202), never supplied by a client, and it is the one
    field where an instant is the right idea. A validator applied to it by analogy would be
    a different, unrequested change to ADR-8's other half.
    """
    from data.tables import MealEvent

    created = client.post("/api/meals", json=_meal(
        idempotency_key="ffffffff-0000-0000-0000-000000000001"))
    meal_id = created.json()["meal_id"]

    meal = db.get(MealEvent, meal_id)
    assert meal is not None
    assert meal.logged_at is not None
    assert meal.logged_at != meal.datetime
