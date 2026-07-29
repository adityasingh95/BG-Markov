"""S-1013 — recording the daily Tresiba (SDET, written RED first).

`basal_log` has been a table since S-201 and `effective_basal` has been computed from it
since S-402. **Nothing could write to it** (DL-046), so the model could not be fitted on
real data at all — a blocker found while planning the refit, not by any test.

Two adversarial directions, both things a reasonable person would do:

1. **`datetime.now()` for `time_taken`**, because she is *usually* logging right after
   taking it. *Usually* is what makes it dangerous: the EWMA's 25-hour half-life is a
   function of the time axis, so a wrong time silently distorts every later value.
2. **Using `units` directly as a model feature** — one line, reads sensibly, and wrong for
   an insulin with ~42 h action and a 3–4 day steady state. Today's dose is not today's
   effect.

RED: `record_basal` does not exist; `POST /api/basal` 404s.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.basal import record_basal
from data.db import create_all, make_engine, session_factory
from data.repositories import basal_doses
from data.tables import AuditLog, BasalLog, LoggedBy
from features.basal import effective_basal

_DAY = dt.date(2026, 1, 1)
_TAKEN = dt.time(22, 30)  # she takes it at night


class _FixedClock:
    """A clock that is unmistakably NOT the reported time."""

    def now(self) -> dt.datetime:
        return dt.datetime(2026, 3, 15, 9, 5)


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'basal.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- ★ ADR-8: reported time, never the clock ---------------------------------


def test_time_taken_is_reported_and_logged_at_is_the_clock(session: Session) -> None:
    """★ THE ADR-8 SEAM FOR THIS TABLE.

    She takes it at 22:30 and logs it the next morning. If `time_taken` were defaulted to
    the system clock, the EWMA's time axis — the whole basis of the 25-hour half-life —
    would be silently wrong, with no error and no way to detect it afterwards.
    """
    record_basal(session, date=_DAY, units=24.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()

    row = session.scalars(select(BasalLog)).one()
    assert row.time_taken == _TAKEN, "the reported time was overwritten"
    assert row.logged_at == _FixedClock().now()
    assert row.logged_at.time() != row.time_taken


def test_the_reported_time_survives_a_correction(session: Session) -> None:
    """A correction may change the time — but only to another *reported* one."""
    record_basal(session, date=_DAY, units=24.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()
    record_basal(
        session, date=_DAY, units=24.0, time_taken=dt.time(23, 15), clock=_FixedClock()
    )
    session.flush()
    assert session.scalars(select(BasalLog)).one().time_taken == dt.time(23, 15)


# --- ★ one row per date; a repeat is a correction, and it is audited ---------


def test_re_recording_a_date_corrects_rather_than_duplicating(session: Session) -> None:
    """★ Two rows for one day would DOUBLE-COUNT the dose in the smoothing, and the
    resulting `effective_basal` would look like a titration that never happened."""
    record_basal(session, date=_DAY, units=24.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()
    record_basal(session, date=_DAY, units=26.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()

    rows = list(session.scalars(select(BasalLog)))
    assert len(rows) == 1, f"a correction created a duplicate row: {len(rows)} rows"
    assert rows[0].units == 26.0


def test_a_correction_is_audited_old_to_new(session: Session) -> None:
    """★ 04 §10 — every edit to a clinical record is audited. A basal dose silently
    changed is a change to the input of every later `effective_basal`."""
    record_basal(session, date=_DAY, units=24.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()
    record_basal(session, date=_DAY, units=26.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()

    audits = list(session.scalars(select(AuditLog).where(AuditLog.table_name == "basal_log")))
    assert audits, "the correction was not audited"
    assert audits[-1].field == "units"
    assert audits[-1].old_value == "24.0" and audits[-1].new_value == "26.0"


def test_a_first_entry_is_not_audited_as_a_change(session: Session) -> None:
    """Recording a dose for the first time is not an edit; auditing it as one would bury
    the real corrections in noise."""
    record_basal(session, date=_DAY, units=24.0, time_taken=_TAKEN, clock=_FixedClock())
    session.flush()
    assert not list(session.scalars(select(AuditLog).where(AuditLog.table_name == "basal_log")))


@pytest.mark.parametrize("units", [0.0, -4.0])
def test_a_non_positive_dose_is_refused(session: Session, units: float) -> None:
    with pytest.raises(ValueError):
        record_basal(
            session, date=_DAY, units=units, time_taken=_TAKEN, clock=_FixedClock()
        )


# --- ★ the bridge this story exists to build ---------------------------------


def test_basal_doses_feeds_the_s402_ewma(session: Session) -> None:
    """★ THE POINT OF THE STORY. The EWMA has been correct and unreachable since S-402;
    this asserts the DB now reaches it, and that the timestamp is built from the
    **reported** date + time."""
    for i, units in enumerate([24.0, 24.0, 24.0]):
        record_basal(
            session, date=_DAY + dt.timedelta(days=i), units=units,
            time_taken=_TAKEN, clock=_FixedClock(),
        )
    session.flush()

    doses = basal_doses(session)
    assert [u for _, u in doses] == [24.0, 24.0, 24.0]
    assert [when.date() for when, _ in doses] == [_DAY + dt.timedelta(days=i) for i in range(3)]
    assert all(when.time() == _TAKEN for when, _ in doses), (
        "the timestamp must come from the REPORTED time, not midnight or the clock"
    )
    assert effective_basal(doses) == pytest.approx([24.0, 24.0, 24.0])


def test_a_step_change_is_smoothed_not_stepped(session: Session) -> None:
    """★ 24 U → 30 U. The next day is strictly between the two, and after five days it is
    near 30. This is the whole reason the feature is an EWMA and not the daily figure:
    Tresiba has ~42 h action and a 3–4 day steady state."""
    doses_in = [24.0] * 5 + [30.0] * 6
    for i, units in enumerate(doses_in):
        record_basal(
            session, date=_DAY + dt.timedelta(days=i), units=units,
            time_taken=_TAKEN, clock=_FixedClock(),
        )
    session.flush()

    smoothed = effective_basal(basal_doses(session))
    day_after_change = smoothed[5]
    assert 24.0 < day_after_change < 30.0, (
        f"the step was not smoothed: {day_after_change}"
    )
    assert abs(smoothed[-1] - 30.0) < 0.5, f"did not approach the new dose: {smoothed[-1]}"


def test_basal_doses_is_ordered_by_reported_date(session: Session) -> None:
    """Insertion order is not chronology — a backfilled day must not reorder the series."""
    for i in (2, 0, 1):
        record_basal(
            session, date=_DAY + dt.timedelta(days=i), units=20.0 + i,
            time_taken=_TAKEN, clock=_FixedClock(),
        )
    session.flush()
    doses = basal_doses(session)
    assert [u for _, u in doses] == [20.0, 21.0, 22.0]


def test_no_doses_is_an_empty_series_not_an_error(session: Session) -> None:
    """Day one."""
    assert basal_doses(session) == []


# --- the form ----------------------------------------------------------------


def test_the_form_records_a_dose(client: TestClient, session: Session) -> None:
    r = client.post(
        "/api/basal",
        json={"date": "2026-01-01", "units": 24.0, "time_taken": "22:30:00",
              "logged_by": LoggedBy.patient.value},
    )
    assert r.status_code in (200, 201), r.text
    assert session.scalars(select(BasalLog)).one().units == 24.0


def test_the_form_refuses_a_non_positive_dose(client: TestClient) -> None:
    r = client.post(
        "/api/basal",
        json={"date": "2026-01-01", "units": 0, "time_taken": "22:30:00",
              "logged_by": LoggedBy.patient.value},
    )
    assert r.status_code == 422, r.text


def test_the_form_requires_a_reported_time(client: TestClient) -> None:
    """★ ADR-8 on the wire: the client must say when she took it. A server-side default
    would be `datetime.now()` wearing a different hat."""
    r = client.post(
        "/api/basal",
        json={"date": "2026-01-01", "units": 24.0, "logged_by": LoggedBy.patient.value},
    )
    assert r.status_code == 422, "time_taken was defaulted rather than required"


def test_the_basal_page_renders_with_a_numeric_keypad(client: TestClient) -> None:
    body = client.get("/basal").text.lower()
    assert "basal" in body or "tresiba" in body
    assert 'inputmode="numeric"' in body
