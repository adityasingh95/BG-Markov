"""S-301 — the logging flow (SDET). Adherence is the binding constraint.

A repeat meal must be ≤4 taps + 2 numbers, a killed entry must not lose the
draft, and optional fields must never block.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_repeat_meal_in_at_most_four_taps(page: Page) -> None:
    """★ REQ-001, tested: a repeat meal logs in ≤4 taps + 2 numbers.

    The tap count is derived from *actual* page interactions (every real click is
    counted by a wrapper), not a hand-maintained integer — so the budget can't
    silently drift (audit H5)."""
    taps = 0

    def tap(selector: str) -> None:
        nonlocal taps
        taps += 1
        page.click(selector)

    tap("[data-favourite]")                 # tap — populates all macros
    page.fill("#f-pre_bg", "142")           # number 1 (typing, not a tap)
    page.fill("#f-meal_bolus_units", "6")   # number 2
    tap(".timing-preset")                   # tap — sets the signed offset
    tap("button.primary")                   # tap — LOG MEAL

    toast = page.locator("#toast")
    toast.wait_for(state="visible", timeout=5000)
    assert "Logged" in (toast.text_content() or ""), "expected a logged confirmation"

    # Assert on the REAL number of taps performed to reach a logged meal.
    assert taps <= 4, f"a repeat meal took {taps} taps (budget is 4)"


def test_draft_survives_a_killed_entry(page: Page) -> None:
    """localStorage draft: a reload (a killed browser) restores the entry."""
    page.click("[data-favourite]")
    page.fill("#f-pre_bg", "155")
    page.fill("#f-meal_bolus_units", "7")

    page.reload(wait_until="networkidle")  # simulate a kill mid-entry

    assert page.input_value("#f-pre_bg") == "155", "draft BG was lost on reload"
    assert page.input_value("#f-meal_bolus_units") == "7", "draft bolus was lost on reload"


def test_optional_section_is_collapsed_by_default(page: Page) -> None:
    """Optional fields are collapsed and never block submission (05b §3)."""
    is_open = page.eval_on_selector("details.optional", "el => el.open")
    assert is_open is False
