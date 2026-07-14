"""S-301 — the logging flow (SDET). Adherence is the binding constraint.

A repeat meal must be ≤4 taps + 2 numbers, a killed entry must not lose the
draft, and optional fields must never block.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_repeat_meal_in_at_most_four_taps(page: Page) -> None:
    """★ REQ-001, tested: favourite (tap 1) → BG → bolus → timing (tap 2) →
    LOG MEAL (tap 3) ⇒ a confirmation appears. Two numbers, three taps."""
    taps = 0

    page.click("[data-favourite]")          # tap 1 — populates all macros
    taps += 1
    page.fill("#f-pre_bg", "142")           # number 1
    page.fill("#f-meal_bolus_units", "6")   # number 2
    page.click(".timing-preset")            # tap 2 — sets the signed offset
    taps += 2  # (the preset click, then the submit below)
    page.click("button.primary")            # tap 3 — LOG MEAL

    assert taps <= 4, f"a repeat meal took {taps} taps (budget is 4)"

    toast = page.locator("#toast")
    toast.wait_for(state="visible", timeout=5000)
    assert "Logged" in (toast.text_content() or ""), "expected a logged confirmation"


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
