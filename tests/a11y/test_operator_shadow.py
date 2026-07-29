"""S-1001a — the report card is readable (SDET, written RED first).

`05b §2` is non-negotiable and it applies to the operator too: he may be reading this at
2am, on a phone, deciding something serious. **Colour is never the sole signal** — a
Better/Worse badge that only differs by hue is invisible to a colour-blind reader and to
anyone on a washed-out screen.

RED: `GET /operator/shadow` does not exist.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y


def test_report_card_has_no_axe_violations(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/operator/shadow")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_no_horizontal_overflow_at_200_percent_zoom(page: Page, base_url: str) -> None:
    """A table of metrics is the classic thing that breaks at 200%."""
    page.set_viewport_size({"width": 320, "height": 720})
    page.goto(f"{base_url}/operator/shadow")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert overflow is False, "the report card scrolls horizontally at 200% zoom"


def test_every_verdict_badge_carries_text_not_colour_alone(page: Page, base_url: str) -> None:
    """★ 05b §2. The meaning must survive with no colour vision at all."""
    page.goto(f"{base_url}/operator/shadow")
    badges = page.eval_on_selector_all(
        "[data-verdict]", "els => els.map(e => e.textContent.trim())"
    )
    for text in badges:
        assert text, "a verdict badge rendered with no text — colour would be its only signal"
