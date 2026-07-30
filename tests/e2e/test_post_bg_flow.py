"""S-303 — the post-meal reading flow (SDET). Reported time, asked never assumed.

★ **Rewritten by S-1021.** The original assertion was:

    assert (toast.text_content() or "").strip(), "expected a save confirmation"

It had been green since S-303 while the toast it was passing on read **"Could not save —
please try again."** The form 500s from a real browser and the test could not tell, because
any non-empty toast satisfied it — and the failure path writes a toast, which is what a good
error state does.

The assertion now reaches the row.
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page
from sqlalchemy.orm import Session

from tests.e2e.conftest import assert_saved

pytestmark = pytest.mark.e2e


def _log_a_meal(base_url: str, *, key: str = "55555555-5555-5555-5555-555555555555") -> int:
    resp = httpx.post(base_url + "/api/meals", json={
        "idempotency_key": key,
        "datetime": "2026-07-13T08:00:00", "meal_type": "breakfast",
        "pre_bg": 142, "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 45.0, "meal_bolus_units": 6.0, "bolus_offset_min": -15,
        "logged_by": "patient",
    }, timeout=5.0)
    resp.raise_for_status()
    return int(resp.json()["meal_id"])


def test_post_bg_form_asks_reported_time_and_saves(
    page: Page, live_server: str, db_session: Session
) -> None:
    from data.tables import MealEvent

    meal_id = _log_a_meal(live_server)
    page.goto(live_server + f"/meals/{meal_id}/post-bg", wait_until="networkidle")

    # The reported "taken at" time is present and editable — never assumed.
    taken_at = page.query_selector("[data-post-bg-time]")
    assert taken_at is not None, "expected an editable reported reading-time field"
    assert taken_at.is_editable()

    page.fill("#f-post_bg", "168")
    page.click("button.primary")

    assert_saved(page)

    # ★ The assertion that matters: the reading is in the database, with the elapsed time
    # derived from the REPORTED reading time. A toast is a claim; this is the record.
    meal = db_session.get(MealEvent, meal_id)
    assert meal is not None
    assert meal.post_bg == 168, "the toast said saved and the reading is not in the row"
    assert meal.elapsed_min == 120, (
        "elapsed_min must come from the reported reading time (meal 08:00 + 120)"
    )


def test_a_late_reading_is_saved_and_not_scolded(
    page: Page, live_server: str, db_session: Session
) -> None:
    """05b §4: feedback is non-judgemental. A late reading is still a reading."""
    from data.tables import MealEvent

    meal_id = _log_a_meal(live_server, key="55555555-5555-5555-5555-555555555556")
    page.goto(live_server + f"/meals/{meal_id}/post-bg", wait_until="networkidle")

    page.fill("#f-post_bg", "191")
    page.fill("#post-bg-time", "2026-07-13T11:30")  # 210 min — outside the window
    page.click("button.primary")

    text = assert_saved(page)
    assert "that's fine" in text, f"a late reading must not be scolded: {text!r}"

    meal = db_session.get(MealEvent, meal_id)
    assert meal is not None
    assert meal.post_bg == 191, "an out-of-window reading is still recorded"
    assert meal.elapsed_min == 210
