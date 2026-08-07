"""S-1019 (SDET) — a retried submission records one meal and one bolus. RED first.

S-1016 made the server refuse a duplicate. It is correct, tested nine ways, and **it has
never once been reached from the UI**: `app.js` mints a fresh `crypto.randomUUID()` inside
`payload()`, which runs once per submit. Two taps, two keys, two meals, two boluses.

★ A guard whose input is supplied by the caller is only as good as the caller. Every S-1016
test supplied the key itself, so all of them tested the server's half of a two-party
protocol and none of them tested the other half.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, Route
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.e2e.conftest import FAILURE_TOASTS, assert_saved

pytestmark = pytest.mark.e2e


def _counts(session: Session) -> tuple[int, int]:
    from data.tables import BolusLog, MealEvent

    session.expire_all()
    meals = session.scalar(select(func.count()).select_from(MealEvent)) or 0
    boluses = session.scalar(select(func.count()).select_from(BolusLog)) or 0
    return meals, boluses


def _fill(page: Page, *, when: str, bg: str, units: str) -> None:
    page.locator(".chip.favourite").first.click()
    page.fill("#meal-time", when)
    page.fill("#f-pre_bg", bg)
    page.fill("#f-meal_bolus_units", units)
    page.locator(".timing-preset", has_text="Just before").click()


def test_two_taps_record_one_meal_and_one_bolus(
    page: Page, live_server: str, db_session: Session
) -> None:
    """★ The headline assertion is on `bolus_log`, not the meal count.

    Following S-1016: an implementation that dedupes the meal and re-inserts the boluses
    passes a meal-count test and preserves the entire harm. `bolus_log` is REQ-006's sole
    source of truth for IOB, the calculator subtracts IOB, and the demo measured the end of
    that chain — IOB 7.26 → 14.26 U, recommended dose 6.91 U → 0.00 U.
    """
    before_meals, before_boluses = _counts(db_session)

    _fill(page, when="2026-07-20T12:30", bg="141", units="6")
    button = page.locator("button.primary")
    button.click()
    button.click(force=True)  # the second tap, immediately
    assert_saved(page)
    page.wait_for_timeout(1000)  # let a second request land, if one was sent

    after_meals, after_boluses = _counts(db_session)
    assert after_meals - before_meals == 1, "a double tap created more than one meal"
    assert after_boluses - before_boluses == 1, (
        "a double tap created a SECOND BOLUS — IOB is now overstated and every later "
        "recommendation will be too small"
    )


def test_two_separate_entries_still_create_two_meals(
    page: Page, live_server: str, db_session: Session
) -> None:
    """★ The failure mode of an over-eager fix, and the worse one.

    A key that never rotates makes her second breakfast disappear — silently, with a ✓ on
    screen. Losing a meal she logged is worse than logging one twice, because a duplicate is
    visible in the data and an absence is not.
    """
    before_meals, _ = _counts(db_session)

    _fill(page, when="2026-07-21T08:00", bg="128", units="5")
    page.locator("button.primary").click()
    assert_saved(page)

    page.reload(wait_until="networkidle")
    _fill(page, when="2026-07-21T13:00", bg="163", units="7")
    page.locator("button.primary").click()
    assert_saved(page)
    page.wait_for_timeout(500)

    after_meals, _ = _counts(db_session)
    assert after_meals - before_meals == 2, "two genuine meals were collapsed into one"


def test_a_lost_response_is_safe_to_retry(
    page: Page, live_server: str, db_session: Session
) -> None:
    """★ The case the KEY protects, isolated from the disabled button.

    The first request reaches the server and is recorded; the response is then dropped, so
    the browser reports a failure and the draft is kept. She presses Log again. The second
    request must carry the SAME key and the server must return the meal it already has.

    Written this way deliberately. The double-tap test above is also satisfied by disabling
    the button, so on its own it cannot tell whether the key works — an adversarial plant
    that restored per-submit minting left it green. This one cannot pass without the key.
    """
    dropped = {"once": False}

    def _drop_the_first_response(route: Route) -> None:
        if not dropped["once"]:
            dropped["once"] = True
            route.fetch()   # the server DOES record it...
            route.abort()   # ...and the browser never learns
            return
        route.continue_()

    page.route("**/api/meals", _drop_the_first_response)
    before_meals, before_boluses = _counts(db_session)

    _fill(page, when="2026-07-22T19:00", bg="150", units="6")
    button = page.locator("button.primary")

    button.click()
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
    assert (page.locator("#toast").text_content() or "").strip() in FAILURE_TOASTS, (
        "a dropped response must be reported as a failure she can retry"
    )

    # ★ Clear the failure toast before retrying, so the assertion below cannot possibly be
    # reading the PREVIOUS attempt's message. Without this the test is racing the app's own
    # clear-then-write, and a stale read is indistinguishable from a real result.
    page.evaluate("document.querySelector('#toast').textContent = ''")

    button.click()          # she presses Log again
    assert_saved(page)
    page.wait_for_timeout(500)

    after_meals, after_boluses = _counts(db_session)
    assert after_meals - before_meals == 1, (
        "the retry created a SECOND meal — the key did not survive the failed attempt"
    )
    assert after_boluses - before_boluses == 1, "the retry created a second bolus"


def test_the_key_survives_a_reload_mid_entry(
    page: Page, live_server: str, db_session: Session
) -> None:
    """A restored draft is the SAME submission.

    The draft already survives a killed browser (S-301). If the key did not survive with it,
    the crash-and-retry case — the one the draft exists for — would double-log.
    """
    dropped = {"once": False}

    def _drop_the_first_response(route: Route) -> None:
        if not dropped["once"]:
            dropped["once"] = True
            route.fetch()
            route.abort()
            return
        route.continue_()

    page.route("**/api/meals", _drop_the_first_response)
    before_meals, before_boluses = _counts(db_session)

    _fill(page, when="2026-07-23T19:00", bg="144", units="5")
    page.locator("button.primary").click()
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)

    page.reload(wait_until="networkidle")   # killed browser; the draft comes back
    assert page.input_value("#f-pre_bg") == "144", "the draft did not survive"
    page.locator("button.primary").click()
    assert_saved(page)
    page.wait_for_timeout(500)

    after_meals, after_boluses = _counts(db_session)
    assert after_meals - before_meals == 1, "a restored draft submitted again double-logged"
    assert after_boluses - before_boluses == 1


def test_the_submit_button_is_disabled_while_in_flight(page: Page, live_server: str) -> None:
    """Belt as well as braces — and the only part of this she can actually see.

    The key makes a duplicate harmless. The disabled button makes it not happen, which is
    also the honest feedback: pressing a button that appears to do nothing is why people
    press it again.
    """
    _fill(page, when="2026-07-23T09:15", bg="137", units="4")

    # A MutationObserver rather than a sleep-and-peek: the in-flight window is short and
    # timing-dependent, and a test that races the network is a test that will one day fail
    # for a reason nobody can reproduce.
    page.evaluate(
        """() => {
            window.__disabledSeen = false;
            const b = document.querySelector('button.primary');
            new MutationObserver(() => { if (b.disabled) window.__disabledSeen = true; })
                .observe(b, { attributes: true, attributeFilter: ['disabled'] });
        }"""
    )

    button = page.locator("button.primary")
    button.click()
    assert_saved(page)

    assert page.evaluate("() => window.__disabledSeen") is True, (
        "the submit button was never disabled — pressing a button that appears to do "
        "nothing is why people press it again"
    )
    assert button.is_enabled(), "the button must be usable again once the save completed"
