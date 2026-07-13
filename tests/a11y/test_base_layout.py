"""S-102 — accessible base layout. Browser-driven a11y specification.

The requirement source is ``docs/05b-ui-ux-spec.md §2`` (Accessibility —
Non-Negotiable). She may be logging *while cognitively impaired by a low*; these
are patient-safety tests, not polish. Written RED before any ``api/`` code.
"""

from __future__ import annotations

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y

# Fields that are semantically BG / dose / clinical-numeric. A field whose
# name/id/data-field-kind matches this must render inputmode="numeric" so the
# phone shows a numeric keypad — even at BG 55.
_CLINICAL_NUMERIC = re.compile(
    r"bg|glucose|bolus|dose|carb|unit|correction|basal", re.IGNORECASE
)


def _clinical_numeric_inputs(page: Page) -> list[dict[str, str | None]]:
    return page.eval_on_selector_all(
        "input",
        """els => els.map(e => ({
            name: e.getAttribute('name'),
            id: e.getAttribute('id'),
            kind: e.getAttribute('data-field-kind'),
            inputmode: e.getAttribute('inputmode'),
            type: e.getAttribute('type'),
        }))""",
    )


def _is_clinical_numeric(el: dict[str, str | None]) -> bool:
    if el.get("kind"):
        return True
    token = " ".join(v for v in (el.get("name"), el.get("id")) if v)
    return bool(_CLINICAL_NUMERIC.search(token))


def test_axe_no_violations(page: Page) -> None:
    """axe-core finds zero accessibility violations on the base layout."""
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_every_bg_dose_field_is_inputmode_numeric(page: Page) -> None:
    """Every BG/dose field renders inputmode="numeric" (05b §2)."""
    clinical = [el for el in _clinical_numeric_inputs(page) if _is_clinical_numeric(el)]
    assert clinical, "expected at least one BG/dose field on the base layout"
    offenders = [el for el in clinical if el.get("inputmode") != "numeric"]
    assert not offenders, f"BG/dose fields missing inputmode=numeric: {offenders}"


def test_base_font_at_least_18px(page: Page) -> None:
    """Base font ≥ 18px (05b §2)."""
    size_px = page.evaluate(
        "parseFloat(getComputedStyle(document.body).fontSize)"
    )
    assert size_px >= 18.0, f"base font {size_px}px < 18px"


def test_touch_targets_at_least_48px(page: Page) -> None:
    """Every button and primary numeric input is ≥ 48 × 48 px (05b §2)."""
    boxes = page.eval_on_selector_all(
        "button, [role=button], input[data-field-kind]",
        """els => els.map(e => {
            const r = e.getBoundingClientRect();
            return {tag: e.tagName, w: r.width, h: r.height,
                    label: (e.textContent||e.getAttribute('name')||'').trim()};
        })""",
    )
    assert boxes, "expected buttons / numeric inputs on the base layout"
    too_small = [b for b in boxes if b["w"] < 48 or b["h"] < 48]
    assert not too_small, f"touch targets below 48x48: {too_small}"


def test_no_select_for_dish_selection(page: Page) -> None:
    """Dish selection uses search + recents, never a <select> dropdown (05b §2)."""
    dish_selects = page.eval_on_selector_all(
        "select",
        "els => els.map(e => e.getAttribute('name') || e.id || '')",
    )
    dishy = [s for s in dish_selects if re.search(r"dish|meal|food", s, re.IGNORECASE)]
    assert not dishy, f"dish selection must not use <select>: {dishy}"
    # The dish picker must actually exist as a search affordance.
    assert page.query_selector("[data-dish-search]") is not None, (
        "expected a dish search affordance (search + recents), none found"
    )


def test_bolus_timing_is_inputtable_not_only_presets(page: Page) -> None:
    """bolus_offset_min is a signed continuous value (REQ-003): the timing group
    must offer a numeric entry field, not only preset quick-pick chips. The
    presets are for speed; the field is for any offset the presets don't cover.
    (Full signed / cannot-be-skipped capture is S-302; here it must at least be
    inputtable and accessible.)"""
    timing = page.query_selector("fieldset.timing, [aria-label='Bolus timing']")
    assert timing is not None, "expected a bolus-timing group"
    # Preset quick-picks still present.
    assert timing.query_selector("button") is not None, "expected preset timing chips"
    # ...and a numeric offset field alongside them.
    field = page.query_selector("input[name='bolus_offset_min']")
    assert field is not None, "bolus timing must be inputtable (a numeric offset field)"
    assert field.get_attribute("inputmode") == "numeric", "timing field needs inputmode=numeric"


def test_bolus_timing_supports_signed_before_and_after(page: Page) -> None:
    """bolus_offset_min is SIGNED — negative = pre-bolus, positive = after eating.
    The custom entry must let her express both directions, and (REQ-003) must not
    silently default one: no direction is pre-selected."""
    dirs = page.eval_on_selector_all(
        "fieldset.timing [data-dir], [aria-label='Bolus timing'] [data-dir]",
        "els => els.map(e => e.getAttribute('data-dir'))",
    )
    assert "before" in dirs, "expected a 'before eating' (pre-bolus, negative) choice"
    assert "after" in dirs, "expected an 'after eating' (positive) choice"
    pressed = page.eval_on_selector_all(
        "fieldset.timing [data-dir], [aria-label='Bolus timing'] [data-dir]",
        "els => els.map(e => e.getAttribute('aria-pressed'))",
    )
    assert all(p != "true" for p in pressed), (
        "timing direction must not be pre-selected/defaulted (REQ-003)"
    )


def test_no_horizontal_overflow_at_200pct_zoom(page: Page) -> None:
    """Usable at 200% zoom — content reflows, no horizontal page scroll (05b §2)."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.documentElement.style.zoom = '2'")
    overflow = page.evaluate(
        """() => {
            const el = document.scrollingElement || document.documentElement;
            return el.scrollWidth - el.clientWidth;
        }"""
    )
    assert overflow <= 1, f"horizontal overflow of {overflow}px at 200% zoom"


def test_warning_not_signalled_by_colour_alone(page: Page) -> None:
    """A risk/warning cue is carried by text or icon, not colour alone (05b §2)."""
    warning = page.query_selector("[data-risk-cue]")
    assert warning is not None, "expected a risk/warning element on the base layout"
    text = (warning.text_content() or "").strip()
    has_icon = warning.query_selector("[aria-hidden='true']") is not None
    assert text, "warning conveys nothing without colour: empty text"
    assert has_icon or len(text) > 3, (
        "warning must carry an icon or descriptive text, not colour alone"
    )
