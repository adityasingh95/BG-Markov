"""S-1001a — the report card is readable (SDET, written RED first).

`05b §2` is non-negotiable and it applies to the operator too: he may be reading this at
2am, on a phone, deciding something serious. **Colour is never the sole signal** — a
Better/Worse badge that differs only by hue is invisible to a colour-blind reader and on
any washed-out screen.

RED: `GET /operator/shadow` does not exist.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y


def test_report_card_has_no_axe_violations(page: Page, live_server: str) -> None:
    page.goto(live_server + "/operator/shadow", wait_until="networkidle")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_no_horizontal_overflow_at_200pct_zoom(page: Page, live_server: str) -> None:
    """A table of metrics is the classic thing that breaks at 200% zoom (05b §2)."""
    page.goto(live_server + "/operator/shadow", wait_until="networkidle")
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.documentElement.style.zoom = '2'")
    overflow = page.evaluate(
        """() => {
            const el = document.scrollingElement || document.documentElement;
            return el.scrollWidth - el.clientWidth;
        }"""
    )
    assert overflow <= 1, f"horizontal overflow of {overflow}px at 200% zoom"


def test_the_gate_checklist_is_not_signalled_by_colour_alone(
    page: Page, live_server: str
) -> None:
    """★ 05b §2. Each of the five conditions must read as met/unmet with no colour vision
    at all — the tick is `aria-hidden`, so a screen reader needs the words beside it."""
    page.goto(live_server + "/operator/shadow", wait_until="networkidle")
    items = page.eval_on_selector_all(
        ".gate-checklist li", "els => els.map(e => e.textContent.trim())"
    )
    assert len(items) == 5, "the checklist must show all five Gate-1 conditions"
    for text in items:
        assert "met" in text.lower(), (
            "a checklist row conveys met/unmet by icon and colour only: " + text
        )
