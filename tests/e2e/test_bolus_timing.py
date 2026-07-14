"""S-302 [SAFETY] — bolus timing cannot be skipped (client side, SDET).

The form refuses to submit without a timing choice and never auto-fills 0.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def _fill_meal_without_timing(page: Page) -> None:
    page.click("[data-favourite]")
    page.fill("#f-pre_bg", "142")
    page.fill("#f-meal_bolus_units", "6")
    # deliberately choose NO timing


def test_submit_without_timing_is_blocked(page: Page) -> None:
    """No timing chosen ⇒ a prompt appears and nothing is logged (REQ-003)."""
    _fill_meal_without_timing(page)
    page.click("button.primary")

    error = page.locator("[data-timing-error]")
    error.wait_for(state="visible", timeout=3000)
    assert "timing" in (error.text_content() or "").lower()

    # The success confirmation must NOT appear — the meal was not logged.
    toast = page.locator("#toast")
    assert not toast.is_visible() or "Logged" not in (toast.text_content() or "")


def test_preset_15_min_before_maps_to_minus_15(page: Page) -> None:
    """"15 min before" ⇒ signed offset -15."""
    page.click("button.timing-preset:has-text('15 min before')")
    assert page.input_value("#f-bolus_offset_min") == "-15"


def test_choosing_timing_allows_the_log(page: Page) -> None:
    """The positive path: with a timing choice, the meal logs."""
    _fill_meal_without_timing(page)
    page.click("button.timing-preset:has-text('15 min before')")
    page.click("button.primary")
    toast = page.locator("#toast")
    toast.wait_for(state="visible", timeout=5000)
    assert "Logged" in (toast.text_content() or "")
