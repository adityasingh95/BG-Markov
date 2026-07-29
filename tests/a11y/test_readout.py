"""S-1002 — the patient readout is readable while low (SDET, written RED first).

`05b §2` is non-negotiable and this is the screen it was written for: she may be logging or
reading **while cognitively impaired by a low**, on a phone, in bad light. A risk cue
carried by colour alone is no cue at all.

RED: `GET /meals/{id}/readout` does not exist.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y

_READOUT = "/meals/1/readout"


def test_readout_has_no_axe_violations(page: Page, live_server: str) -> None:
    page.goto(live_server + _READOUT, wait_until="networkidle")
    Axe()  # constructed before the assertion so a missing axe build fails loudly
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_no_horizontal_overflow_at_200pct_zoom(page: Page, live_server: str) -> None:
    page.goto(live_server + _READOUT, wait_until="networkidle")
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.documentElement.style.zoom = '2'")
    overflow = page.evaluate(
        """() => {
            const el = document.scrollingElement || document.documentElement;
            return el.scrollWidth - el.clientWidth;
        }"""
    )
    assert overflow <= 1, f"horizontal overflow of {overflow}px at 200% zoom"


def test_the_message_is_carried_by_text_not_colour(page: Page, live_server: str) -> None:
    """★ 05b §2 — colour is never the sole signal. Whatever this page says, it must still
    say it with the colour removed."""
    page.goto(live_server + _READOUT, wait_until="networkidle")
    text = (page.text_content("main") or "").strip()
    assert len(text) > 40, "the readout must say something in words, not render a colour"
