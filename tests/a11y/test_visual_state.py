"""S-1022 (SDET) — selection state is visible, and not by colour alone. RED first.

`app.js` sets `aria-pressed` correctly and **no CSS reads it**, so the one thing the meal
form has to tell her — *which dish did I just tap?* — reaches a screen reader and nobody
else. Worse, `.chk` (the ✓) renders unconditionally, so **all three favourites look chosen
at all times.**

`05b §2` puts her at BG 55 on a phone. REQ-001's whole adherence argument is that a repeat
meal takes ≤4 taps; a control that looks identical before and after you press it is a
control you press again.

Everything here asserts on **computed style**. Asserting on `app.css` source text would
prove only that a rule was typed, not that it applies.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.a11y

_FAV = ".chip.favourite"


def _tick_is_visible(page: Page, chip_index: int) -> bool:
    """Is the ✓ inside this chip actually rendered?

    Checked through the box model, not through `textContent`: a tick hidden with
    `display: none` is still in the text, and a test reading text would call it visible.
    """
    return bool(page.eval_on_selector_all(
        f"{_FAV} .chk",
        "(els, i) => { const e = els[i]; const r = e.getBoundingClientRect();"
        " return r.width > 0 && r.height > 0"
        " && getComputedStyle(e).visibility !== 'hidden'; }",
        chip_index,
    ))


def _style(page: Page, selector: str, index: int, props: list[str]) -> dict[str, str]:
    return dict(page.eval_on_selector_all(
        selector,
        "(els, args) => { const s = getComputedStyle(els[args.i]);"
        " return args.props.map(p => [p, s.getPropertyValue(p)]); }",
        {"i": index, "props": props},
    ))


def test_an_unselected_favourite_shows_no_tick(page: Page) -> None:
    """★ RED: every favourite shows a ✓ before anything is tapped."""
    assert page.locator(_FAV).count() >= 2, "need at least two favourites to compare"
    ticks = [_tick_is_visible(page, i) for i in range(page.locator(_FAV).count())]
    assert not any(ticks), (
        f"favourites show a tick before being tapped: {ticks}. Every dish looks chosen, so "
        "the form cannot tell her which one she picked."
    )


def test_tapping_a_favourite_shows_its_tick_and_only_its_tick(page: Page) -> None:
    page.locator(_FAV).nth(1).click()
    count = page.locator(_FAV).count()
    ticks = [_tick_is_visible(page, i) for i in range(count)]
    assert ticks[1] is True, "the tapped favourite shows no tick"
    assert sum(ticks) == 1, f"more than one favourite looks chosen: {ticks}"


def test_changing_the_choice_moves_the_tick(page: Page) -> None:
    page.locator(_FAV).nth(0).click()
    page.locator(_FAV).nth(2).click()
    ticks = [_tick_is_visible(page, i) for i in range(page.locator(_FAV).count())]
    assert ticks[2] is True
    assert ticks[0] is False, "the previous choice still looks chosen"
    assert sum(ticks) == 1


def test_pressed_and_unpressed_differ_by_more_than_colour(page: Page) -> None:
    """★ The adversarial case, and the one `05b §2` names outright.

    A design that signals selection with background colour alone passes a naive
    "they look different" test and is **invisible in greyscale** — which is the state a
    colour-blind reader, a sun-washed phone screen, and a printed page are all in.

    So: at least one non-colour property must differ too.
    """
    page.locator(_FAV).nth(0).click()
    props = ["border-top-width", "border-left-width", "font-weight", "outline-width"]
    pressed = _style(page, _FAV, 0, props)
    unpressed = _style(page, _FAV, 1, props)
    differing = [p for p in props if pressed[p] != unpressed[p]]
    assert differing, (
        f"pressed and unpressed chips differ only by colour: {pressed} vs {unpressed}. "
        "05b §2: colour is never the sole signal."
    )


def test_only_one_timing_preset_is_pressed_at_a_time(page: Page) -> None:
    presets = page.locator(".timing-preset")
    presets.nth(0).click()
    presets.nth(2).click()
    pressed = page.eval_on_selector_all(
        ".timing-preset", "els => els.map(e => e.getAttribute('aria-pressed'))"
    )
    assert pressed.count("true") == 1, f"timing presets: {pressed}"


def test_the_before_after_pair_shows_which_one_is_chosen(page: Page) -> None:
    """The signed offset is REQ-003's whole point; which direction is chosen must be
    visible, not merely stored."""
    page.locator("[data-dir]").nth(0).click()
    props = ["border-top-width", "font-weight", "outline-width"]
    chosen = _style(page, "[data-dir]", 0, props)
    other = _style(page, "[data-dir]", 1, props)
    assert any(chosen[p] != other[p] for p in props), (
        f"before/after look identical once chosen: {chosen} vs {other}"
    )


def test_the_primary_action_is_visually_dominant(page: Page) -> None:
    """`Log meal` must not compete with a chip. Hierarchy asserted, not intended."""
    primary = page.eval_on_selector("button.primary", "e => e.getBoundingClientRect().width")
    chip = page.eval_on_selector(_FAV, "e => e.getBoundingClientRect().width")
    assert primary > chip * 1.5, (
        f"the primary action ({primary}px) is not dominant over a chip ({chip}px)"
    )


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_body_text_stays_readable_in_both_schemes(page: Page, scheme: str) -> None:
    """★ The half-done dark theme: set the background and leave the text hard-coded.

    Asserting *"a dark theme exists"* passes on exactly that. This asserts the text and the
    surface are actually far apart, in the scheme the phone is in.
    """
    page.emulate_media(color_scheme=scheme)
    page.reload(wait_until="networkidle")

    def luminance(rgb: str) -> float:
        nums = [float(n) for n in rgb.replace("rgba", "rgb").strip("rgb() ").split(",")[:3]]
        chan = []
        for n in nums:
            c = n / 255.0
            chan.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]

    style = _style(page, "body", 0, ["color", "background-color"])
    ink, surface = luminance(style["color"]), luminance(style["background-color"])
    lighter, darker = max(ink, surface), min(ink, surface)
    ratio = (lighter + 0.05) / (darker + 0.05)
    assert ratio >= 7.0, (
        f"body text contrast in {scheme} is {ratio:.1f}:1 — 05b §2 asks for AA as a "
        "MINIMUM, and she may be reading this at BG 55"
    )
