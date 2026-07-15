"""S-306 — the /corrections form is accessible (05b §2). Browser-driven.

She may log a correction while impaired by a low; the correction form is held to
the same accessibility floor as the meal form. Written RED before the route
exists. See docs/stories/S-306.md.
"""

from __future__ import annotations

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y

_CLINICAL_NUMERIC = re.compile(r"bg|glucose|unit|correction", re.IGNORECASE)


def test_corrections_form_axe_clean(page: Page, live_server: str) -> None:
    page.goto(live_server + "/corrections", wait_until="networkidle")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_corrections_bg_and_units_are_inputmode_numeric(page: Page, live_server: str) -> None:
    page.goto(live_server + "/corrections", wait_until="networkidle")
    fields = page.eval_on_selector_all(
        "input",
        """els => els.map(e => ({
            name: e.getAttribute('name'),
            kind: e.getAttribute('data-field-kind'),
            inputmode: e.getAttribute('inputmode'),
            type: e.getAttribute('type'),
        }))""",
    )
    clinical = [
        f for f in fields
        if f.get("type") != "hidden"
        and (f.get("kind") or (f.get("name") and _CLINICAL_NUMERIC.search(f["name"])))
    ]
    assert clinical, "expected BG/units fields on the correction form"
    offenders = [f for f in clinical if f.get("inputmode") != "numeric"]
    assert not offenders, f"BG/units fields missing inputmode=numeric: {offenders}"


def test_corrections_asks_about_food_in_window(page: Page, live_server: str) -> None:
    """The 'will you be eating in the next 4 hours?' question must be present — it
    is what decides whether this is a clean ISF signal (F-3.2)."""
    page.goto(live_server + "/corrections", wait_until="networkidle")
    assert page.query_selector("[data-food-in-window]") is not None, (
        "expected the food-in-window question on the correction form"
    )


def test_corrections_base_font_at_least_18px(page: Page, live_server: str) -> None:
    page.goto(live_server + "/corrections", wait_until="networkidle")
    size_px = page.evaluate("parseFloat(getComputedStyle(document.body).fontSize)")
    assert size_px >= 18.0, f"base font {size_px}px < 18px"
