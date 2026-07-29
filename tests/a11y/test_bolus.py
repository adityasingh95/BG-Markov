"""S-1003 — the calculator is usable while low (SDET).

`05b §2`. She may be entering numbers into this screen at BG 55, which is precisely when
a fiddly control or a colour-only warning stops working.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y

_URL = "/bolus?at=2026-01-01T12:30&carbs_g=900&current_bg=180"  # the flagged-typo state


@pytest.fixture()
def profile(live_server: str) -> None:
    """A profile with a usable ICR in the live server's own database.

    Without it the calculator correctly renders the profile-incomplete state, and these
    tests would grade a page other than the one they name — the same mistake as the
    readout a11y suite pointing at a nonexistent meal. The live server runs in-process,
    so `api.deps._get_engine()` is the very engine it is serving from.
    """
    import datetime as dt

    from api.deps import _get_engine
    from data.db import session_factory
    from data.tables import PatientProfile

    with session_factory(_get_engine())() as session:
        session.add(PatientProfile(
            effective_from=dt.date(2026, 1, 1), icr=9.0, isf=30.0, target_bg=135,
        ))
        session.commit()


def test_calculator_has_no_axe_violations(page: Page, live_server: str, profile: None) -> None:
    page.goto(live_server + _URL, wait_until="networkidle")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_numeric_fields_bring_up_a_numeric_keypad(page: Page, live_server: str) -> None:
    """05b §2 — a text keyboard at BG 55 is a real barrier."""
    page.goto(live_server + "/bolus", wait_until="networkidle")
    modes = page.eval_on_selector_all(
        "input[data-field-kind]", "els => els.map(e => e.getAttribute('inputmode'))"
    )
    assert modes and all(m == "numeric" for m in modes), modes


def test_no_horizontal_overflow_at_200pct_zoom(page: Page, live_server: str, profile: None) -> None:
    page.goto(live_server + _URL, wait_until="networkidle")
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.documentElement.style.zoom = '2'")
    overflow = page.evaluate(
        """() => {
            const el = document.scrollingElement || document.documentElement;
            return el.scrollWidth - el.clientWidth;
        }"""
    )
    assert overflow <= 1, f"horizontal overflow of {overflow}px at 200% zoom"


def test_the_implausible_flag_is_not_signalled_by_colour_alone(
    page: Page, live_server: str, profile: None
) -> None:
    """★ The most important thing on the page in this state is that the number is WRONG.
    If that is carried by a red tint, it is not carried at all."""
    page.goto(live_server + _URL, wait_until="networkidle")
    text = (page.text_content("main") or "").lower()
    assert "looks wrong" in text or "implausible" in text
    assert "re-check" in text
