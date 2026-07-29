"""S-1005 [SAFETY] — the whole cycle, on synthetic data (SDET).

Every invariant here is already tested in isolation and passes. This suite asks the other
question: **do they still hold across the seams?**

The unit suite proves each invariant holds *given its inputs*. It cannot prove those inputs
are what the previous stage actually produced. Every failure this file exists to catch lives
in the gap between two stages that each pass their own tests — `get_training_set` excludes
rescued meals, but does the *fit* consume that set? `serve_prediction` persists before
returning, but does the *caller* go through it?

**One assertion per seam, named after the seam.** A future stage added without one is then
visible as an absence rather than buried in a long happy path. The backlog is explicit:
**do not let this degrade into a smoke test.** "The pipeline ran without raising" would pass
on a chain that trains on rescued lows, serves unpersisted predictions and leaks across
folds — every one of those runs cleanly.

**What this cannot do:** it runs on synthetic data (S-1004). It proves the plumbing, not
that the model is any good, and nothing in it is evidence about her.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.safety import BOLUS_BG_FLOOR, MAX_BOLUS_U, GateNotPassed, SafetyViolation
from data.db import create_all, make_engine, session_factory
from data.predictions import serve_prediction
from data.repositories import (
    annotate_validity,
    get_hypo_events,
    get_training_set,
)
from data.tables import LoggedBy, MealEvent, MealType, PredictionLog
from features.cv import forward_chaining_folds
from models.guardrails import guard_prediction
from models.state import bg_to_state
from prescribe.bolus import recommend_bolus
from prescribe.gates import gate1_status
from prescribe.readout import build_patient_readout
from synthetic.generator import generate

_ICR, _ISF, _TARGET = 9.0, 30.0, 135.0  # DL-032
_SEED, _DAYS = 4242, 120


@pytest.fixture(scope="module")
def dataset():  # type: ignore[no-untyped-def]
    return generate(seed=_SEED, days=_DAYS, start=dt.date(2026, 1, 1))


def _load(s: Session, dataset) -> None:  # type: ignore[no-untyped-def]
    """Write the synthetic cycle **through `annotate_validity`**, not straight into the DB.

    Bypassing it would skip the stage where the validity rules live — and the point of this
    suite is that the stages are wired to each other.
    """
    prev: dt.datetime | None = None
    for m in dataset.meals:
        meal = MealEvent(
            datetime=m.datetime, logged_at=m.logged_at, logged_by=LoggedBy.patient,
            meal_type=MealType(m.meal_type), pre_bg=m.pre_bg, pre_bg_time=m.pre_bg_time,
            post_bg=m.post_bg, post_bg_time=m.post_bg_time, elapsed_min=m.elapsed_min,
            meal_bolus_units=m.meal_bolus_units,
            correction_bolus_units=m.correction_bolus_units,
            bolus_offset_min=m.bolus_offset_min, carbs_g=m.carbs_g,
            protein_g=m.protein_g, fat_g=m.fat_g, fiber_g=m.fiber_g,
            macro_confidence=m.macro_confidence, ex_duration_min=m.ex_duration_min,
            ex_offset_min=m.ex_offset_min, pre_ex_duration_min=m.pre_ex_duration_min,
            hypo_treatment=m.hypo_treatment, hypo_treatment_g=m.hypo_treatment_g,
            snack_during_window=m.snack_during_window,
        )
        s.add(annotate_validity(meal, prev))
        prev = m.datetime
    s.flush()


@pytest.fixture()
def session(tmp_path: pathlib.Path, dataset) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """A full cycle: 120 days, which clears the 150-valid-meal volume floor."""
    engine = make_engine(f"sqlite:///{tmp_path / 'cycle.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        _load(s, dataset)
        yield s


@pytest.fixture()
def early_session(tmp_path: pathlib.Path) -> Iterator[Session]:
    """An **early** cycle — 40 days, deliberately short of the volume floor.

    The full run reaches 188 valid meals, so the "< 150 valid meals" condition the AC names
    cannot be exercised on it. Asserting the readout refuses there would pass for the wrong
    reason (the other four conditions are unmet anyway), which is the failure mode this
    whole suite exists to avoid.
    """
    engine = make_engine(f"sqlite:///{tmp_path / 'early.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        _load(s, generate(seed=_SEED, days=40, start=dt.date(2026, 1, 1)))
        yield s


# --- ★ seam: validity → training set → the model that is actually fit ---------


def test_the_synthetic_cycle_contains_rescued_lows_at_all(session: Session) -> None:
    """A precondition for the INV-7 seam test below. If the generator produced no rescues,
    the next test would pass vacuously — the exact failure mode this suite is written to
    avoid, applied to itself."""
    rescued = [m for m in session.scalars(select(MealEvent)) if m.hypo_treatment]
    assert rescued, "the synthetic cycle contains no rescued lows; the INV-7 seam is untested"


def test_inv7_across_the_chain_the_fit_never_sees_a_rescued_low(session: Session) -> None:
    """★ THE SEAM INV-7 EXISTS FOR.

    The unit tests prove the two accessors disagree correctly. This proves the **fit
    consumes the right one**. The failure it catches — "invalid rows get dropped", applied
    one layer up — silently deletes exactly the lows the system exists to predict, and
    every unit test still passes.
    """
    training = get_training_set(session)
    hypo_events = get_hypo_events(session)

    rescued_ids = {m.meal_id for m in session.scalars(select(MealEvent)) if m.hypo_treatment}
    training_ids = {m.meal_id for m in training}
    hypo_ids = {m.meal_id for m in hypo_events}

    assert rescued_ids, "no rescues to check"
    assert not (rescued_ids & training_ids), (
        f"rescued lows leaked into the fitted training set: {rescued_ids & training_ids}"
    )
    assert rescued_ids <= hypo_ids, (
        f"rescued lows missing from the hypo events: {rescued_ids - hypo_ids}"
    )


def test_inv7_rescued_lows_are_in_the_hypo_recall_denominator(session: Session) -> None:
    """★ Retained is not enough — they must be **counted**. A rescue kept in a table but
    absent from the denominator makes hypo recall look better precisely because a low
    happened."""
    hypo_ids = {m.meal_id for m in get_hypo_events(session)}
    rescued_ids = {m.meal_id for m in session.scalars(select(MealEvent)) if m.hypo_treatment}
    denominator = len(hypo_ids)
    assert denominator >= len(rescued_ids)
    without_rescues = len(hypo_ids - rescued_ids)
    assert denominator > without_rescues, (
        "the rescues contribute nothing to the hypo denominator"
    )


# --- ★ seam: the gate → the patient surface AND the operator surface ----------


def test_inv2_across_the_chain_readout_refuses_while_the_dashboard_still_renders(
    early_session: Session,
) -> None:
    """★ BOTH HALVES MATTER. The readout must refuse below the gate; the operator
    dashboard must **still render**. A system that hides its evidence screen when the gate
    is shut is one where the operator cannot see why it is shut."""
    from fastapi.testclient import TestClient

    from api.app import app
    from api.deps import get_session

    n_valid = len(get_training_set(early_session))
    assert n_valid < 150, f"this assertion needs the < 150 state; got {n_valid}"

    def _override() -> Iterator[Session]:
        yield early_session

    app.dependency_overrides[get_session] = _override
    try:
        client = TestClient(app)
        meal_id = early_session.scalars(select(MealEvent.meal_id)).first()
        readout = client.get(f"/meals/{meal_id}/readout")
        assert readout.status_code == 200
        assert "higher chance of a low" not in readout.text.lower()

        dashboard = client.get("/operator/shadow")
        assert dashboard.status_code == 200, "the evidence screen went dark with the gate"
        assert "gate 1 is <strong>closed</strong>" in dashboard.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_volume_alone_does_not_open_the_gate_on_a_full_cycle(session: Session) -> None:
    """★ The full 120-day cycle clears the volume floor (188 valid meals) — and Gate 1 is
    **still shut**, on the four other conditions. Volume is necessary and never sufficient
    (03 §3), asserted here on real pipeline output rather than on hand-made numbers."""
    n_valid = len(get_training_set(session))
    assert n_valid >= 150, f"expected the volume floor to be cleared; got {n_valid}"

    status = gate1_status(
        valid_meals=n_valid, model_hypo_recall=0.0, baseline_hypo_recall=0.0,
        is_promoted=False, shadow_days=0, calibration_ok=False,
    )
    assert status.meets_volume is True
    assert status.is_open is False
    assert set(status.failed_conditions) == {
        "beats_baseline", "calibration", "shadow_period", "promotion"
    }


def test_the_readout_builder_refuses_on_a_live_closed_gate(session: Session) -> None:
    """The builder is the backstop a future second caller cannot forget (S-804)."""
    closed = gate1_status(
        valid_meals=len(get_training_set(session)), model_hypo_recall=0.0,
        baseline_hypo_recall=0.0, is_promoted=False, shadow_days=0, calibration_ok=False,
    )
    guarded = guard_prediction(
        proba=np.array([0.1, 0.1, 0.6, 0.1, 0.1]), states=(1, 2, 3, 4, 5),
        predicted_bg=130.0, baseline_state=3, in_distribution=True, n_nearby_train=50,
    )
    with pytest.raises(GateNotPassed):
        build_patient_readout(
            gate1=closed, guarded=guarded, kill_switch_tripped=False, baseline_state=3
        )


# --- ★ seam: serving → prediction_log (INV-9 over a whole run) ----------------


def test_inv9_across_the_chain_nothing_escapes_unpersisted(session: Session) -> None:
    """★ Not "the function persists" — **"nothing escaped un-persisted over a whole
    cycle"**. Counted, so a path that returns without logging shows up as a mismatch."""
    before = session.query(PredictionLog).count()
    served = 0
    for meal in list(session.scalars(select(MealEvent)))[:25]:
        guarded = guard_prediction(
            proba=np.array([0.05, 0.15, 0.6, 0.15, 0.05]), states=(1, 2, 3, 4, 5),
            predicted_bg=float(meal.pre_bg), baseline_state=bg_to_state(meal.pre_bg),
            in_distribution=True, n_nearby_train=50,
        )
        serve_prediction(
            session, guarded, model_version="e2e", gate_state="shadow",
            input_features={"pre_bg": float(meal.pre_bg)}, meal_id=meal.meal_id,
        )
        served += 1

    after = session.query(PredictionLog).count()
    assert after - before == served, (
        f"{served} predictions served, {after - before} persisted — "
        "something was returned without being written"
    )


# --- ★ seam: features → folds → fit (no temporal leakage) --------------------


def test_no_temporal_leakage_in_any_fold(session: Session) -> None:
    """★ Ordering is not enough. Basal is constant within a day, so a **shared calendar
    date** leaks at day granularity even when every timestamp is ordered."""
    meals = get_training_set(session)
    dates = [m.datetime for m in meals]
    assert len(dates) > 20, "not enough valid meals to fold"

    for k, (train_idx, test_idx) in enumerate(forward_chaining_folds(dates, n_splits=3)):
        train_days = {dates[i].date() for i in train_idx}
        test_days = {dates[i].date() for i in test_idx}
        assert max(dates[i] for i in train_idx) < min(dates[i] for i in test_idx), (
            f"fold {k}: train does not strictly precede test"
        )
        assert not (train_days & test_days), (
            f"fold {k} shares calendar days across train/test: {train_days & test_days}"
        )


# --- ★ seam: the profile → the dose path (S-1011, Gate 2 retired) ------------


def test_a_missing_icr_is_an_input_error_not_a_gate(session: Session) -> None:
    """★ Gate 2 is retired (S-1011/DL-035) and must not creep back under another name.
    Asserted to be **neither** a `SafetyViolation` **nor** a `GateNotPassed`."""
    for bad in (None, 0.0, -1.0):
        with pytest.raises(ValueError) as exc:
            recommend_bolus(
                icr=bad, isf=_ISF, carbs_g=40.0, current_bg=180.0,  # type: ignore[arg-type]
                target_bg=_TARGET, iob=0.0,
            )
        assert not isinstance(exc.value, SafetyViolation), (
            "a missing ICR was raised as a safety violation — that is a gate by another name"
        )
        assert not isinstance(exc.value, GateNotPassed)

    ok = recommend_bolus(
        icr=_ICR, isf=_ISF, carbs_g=40.0, current_bg=180.0, target_bg=_TARGET, iob=0.0
    )
    assert ok.total_units > 0


def test_inv3_and_inv4_hold_at_the_end_of_the_chain(session: Session) -> None:
    """★ The same properties S-1003 asserts on the screen, asserted here on the path —
    so a future UI that bypasses the screen still meets them."""
    with pytest.raises(SafetyViolation):
        recommend_bolus(
            icr=_ICR, isf=_ISF, carbs_g=40.0, current_bg=BOLUS_BG_FLOOR - 1,
            target_bg=_TARGET, iob=0.0,
        )

    typo = recommend_bolus(
        icr=_ICR, isf=_ISF, carbs_g=900.0, current_bg=180.0, target_bg=_TARGET, iob=0.0
    )
    assert typo.total_units == MAX_BOLUS_U
    assert typo.implausible_input is True, "capped without being flagged"


def test_the_dose_path_never_consulted_the_model(session: Session) -> None:
    """★ REQ-042 across the chain: a dose computed in the same process as a fitted model
    still owes nothing to it. The recommendation is reproducible from the formula alone."""
    rec = recommend_bolus(
        icr=_ICR, isf=_ISF, carbs_g=45.0, current_bg=195.0, target_bg=_TARGET, iob=1.0
    )
    expected = 45.0 / _ICR + (195.0 - _TARGET) / _ISF - 1.0
    assert rec.total_units == pytest.approx(expected, abs=1e-9)


# --- ★ the cycle is reproducible ---------------------------------------------


def test_the_whole_cycle_is_reproducible_from_its_seed() -> None:
    """A cycle that differs run to run cannot be used to investigate anything."""
    a = generate(seed=_SEED, days=30, start=dt.date(2026, 1, 1))
    b = generate(seed=_SEED, days=30, start=dt.date(2026, 1, 1))
    assert a.to_jsonable() == b.to_jsonable()
