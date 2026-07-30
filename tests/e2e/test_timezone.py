"""S-1018 (SDET) — the reported time survives the phone it was typed on. RED first.

★ **The test that would have caught it.** Every other browser test in this repo inherits
the container's timezone, which is UTC, so `new Date(local).toISOString()` round-trips to
the same numbers and the conversion looks harmless. It is only harmless in UTC.

She is not in UTC.
"""

from __future__ import annotations

import datetime as dt

import pytest
from playwright.sync_api import BrowserContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.e2e.conftest import assert_saved

pytestmark = pytest.mark.e2e

TYPED = "2026-07-28T08:00"


def _newest_meal(session: Session) -> object:
    from data.tables import MealEvent

    session.expire_all()
    return session.scalars(select(MealEvent).order_by(MealEvent.meal_id.desc())).first()


def test_a_breakfast_typed_at_0800_in_kolkata_is_stored_at_0800(
    browser_at: object, live_server: str, db_session: Session
) -> None:
    """★ The acceptance criterion. Typed 08:00, stored 08:00 — on a phone in India.

    Before the fix this stored **02:30**: `app.js` converted her local wall-clock time into
    a UTC instant, the schema accepted the offset, and SQLite wrote the shifted value back
    as a naive local datetime. Nothing raised. 02:30 is a plausible row.
    """
    context: BrowserContext = browser_at("Asia/Kolkata")  # type: ignore[operator]
    page = context.new_page()
    page.goto(live_server + "/", wait_until="networkidle")

    page.locator(".chip.favourite").first.click()
    page.fill("#meal-time", TYPED)
    page.fill("#f-pre_bg", "127")
    page.fill("#f-meal_bolus_units", "4")
    page.locator(".timing-preset", has_text="Just before").click()
    page.locator("button.primary").click()
    assert_saved(page)

    meal = _newest_meal(db_session)
    assert meal is not None
    stored: dt.datetime = meal.datetime  # type: ignore[attr-defined]
    assert stored.strftime("%Y-%m-%dT%H:%M") == TYPED, (
        f"she typed {TYPED} and the database holds {stored} — "
        "the reported time was relabelled by her UTC offset"
    )


def test_the_meal_type_and_the_hour_agree(
    browser_at: object, live_server: str, db_session: Session
) -> None:
    """★ The corruption was self-inconsistent inside a single row, and nothing checked.

    `meal_type` is decided in the browser from her LOCAL time, while `datetime` was being
    shifted to UTC — so the row said `breakfast` at 02:30. Two fields derived from one input
    disagreeing is the strongest available signal that the input was mangled, and it was
    being written to disk without comment.
    """
    context: BrowserContext = browser_at("Asia/Kolkata")  # type: ignore[operator]
    page = context.new_page()
    page.goto(live_server + "/", wait_until="networkidle")

    page.locator(".chip.favourite").first.click()
    page.fill("#meal-time", "2026-07-27T08:30")
    page.fill("#f-pre_bg", "133")
    page.fill("#f-meal_bolus_units", "5")
    page.locator(".timing-preset", has_text="Just before").click()
    page.locator("button.primary").click()
    assert_saved(page)

    meal = _newest_meal(db_session)
    assert meal is not None
    hour: int = meal.datetime.hour  # type: ignore[attr-defined]
    meal_type = str(meal.meal_type.value)  # type: ignore[attr-defined]
    assert meal_type == "breakfast"
    assert 5 <= hour <= 11, f"a meal labelled breakfast is stored at {hour:02d}h"


def test_the_post_meal_reading_saves_from_a_non_utc_phone(
    browser_at: object, live_server: str, db_session: Session
) -> None:
    """The 500 that lost her readings, driven from the browser that produced it."""
    from data.tables import MealEvent

    context: BrowserContext = browser_at("Asia/Kolkata")  # type: ignore[operator]
    page = context.new_page()
    page.goto(live_server + "/", wait_until="networkidle")
    page.locator(".chip.favourite").first.click()
    page.fill("#meal-time", "2026-07-26T13:00")
    page.fill("#f-pre_bg", "150")
    page.fill("#f-meal_bolus_units", "6")
    page.locator(".timing-preset", has_text="Just before").click()
    page.locator("button.primary").click()
    assert_saved(page)

    meal = _newest_meal(db_session)
    assert meal is not None
    meal_id: int = meal.meal_id  # type: ignore[attr-defined]

    page.goto(live_server + f"/meals/{meal_id}/post-bg", wait_until="networkidle")
    page.fill("#f-post_bg", "163")
    page.locator("button.primary").click()
    assert_saved(page)

    db_session.expire_all()
    saved = db_session.get(MealEvent, meal_id)
    assert saved is not None
    assert saved.post_bg == 163
    assert saved.elapsed_min == 120, "elapsed_min must be 120, not 120 ± an offset"
