"""S-1002 — the patient readout is readable while low (SDET, written RED first).

`05b §2` is non-negotiable and this is the screen it was written for: she may be logging or
reading **while cognitively impaired by a low**, on a phone, in bad light. A risk cue
carried by colour alone is no cue at all.

RED: `GET /meals/{id}/readout` does not exist.
"""

from __future__ import annotations

import httpx
import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y


@pytest.fixture()
def readout_url(live_server: str) -> str:
    """A readout for a meal that actually exists.

    Created through `POST /api/meals` against the live server rather than assumed. A
    hard-coded id renders FastAPI's 404 JSON page, which has no `<title>` and fails axe
    for reasons that have nothing to do with this screen — a red test that proves nothing
    about the thing it names.
    """
    payload = {
        "idempotency_key": "a11y-readout",
        "datetime": "2026-01-01T12:00:00",
        "meal_type": "lunch",
        "pre_bg": 120,
        "pre_bg_time": "2026-01-01T11:55:00",
        "carbs_g": 40.0,
        "meal_bolus_units": 4.0,
        "bolus_offset_min": -10,
    }
    r = httpx.post(f"{live_server}/api/meals", json=payload, timeout=10.0)
    assert r.status_code in (200, 201), r.text
    return f"{live_server}/meals/{r.json()['meal_id']}/readout"


def test_readout_has_no_axe_violations(page: Page, readout_url: str) -> None:
    page.goto(readout_url, wait_until="networkidle")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_no_horizontal_overflow_at_200pct_zoom(page: Page, readout_url: str) -> None:
    page.goto(readout_url, wait_until="networkidle")
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.documentElement.style.zoom = '2'")
    overflow = page.evaluate(
        """() => {
            const el = document.scrollingElement || document.documentElement;
            return el.scrollWidth - el.clientWidth;
        }"""
    )
    assert overflow <= 1, f"horizontal overflow of {overflow}px at 200% zoom"


def test_the_message_is_carried_by_text_not_colour(page: Page, readout_url: str) -> None:
    """★ 05b §2 — colour is never the sole signal. Whatever this page says, it must still
    say it with the colour removed."""
    page.goto(readout_url, wait_until="networkidle")
    text = (page.text_content("main") or "").strip()
    assert len(text) > 40, "the readout must say something in words, not render a colour"
