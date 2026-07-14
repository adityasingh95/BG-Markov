"""S-302 [SAFETY] — bolus timing cannot be skipped/defaulted (server side, SDET).

`bolus_offset_min` is required with no default; an absent or null value is a
422, never a silent 0.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.deps import get_session
from api.schemas import MealCreate
from data.db import create_all, make_engine, session_factory


@pytest.fixture
def api(tmp_path: Path) -> Iterator[TestClient]:
    engine = make_engine(f"sqlite:///{tmp_path / 'timing.db'}")
    create_all(engine)
    factory = session_factory(engine)

    def _override() -> Iterator[object]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "idempotency_key": "22222222-2222-2222-2222-222222222222",
        "datetime": "2026-07-13T08:00:00",
        "meal_type": "lunch",
        "pre_bg": 130,
        "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 40.0,
        "meal_bolus_units": 5.0,
        "bolus_offset_min": -15,
        "logged_by": "patient",
    }
    payload.update(overrides)
    return payload


def test_schema_requires_bolus_offset_with_no_default() -> None:
    """The field must be required — a default would silently fabricate timing."""
    field = MealCreate.model_fields["bolus_offset_min"]
    assert field.is_required(), "bolus_offset_min must have no default (REQ-003)"


def test_null_bolus_offset_is_rejected(api: TestClient) -> None:
    resp = api.post("/api/meals", json=_payload(bolus_offset_min=None))
    assert resp.status_code == 422


def test_absent_bolus_offset_is_rejected(api: TestClient) -> None:
    payload = _payload()
    del payload["bolus_offset_min"]
    resp = api.post("/api/meals", json=payload)
    assert resp.status_code == 422


def test_a_deliberate_zero_offset_is_accepted(api: TestClient) -> None:
    """"With food" is a chosen 0 — distinct from unset, and allowed."""
    resp = api.post("/api/meals", json=_payload(bolus_offset_min=0))
    assert resp.status_code == 200
