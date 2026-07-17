"""S-803 [SAFETY] — the kill switch (SDET, written RED first).

When the model drifts below the baseline it was supposed to beat, it must stop speaking —
and STAY stopped. The dangerous failure is the quiet un-trip: a degraded model that got
switched off, produced one lucky good prediction, and silently turned itself back on. A
human, not a data point, decides when it is safe to trust again. See docs/stories/S-803.md.

RED: `prescribe.kill_switch` does not exist yet.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from data.tables import ModelArtifact
from prescribe.kill_switch import (
    ManualReArmRequired,
    evaluate_kill_switch,
    is_tripped,
    rearm,
    should_trip,
)

_VERSION = "v-test-1"


def _seed_model(session: Session) -> None:
    session.add(
        ModelArtifact(
            version=_VERSION,
            fit_date=dt.datetime(2026, 3, 1, 8, 0),
            data_hash="abc123",
            n_rows=180,
            feature_list=["pre_bg", "carbs_g"],
            metrics={"hypo_recall": 0.7},
        )
    )
    session.flush()


def test_should_trip_on_drift_below_baseline() -> None:
    assert should_trip(rolling_recall=0.40, baseline_recall=0.50) is True
    assert should_trip(rolling_recall=0.60, baseline_recall=0.50) is False
    # a tie does not trip — the model is not (yet) below baseline
    assert should_trip(rolling_recall=0.50, baseline_recall=0.50) is False


def test_drift_trips_and_persists(session: Session) -> None:
    _seed_model(session)
    assert is_tripped(session, _VERSION) is False
    tripped = evaluate_kill_switch(
        session, _VERSION, rolling_recall=0.40, baseline_recall=0.50
    )
    assert tripped is True
    assert is_tripped(session, _VERSION) is True  # read back from model_artifact


def test_a_subsequent_good_run_does_not_re_arm(session: Session) -> None:
    """★ Once tripped, a good evaluation must NOT silently clear it."""
    _seed_model(session)
    evaluate_kill_switch(session, _VERSION, rolling_recall=0.40, baseline_recall=0.50)
    assert is_tripped(session, _VERSION) is True
    # a subsequent GOOD run (recall beats baseline) — must remain suppressed
    still = evaluate_kill_switch(session, _VERSION, rolling_recall=0.80, baseline_recall=0.50)
    assert still is True
    assert is_tripped(session, _VERSION) is True


def test_re_arm_is_manual_only(session: Session) -> None:
    """★ Only an explicit operator action clears the switch."""
    _seed_model(session)
    evaluate_kill_switch(session, _VERSION, rolling_recall=0.40, baseline_recall=0.50)
    assert is_tripped(session, _VERSION) is True

    with pytest.raises(ManualReArmRequired):
        rearm(session, _VERSION, operator_confirmed=False)
    assert is_tripped(session, _VERSION) is True  # still suppressed after a refused re-arm

    rearm(session, _VERSION, operator_confirmed=True)
    assert is_tripped(session, _VERSION) is False  # manual action re-arms it


def test_unknown_model_version_raises(session: Session) -> None:
    with pytest.raises(ValueError):
        is_tripped(session, "no-such-version")


def test_evaluate_leaves_a_healthy_model_untripped(session: Session) -> None:
    _seed_model(session)
    tripped = evaluate_kill_switch(
        session, _VERSION, rolling_recall=0.80, baseline_recall=0.50
    )
    assert tripped is False
    assert is_tripped(session, _VERSION) is False
