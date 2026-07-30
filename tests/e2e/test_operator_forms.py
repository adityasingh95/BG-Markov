"""S-1020 (SDET) — the basal and profile forms save what she types. RED first.

Both post natively to a JSON endpoint, so the browser sends urlencoded, FastAPI 422s, and
**the browser navigates to the JSON error**. "Did not navigate" is half of what broke, so
both halves are asserted: the row exists, and she is still on the form.
"""

from __future__ import annotations

import datetime as dt

import pytest
from playwright.sync_api import Page
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.e2e.conftest import assert_saved

pytestmark = pytest.mark.e2e


def test_the_basal_form_records_the_daily_dose(
    page: Page, live_server: str, db_session: Session
) -> None:
    """★ `effective_basal` is an EWMA over these rows with a 25 h half-life, because
    Tresiba takes 3–4 days to reach steady state. A day she cannot record is a day the
    feature is stale — and it goes stale in a way that looks exactly like "she took the
    same dose again"."""
    from data.tables import BasalLog

    page.goto(live_server + "/basal", wait_until="networkidle")
    page.fill("#date", "2026-07-25")
    page.fill("#units", "26")
    page.fill("#time_taken", "22:15")
    page.locator('button[type="submit"]').click()

    assert_saved(page)
    assert page.url.rstrip("/").endswith("/basal"), (
        f"the browser navigated away to {page.url} — she left the app for a JSON blob"
    )

    db_session.expire_all()
    row = db_session.scalars(
        select(BasalLog).where(BasalLog.date == dt.date(2026, 7, 25))
    ).one()
    assert row.units == 26.0
    assert row.time_taken == dt.time(22, 15), "the REPORTED injection time, not a default"


def test_reposting_a_date_corrects_it_rather_than_duplicating(
    page: Page, live_server: str, db_session: Session
) -> None:
    """The S-1013 rule, now actually reachable: two rows would double-count in the EWMA
    and show a titration that never happened."""
    from data.tables import BasalLog

    for units in ("24", "30"):
        page.goto(live_server + "/basal", wait_until="networkidle")
        page.fill("#date", "2026-07-26")
        page.fill("#units", units)
        page.fill("#time_taken", "22:00")
        page.locator('button[type="submit"]').click()
        assert_saved(page)

    db_session.expire_all()
    rows = list(db_session.scalars(
        select(BasalLog).where(BasalLog.date == dt.date(2026, 7, 26))
    ))
    assert len(rows) == 1, "a repeat date created a second dose instead of correcting"
    assert rows[0].units == 30.0


def test_the_profile_form_records_a_new_version(
    page: Page, live_server: str, db_session: Session
) -> None:
    from data.tables import PatientProfile

    page.goto(live_server + "/operator/profile", wait_until="networkidle")
    page.fill("#effective_from", "2026-07-27")
    page.fill("#icr", "8.5")
    page.fill("#isf", "32")
    page.fill("#target_bg", "130")
    page.locator('button[type="submit"]').click()

    assert_saved(page)
    assert "/operator/profile" in page.url, f"navigated away to {page.url}"

    db_session.expire_all()
    row = db_session.scalars(
        select(PatientProfile).where(PatientProfile.effective_from == dt.date(2026, 7, 27))
    ).one()
    assert row.icr == 8.5
    assert row.isf == 32.0
    assert row.target_bg == 130


def test_the_profile_form_shows_the_flags_it_already_returns(
    page: Page, live_server: str, db_session: Session
) -> None:
    """★ DL-048: *"a validation result nobody can see is not a warning"* — and until now
    nobody could see them. The endpoint has returned `flags` since S-1010 and the page threw
    them away, which is the same failure as an unread idempotency key: declared and
    unconnected."""
    page.goto(live_server + "/operator/profile", wait_until="networkidle")
    page.fill("#effective_from", "2026-07-28")
    page.fill("#icr", "45")     # far outside the usual 7–10
    page.fill("#isf", "30")
    page.fill("#target_bg", "135")
    page.locator('button[type="submit"]').click()

    text = assert_saved(page)
    assert "icr" in text.lower() or "unusual" in text.lower() or "check" in text.lower(), (
        f"the out-of-range flag was swallowed; the page said only {text!r}"
    )
