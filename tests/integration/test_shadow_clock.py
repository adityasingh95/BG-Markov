"""S-1007 [SAFETY] — the 90-day shadow clock (SDET, written RED first).

REQ-048 (*"shadow mode ≥ 90 days before patient-visible output"*) has existed since the
PRD and was enforced nowhere. These tests give it its first coverage.

The clock is **derived from `prediction_log.created_at`, never stored**. A stored
`shadow_complete` boolean would be written once — by whoever ran the migration or the
backfill — and would then be true forever regardless of what the data said. A count
re-derived on every call cannot drift from reality (the same principle as ADR-7's
"gates are evaluated live, never cached").

`now` is **injected**, for two reasons: the project has exactly one sanctioned wall-clock
reader (`core/clock.py`, ADR-8), and an injected `now` makes "day 89 vs day 90" testable
without waiting a quarter.

RED: `data.repositories.shadow_days` does not exist.
"""

from __future__ import annotations

import datetime as dt
import inspect
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory
from data.repositories import shadow_days
from data.tables import PredictionLog

_T0 = dt.datetime(2026, 1, 1, 8, 0)


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'shadow.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


def _log(session: Session, created_at: dt.datetime) -> PredictionLog:
    row = PredictionLog(
        created_at=created_at,
        model_version="v-test",
        gate_state="shadow",
        input_features={"pre_bg": 120.0},
        predicted_distribution={"1": 0.05, "2": 0.05, "3": 0.8, "4": 0.05, "5": 0.05},
        baseline_state=3,
    )
    session.add(row)
    session.flush()
    return row


# --- fails closed ------------------------------------------------------------


def test_no_predictions_is_zero_days(session: Session) -> None:
    """★ Day one — nothing has been predicted, so nothing has been shadowed. An empty
    table must read as *no elapsed time*, never as "no constraint"."""
    assert shadow_days(session, now=_T0) == 0


def test_a_single_prediction_today_is_zero_days(session: Session) -> None:
    _log(session, _T0)
    assert shadow_days(session, now=_T0) == 0


# --- measured from the EARLIEST prediction -----------------------------------


def test_counted_from_the_earliest_prediction_not_the_latest(session: Session) -> None:
    """The shadow period starts when shadow logging started. Using the latest row would
    reset the clock to ~0 on every prediction and the gate could never open; using the
    row *count* would let 200 predictions in one week read as 200 days."""
    _log(session, _T0)
    _log(session, _T0 + dt.timedelta(days=95))
    _log(session, _T0 + dt.timedelta(days=99))
    assert shadow_days(session, now=_T0 + dt.timedelta(days=100)) == 100


def test_rows_inserted_out_of_order_still_use_the_earliest(session: Session) -> None:
    """Insertion order is not chronology — a backfilled or replayed row must not decide
    the answer."""
    _log(session, _T0 + dt.timedelta(days=40))
    _log(session, _T0)
    _log(session, _T0 + dt.timedelta(days=20))
    assert shadow_days(session, now=_T0 + dt.timedelta(days=90)) == 90


def test_the_89_90_boundary_is_exact(session: Session) -> None:
    """★ The boundary this story exists for. A partial day does not round up: 89 days
    and 23 hours is still day 89."""
    _log(session, _T0)
    assert shadow_days(session, now=_T0 + dt.timedelta(days=89)) == 89
    assert shadow_days(session, now=_T0 + dt.timedelta(days=89, hours=23)) == 89
    assert shadow_days(session, now=_T0 + dt.timedelta(days=90)) == 90


# --- clamped at zero ---------------------------------------------------------


def test_a_clock_that_steps_backwards_reads_zero_never_negative(session: Session) -> None:
    """★ Clock skew, a timezone bungle, a restored backup. Any of these can put `now`
    behind the earliest logged prediction. The answer is 0 — *not yet* — and never a
    negative number that some future `>=` comparison might mishandle."""
    _log(session, _T0)
    assert shadow_days(session, now=_T0 - dt.timedelta(days=30)) == 0
    assert shadow_days(session, now=_T0 - dt.timedelta(days=1)) == 0


def test_a_future_dated_row_does_not_manufacture_elapsed_time(session: Session) -> None:
    """A row written with a timestamp in the future must not create shadow days out of
    nothing — it is the *earliest* row that anchors the clock, and the result is clamped."""
    _log(session, _T0 + dt.timedelta(days=365))
    assert shadow_days(session, now=_T0) == 0


# --- derived, never stored ---------------------------------------------------


def test_not_memoised_the_answer_grows_as_now_advances(session: Session) -> None:
    """★ Proves it is re-derived per call rather than cached or stored. If a future
    refactor introduces a `shadow_complete` flag or an `lru_cache`, this test is what
    notices — a stored answer would return the same number for every `now`."""
    _log(session, _T0)
    assert shadow_days(session, now=_T0 + dt.timedelta(days=10)) == 10
    assert shadow_days(session, now=_T0 + dt.timedelta(days=89)) == 89
    assert shadow_days(session, now=_T0 + dt.timedelta(days=90)) == 90
    # and back down again, same session — no monotonic memo of a high-water mark
    assert shadow_days(session, now=_T0 + dt.timedelta(days=10)) == 10


def test_a_new_earlier_prediction_lengthens_the_clock(session: Session) -> None:
    """Live data, every call (ADR-7): inserting an earlier row within the same session
    changes the answer immediately."""
    _log(session, _T0 + dt.timedelta(days=50))
    assert shadow_days(session, now=_T0 + dt.timedelta(days=60)) == 10
    _log(session, _T0)
    assert shadow_days(session, now=_T0 + dt.timedelta(days=60)) == 60


def test_now_is_injected_not_read_from_the_wall_clock() -> None:
    """★ `now` must be a required keyword argument. If `shadow_days` read the wall clock
    itself, the 89/90 boundary would be untestable without waiting a quarter, and this
    codebase would have a second clock reader beside `core/clock.py` (ADR-8)."""
    sig = inspect.signature(shadow_days)
    param = sig.parameters["now"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty, "`now` must not default to the wall clock"


def test_no_stored_shadow_flag_exists_on_any_table() -> None:
    """★ The adversarial case. A boolean `shadow_complete` / `shadow_passed` column would
    be set once and then lie forever, and nothing in a green build would reveal it. The
    shadow period is a *derived count* or it is not a safeguard."""
    from data.tables import Base

    offenders = [
        f"{table.name}.{col.name}"
        for table in Base.metadata.sorted_tables
        for col in table.columns
        if "shadow" in col.name.lower()
    ]
    assert not offenders, f"shadow state must be derived, not stored: {offenders}"
