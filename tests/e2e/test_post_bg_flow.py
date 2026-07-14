"""S-303 — the post-meal reading flow (SDET). Reported time, asked never assumed."""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def _log_a_meal(base_url: str) -> int:
    resp = httpx.post(base_url + "/api/meals", json={
        "idempotency_key": "55555555-5555-5555-5555-555555555555",
        "datetime": "2026-07-13T08:00:00", "meal_type": "breakfast",
        "pre_bg": 142, "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 45.0, "meal_bolus_units": 6.0, "bolus_offset_min": -15,
        "logged_by": "patient",
    }, timeout=5.0)
    resp.raise_for_status()
    return int(resp.json()["meal_id"])


def test_post_bg_form_asks_reported_time_and_saves(page: Page, live_server: str) -> None:
    meal_id = _log_a_meal(live_server)
    page.goto(live_server + f"/meals/{meal_id}/post-bg", wait_until="networkidle")

    # The reported "taken at" time is present and editable — never assumed.
    taken_at = page.query_selector("[data-post-bg-time]")
    assert taken_at is not None, "expected an editable reported reading-time field"
    assert taken_at.is_editable()

    page.fill("#f-post_bg", "168")
    page.click("button.primary")

    toast = page.locator("#toast")
    toast.wait_for(state="visible", timeout=5000)
    assert (toast.text_content() or "").strip(), "expected a save confirmation"
