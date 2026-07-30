"""S-1009 — the monthly refit, end to end from the database (SDET, written RED first).

This is the first code that assembles a feature vector **from `meal_event` rows**. Every
consumer before it either tested a pure function over a hand-built list or fabricated the
derived inputs in memory (`scripts/demo_end_to_end.py` does both). That is exactly how
DL-046 (`basal_log` unwritable) and DL-049 (`actual_state` never backfilled) survived as
long as they did, so these tests source everything through the database on purpose.

Four adversarial directions, in descending order of how reasonable each looks:

1. **The assembler running its own `select(MealEvent)`.** One line shorter than going
   through `get_training_set` — and `get_training_set` is where INV-7 is wired, so the
   shortcut routes around the invariant entirely.
2. **Dropping rows whose recency weight falls below a threshold.** Reads as an
   optimisation. Silently deletes the old lows this system exists to predict.
3. **A random train/test split.** The ecosystem default. Basal is constant within a day, so
   it leaks at the day level.
4. **The refit carrying `is_promoted` forward.** Feels like continuity; swaps the served
   model out from under an operator decision made about a different model.

RED: `data.training`, `models.recency`, `models.refit` and `backfill_actual_states` do not
exist; `python -m cli refit` is an unknown subcommand.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.basal import record_basal
from data.db import create_all, make_engine, session_factory
from data.predictions import backfill_actual_states, record_prediction
from data.tables import (
    BolusLog,
    BolusType,
    ExIntensity,
    LoggedBy,
    MealEvent,
    MealType,
    ModelArtifact,
    PredictionLog,
)
from data.training import assemble_training_data
from features.basal import effective_basal
from features.pipeline import FEATURE_NAMES
from models.recency import RECENCY_HALFLIFE_DAYS, recency_weights
from models.refit import TRAILING_WINDOW_DAYS, run_refit
from models.state import bg_to_state

_NOW = dt.datetime(2026, 7, 1, 12, 0)


class _FixedClock:
    """`record_basal` takes a `Clock` (an object with `.now()`), not a callable — the
    project has exactly one sanctioned wall-clock reader and this is how it is injected."""

    def now(self) -> dt.datetime:
        return _NOW


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'refit.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


def _meal(
    session: Session,
    *,
    when: dt.datetime,
    pre_bg: int = 140,
    post_bg: int | None = 150,
    carbs: float = 45.0,
    units: float = 5.0,
    confidence: int = 95,
    hypo_treatment: bool = False,
) -> MealEvent:
    """A meal that passes S-203 validity unless deliberately made otherwise."""
    meal = MealEvent(
        datetime=when,
        logged_at=when + dt.timedelta(minutes=30),
        logged_by=LoggedBy.patient,
        meal_type=MealType.lunch,
        pre_bg=pre_bg,
        pre_bg_time=when - dt.timedelta(minutes=5),
        post_bg=post_bg,
        # S-203's valid window is 105-135 min (core.validity). 120 sits mid-window;
        # the earlier 240 excluded every fixture meal as `outside_window`.
        post_bg_time=when + dt.timedelta(minutes=120) if post_bg is not None else None,
        elapsed_min=120 if post_bg is not None else None,
        meal_bolus_units=units,
        correction_bolus_units=0.0,
        bolus_offset_min=-10,
        carbs_g=carbs,
        protein_g=20.0,
        fat_g=15.0,
        fiber_g=5.0,
        macro_confidence=confidence,
        ex_intensity=ExIntensity.none,
        hypo_treatment=hypo_treatment,
    )
    session.add(meal)
    session.flush()
    return meal


def _bolus(session: Session, *, when: dt.datetime, units: float) -> None:
    session.add(
        BolusLog(
            datetime=when,
            logged_at=when,
            units=units,
            bolus_type=BolusType.meal,
            logged_by=LoggedBy.patient,
        )
    )
    session.flush()


def _basal_series(session: Session, *, start: dt.date, days: int, units: float) -> None:
    for i in range(days):
        record_basal(
            session,
            date=start + dt.timedelta(days=i),
            units=units,
            time_taken=dt.time(22, 0),
            logged_by=LoggedBy.patient,
            clock=_FixedClock(),
        )
    session.flush()


def _spread_meals(session: Session, *, n: int, end: dt.datetime) -> list[MealEvent]:
    """``n`` valid meals, one every 3 days working backwards, with varied outcomes so the
    ordinal fit has more than one state to learn."""
    meals = []
    for i in range(n):
        when = end - dt.timedelta(days=3 * i, hours=i % 5)
        post = (95, 120, 150, 200, 260)[i % 5]
        meals.append(
            _meal(session, when=when, pre_bg=110 + (i % 4) * 20, post_bg=post, carbs=30.0 + i)
        )
    session.flush()
    return meals


# --- ★ the assembler goes through the INV-7 choke point -----------------------


def test_a_rescued_meal_is_absent_from_training_and_still_a_hypo_event(
    session: Session,
) -> None:
    """A rescued meal is absent from training, asserted end to end from the database —
    which is what has been missing, since every other INV-7 test drives it from a
    hand-built list.

    ⚠ **This test does NOT catch the get_training_set bypass**, despite reading as though
    it should. It was labelled "the one that catches the shortcut" and the adversarial pass
    disproved that: planting a private `select(MealEvent)` that replicates
    `get_training_set`'s validity logic minus the INV-7 call leaves this test **green**,
    because a hypo-rescued meal fails S-203 validity anyway and is excluded either way.

    The test that actually catches the bypass is
    `test_the_assembler_raises_rather_than_silently_dropping_a_lost_rescue` — the ledger
    reconciliation, which has no other route to the same answer. Kept as a corroborating
    assertion, relabelled so nobody trusts it for a job it does not do.

    The non-emptiness assertion below is not decoration: under the plant the whole training
    set came back empty, and "the rescue is not in it" was true of nothing at all.
    """
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    rescued = _meal(
        session, when=_NOW - dt.timedelta(days=2), post_bg=60, hypo_treatment=True
    )
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)

    data = assemble_training_data(session, as_of=_NOW)
    assert data.meal_ids, "the training set is empty — this assertion would be vacuous"
    assert rescued.meal_id not in data.meal_ids, "a hypo-rescued meal reached training"


def test_the_assembler_raises_rather_than_silently_dropping_a_lost_rescue(
    session: Session,
) -> None:
    """★ THE ONE THAT ACTUALLY CATCHES THE BYPASS (established by the adversarial pass).

    INV-7's other half: a rescued meal must be *retained* as a hypo event. Deleting the row
    is the vector S-305 armed the ledger against, and the assembler must not be where it
    goes quiet.

    This is the only assertion in the suite that a private `select(MealEvent)` cannot
    satisfy. Validity filtering excludes rescued meals on its own, so "the rescue is absent
    from training" is reachable without INV-7 — but the **ledger reconciliation** is not.
    It has no route to the answer except through `get_training_set`, which is why it is the
    real guard and the other test is corroboration.
    """
    from core.safety import SafetyViolation
    from data.tables import HypoRescueLog

    _spread_meals(session, n=10, end=_NOW - dt.timedelta(days=1))
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    # A rescue on the ledger whose meal row is gone — the low that disappears silently.
    session.add(HypoRescueLog(meal_id=99999, grams=15.0, logged_at=_NOW))
    session.flush()

    with pytest.raises(SafetyViolation):
        assemble_training_data(session, as_of=_NOW)


# --- ★ the derived features come from the DB, not from thin air ---------------


def test_effective_basal_is_the_ewma_and_not_the_raw_daily_dose(session: Session) -> None:
    """★ *"Today's basal dose as a feature"* is a forbidden pattern: degludec runs ~42 h
    with a 3–4 day steady state, so today's dose is not today's effect.

    The step change is deliberate — on a flat 24 U series the EWMA and the raw dose are
    equal, and the forbidden shortcut would pass by coincidence. After a step they differ,
    so the assertion actually bites.
    """
    start = (_NOW - dt.timedelta(days=200)).date()
    # The step sits 2 days before the most recent meal ON PURPOSE. The EWMA half-life is
    # 25 h, so 50 days after a step it has fully converged to 30.0 and is indistinguishable
    # from the raw dose — the assertion below would pass against the forbidden shortcut.
    _basal_series(session, start=start, days=198, units=24.0)
    _basal_series(session, start=start + dt.timedelta(days=198), days=2, units=30.0)
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(hours=6))

    data = assemble_training_data(session, as_of=_NOW)
    col = data.feature_names.index("effective_basal")
    values = data.x[:, col]

    assert not np.allclose(values, 30.0), "the raw daily dose was used as the feature"
    assert not np.allclose(values, 24.0), "the raw daily dose was used as the feature"

    doses = [
        (dt.datetime.combine(start + dt.timedelta(days=i), dt.time(22, 0)),
         24.0 if i < 198 else 30.0)
        for i in range(200)
    ]
    smoothed = effective_basal(doses)
    assert min(smoothed) - 1e-6 <= float(values.max()) <= max(smoothed) + 1e-6
    # ★ Smoothed, not stepped: the most recent meal sits strictly between the two doses.
    assert 24.0 < float(values.max()) < 30.0


def test_iob_at_meal_is_derived_from_the_bolus_log(session: Session) -> None:
    """Manually-entered IOB is forbidden; it is derived from `bolus_log` or it is nothing."""
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    target = _meal(session, when=_NOW - dt.timedelta(days=2), post_bg=150)
    _bolus(session, when=target.datetime - dt.timedelta(minutes=60), units=6.0)

    data = assemble_training_data(session, as_of=_NOW)
    row = data.meal_ids.index(target.meal_id)
    iob = data.x[row, data.feature_names.index("iob_at_meal")]
    assert iob > 0.0, "IOB from an injection an hour earlier came through as zero"


def test_the_outcome_is_binned_and_pre_bg_is_not(session: Session) -> None:
    """The sanctioned direction: bin the **output**, never `pre_bg` as an input. Binning
    `pre_bg` would discard exactly the low-BG resolution needed to predict a low."""
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    target = _meal(session, when=_NOW - dt.timedelta(days=2), pre_bg=137, post_bg=205)

    data = assemble_training_data(session, as_of=_NOW)
    row = data.meal_ids.index(target.meal_id)
    assert data.y_state[row] == bg_to_state(205)
    assert data.x[row, data.feature_names.index("pre_bg")] == pytest.approx(137.0), (
        "pre_bg was binned as an input"
    )
    assert data.feature_names == FEATURE_NAMES


def test_a_meal_without_an_outcome_cannot_be_a_training_row(session: Session) -> None:
    """No `post_bg` means no label. It must be absent, not defaulted to anything."""
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    pending = _meal(session, when=_NOW - dt.timedelta(days=2), post_bg=None)

    data = assemble_training_data(session, as_of=_NOW)
    assert pending.meal_id not in data.meal_ids


# --- ★ the trailing window ----------------------------------------------------


def test_the_trailing_window_boundary_holds_on_both_sides(session: Session) -> None:
    """`07 §Retraining`: trailing 6 months. Asserted one day inside and one day outside —
    a one-sided test passes for an off-by-a-lot window."""
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    _basal_series(session, start=(_NOW - dt.timedelta(days=400)).date(), days=400, units=24.0)
    inside = _meal(session, when=_NOW - dt.timedelta(days=TRAILING_WINDOW_DAYS - 1))
    outside = _meal(session, when=_NOW - dt.timedelta(days=TRAILING_WINDOW_DAYS + 1))

    data = assemble_training_data(session, as_of=_NOW)
    assert inside.meal_id in data.meal_ids
    assert outside.meal_id not in data.meal_ids


# --- ★ recency weighting (DL-047) ---------------------------------------------


def test_the_half_life_is_ninety_days_and_pinned() -> None:
    """DL-047, operator-approved. Pinned exactly: a half-life is a clinical-ish constant and
    changing it silently changes how much her older data counts."""
    assert RECENCY_HALFLIFE_DAYS == 90


def test_a_meal_ninety_days_old_weighs_exactly_half_of_todays() -> None:
    weights = recency_weights(
        [_NOW, _NOW - dt.timedelta(days=RECENCY_HALFLIFE_DAYS)], as_of=_NOW
    )
    assert weights[0] == pytest.approx(1.0)
    assert weights[1] == pytest.approx(0.5)


def test_recency_weight_is_strictly_positive_at_the_oldest_edge() -> None:
    """★ THE ONE THAT CATCHES THE 'OPTIMISATION'.

    Dropping rows below a weight threshold reads as tidy engineering. It silently deletes
    the oldest lows — and a rescued low from five months ago is still a low. The weight
    decays; it must never reach zero, and nothing may floor it to zero.
    """
    weights = recency_weights(
        [_NOW - dt.timedelta(days=TRAILING_WINDOW_DAYS)], as_of=_NOW
    )
    assert weights[0] > 0.0, "an old meal was weighted out of existence"
    assert weights[0] == pytest.approx(0.5 ** (TRAILING_WINDOW_DAYS / 90), rel=1e-6)


def test_a_future_dated_meal_is_not_weighted_above_one() -> None:
    """Clock skew or a restored backup can date a row ahead of `as_of`. It must not become
    the most influential row in the fit."""
    weights = recency_weights([_NOW + dt.timedelta(days=10)], as_of=_NOW)
    assert weights[0] <= 1.0


def test_recency_multiplies_into_the_hypo_and_confidence_weights(session: Session) -> None:
    """★ It composes with the S-601 weights, it does not replace them. Asserted against the
    **product** — an implementation that returned recency alone, or dropped the hypo
    up-weight, passes any assertion that only checks one factor.
    """
    from models.ordinal import DEFAULT_HYPO_WEIGHT
    from models.refit import composite_weights

    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    _spread_meals(session, n=10, end=_NOW - dt.timedelta(days=1))
    # A low outcome (state 2) with reduced macro confidence, 90 days back.
    old_low = _meal(
        session, when=_NOW - dt.timedelta(days=90), post_bg=70, confidence=50
    )

    data = assemble_training_data(session, as_of=_NOW)
    weights = composite_weights(data, as_of=_NOW)
    row = data.meal_ids.index(old_low.meal_id)

    expected = 0.5 * DEFAULT_HYPO_WEIGHT * 0.5  # confidence × hypo × recency
    assert weights[row] == pytest.approx(expected, rel=1e-6)


def test_an_old_low_still_outweighs_a_recent_ordinary_meal(session: Session) -> None:
    """The clinical point of the whole weighting scheme, stated as an assertion: recency
    reduces a low's influence, it does not demote it below an ordinary meal."""
    from models.refit import composite_weights

    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    _spread_meals(session, n=10, end=_NOW - dt.timedelta(days=40))
    old_low = _meal(session, when=_NOW - dt.timedelta(days=150), post_bg=65)
    recent_ordinary = _meal(session, when=_NOW - dt.timedelta(days=1), post_bg=150)

    data = assemble_training_data(session, as_of=_NOW)
    weights = composite_weights(data, as_of=_NOW)
    assert (
        weights[data.meal_ids.index(old_low.meal_id)]
        > weights[data.meal_ids.index(recent_ordinary.meal_id)]
    )


# --- ★ the artifact -----------------------------------------------------------


def test_the_refit_writes_an_unpromoted_artifact_even_when_one_is_promoted(
    session: Session,
) -> None:
    """★ REQ-060: *"promotion never carries over."*

    The pre-existing promoted artifact is the point. On an empty table "is_promoted is
    False" passes vacuously; here an implementation that inherits promotion fails loudly.
    Promotion is a deliberate operator act about **one specific model** — a refit that
    carried it forward would swap the served model out from under that decision.
    """
    session.add(
        ModelArtifact(
            version="v-old", fit_date=_NOW - dt.timedelta(days=30), data_hash="x",
            n_rows=10, feature_list=[], metrics={}, is_promoted=True,
        )
    )
    session.flush()
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    _spread_meals(session, n=25, end=_NOW - dt.timedelta(days=1))

    artifact = run_refit(session, as_of=_NOW)
    assert artifact.is_promoted is False, "the refit inherited promotion"

    fresh = session.scalars(
        select(ModelArtifact).where(ModelArtifact.version == artifact.version)
    ).one()
    assert fresh.is_promoted is False


def test_a_refit_appends_and_never_overwrites(session: Session) -> None:
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    _spread_meals(session, n=25, end=_NOW - dt.timedelta(days=1))

    first = run_refit(session, as_of=_NOW)
    second = run_refit(session, as_of=_NOW + dt.timedelta(days=30))
    session.flush()

    assert first.version != second.version
    assert session.query(ModelArtifact).count() == 2


def test_the_artifact_records_what_it_was_fitted_on(session: Session) -> None:
    """`n_rows`, `feature_list` and the metrics are the manifest an operator reads months
    later to answer *"what was this fitted on?"*."""
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    meals = _spread_meals(session, n=25, end=_NOW - dt.timedelta(days=1))

    artifact = run_refit(session, as_of=_NOW)
    assert artifact.n_rows == len([m for m in meals if m.post_bg is not None])
    assert "hypo_recall" in artifact.metrics

    # ★ `feature_list` records what was ACTUALLY fitted, not what was offered — a subset of
    # FEATURE_NAMES, with the rest named in `dropped_constant_features`. The manifest exists
    # so an operator months later can answer "what did this model see?", and "it saw all 23"
    # would be false whenever a column carried no rank. Both halves are asserted, because a
    # subset alone is satisfiable by dropping everything silently.
    assert set(artifact.feature_list) <= set(FEATURE_NAMES)
    assert artifact.feature_list, "no features survived"
    dropped = artifact.metrics["dropped_constant_features"]
    assert set(artifact.feature_list) | set(dropped) == set(FEATURE_NAMES), (
        "a feature was neither fitted nor recorded as dropped — it vanished"
    )


def test_a_refit_with_too_little_data_refuses_rather_than_fitting_noise(
    session: Session,
) -> None:
    """Three meals cannot support a 23-feature ordinal fit. Refusing is the honest output;
    an artifact fitted on noise looks exactly like one fitted on evidence."""
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    _spread_meals(session, n=3, end=_NOW - dt.timedelta(days=1))

    with pytest.raises(ValueError):
        run_refit(session, as_of=_NOW)
    assert session.query(ModelArtifact).count() == 0


# --- ★ DL-049: the outcome half of every comparison ---------------------------


def test_backfill_fills_actual_state_from_the_meals_post_bg(session: Session) -> None:
    """★ DL-049. The column has existed since S-201, commented `# backfilled`, with nothing
    backfilling it — so there is no hypo recall, no Brier, no calibration, and **Gate 1 can
    never open.** The model would be fitted, correct, and permanently unreviewable."""
    meal = _meal(session, when=_NOW - dt.timedelta(days=2), post_bg=68)
    record_prediction(
        session, model_version="v1", gate_state="shadow", input_features={},
        predicted_distribution={"1": 0.1}, baseline_state=3, meal_id=meal.meal_id,
    )
    session.flush()

    filled = backfill_actual_states(session)
    assert filled == 1
    row = session.scalars(select(PredictionLog)).one()
    assert row.actual_state == bg_to_state(68) == 2


def test_a_prediction_whose_outcome_is_unknown_stays_null(session: Session) -> None:
    """★ "Not yet known" and "state 3" must never be the same value. Defaulting an unread
    outcome to the in-range state would quietly score every un-followed-up meal as a
    success — including the ones that went low."""
    meal = _meal(session, when=_NOW - dt.timedelta(days=1), post_bg=None)
    record_prediction(
        session, model_version="v1", gate_state="shadow", input_features={},
        predicted_distribution={"1": 0.1}, baseline_state=3, meal_id=meal.meal_id,
    )
    session.flush()

    assert backfill_actual_states(session) == 0
    assert session.scalars(select(PredictionLog)).one().actual_state is None


def test_the_backfill_is_idempotent(session: Session) -> None:
    meal = _meal(session, when=_NOW - dt.timedelta(days=2), post_bg=150)
    record_prediction(
        session, model_version="v1", gate_state="shadow", input_features={},
        predicted_distribution={"3": 0.9}, baseline_state=3, meal_id=meal.meal_id,
    )
    session.flush()

    assert backfill_actual_states(session) == 1
    assert backfill_actual_states(session) == 0


def test_a_prediction_with_no_meal_is_left_alone(session: Session) -> None:
    record_prediction(
        session, model_version="v1", gate_state="shadow", input_features={},
        predicted_distribution={"3": 0.9}, baseline_state=3, meal_id=None,
    )
    session.flush()
    assert backfill_actual_states(session) == 0


def test_hypo_recall_is_null_not_zero_when_the_window_contains_no_lows(
    session: Session,
) -> None:
    """★ ADVERSARIAL (SDET, added during GREEN).

    A recall of **0.0** reads as *"it missed every low"*. A window with **no lows in it** is a
    completely different, and far more important, statement: the model has never seen the
    event it exists to predict, and Gate 1's beats-baseline condition has nothing to compare.
    Collapsing the second into the first would put a number on the operator's screen that
    means the opposite of the truth.
    """
    _basal_series(session, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
    for i in range(25):
        _meal(
            session,
            when=_NOW - dt.timedelta(days=3 * i, hours=i % 5),
            pre_bg=110 + (i % 4) * 20,
            post_bg=(120, 150, 200, 260, 175)[i % 5],  # no state 1 or 2 anywhere
            carbs=30.0 + i,
        )
    session.flush()

    artifact = run_refit(session, as_of=_NOW)
    assert artifact.metrics["hypo_recall"] is None, "an undefined recall was reported as 0.0"
    assert artifact.metrics["n_hypo_observed"] == 0


def test_no_composite_weight_is_ever_zero(session: Session) -> None:
    """★ ADVERSARIAL (SDET, added after a plant SURVIVED the first pass).

    `test_recency_weight_is_strictly_positive_at_the_oldest_edge` tests `recency_weights` —
    the **pure function**. Production does not use the pure function; it uses
    `composite_weights`. Planting `np.where(combined < 0.35, 0.0, combined)` there — the
    "tidy up negligible weights" refactor, one line, reads as housekeeping — left the entire
    suite green.

    That is the failure CLAUDE.md names by hand: *"the obvious refactor silently deletes
    exactly the lows the system exists to predict."* A row weighted 0.0 is a row that was not
    in the fit, and the rows that reach zero first are the oldest — which, after the hypo
    up-weight, are disproportionately the rescued lows.

    So this asserts on the composition, over a set built to contain the worst case: an old,
    low-confidence, ordinary meal at the very edge of the window.
    """
    from models.refit import composite_weights

    _basal_series(session, start=(_NOW - dt.timedelta(days=400)).date(), days=400, units=24.0)
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    oldest = _meal(
        session,
        when=_NOW - dt.timedelta(days=TRAILING_WINDOW_DAYS - 1),
        post_bg=150,
        # The lowest confidence that still passes S-203 validity (MIN_MACRO_CONFIDENCE
        # is 50) — below it the meal is excluded before weighting ever sees it.
        confidence=50,
    )
    session.flush()

    data = assemble_training_data(session, as_of=_NOW)
    weights = composite_weights(data, as_of=_NOW)

    assert float(weights.min()) > 0.0, (
        "a training row was weighted to zero — that row was not in the fit at all"
    )
    assert weights[data.meal_ids.index(oldest.meal_id)] > 0.0


def test_the_oldest_rescued_low_keeps_a_positive_weight(session: Session) -> None:
    """★ Stated as the clinical claim it is: *a rescued low from five months ago is still a
    low.* Recency reduces how much it counts. It must never decide it never happened."""
    from models.refit import composite_weights

    _basal_series(session, start=(_NOW - dt.timedelta(days=400)).date(), days=400, units=24.0)
    _spread_meals(session, n=12, end=_NOW - dt.timedelta(days=1))
    old_low = _meal(
        session,
        when=_NOW - dt.timedelta(days=TRAILING_WINDOW_DAYS - 2),
        post_bg=58,
        confidence=50,
    )
    session.flush()

    data = assemble_training_data(session, as_of=_NOW)
    weights = composite_weights(data, as_of=_NOW)
    assert weights[data.meal_ids.index(old_low.meal_id)] > 0.0


# --- ★ the metric Gate 1 turns on --------------------------------------------


def test_a_model_that_predicts_no_lows_scores_zero_recall_not_one() -> None:
    """★ ADVERSARIAL (SDET). Caught by running the app against seeded data, where every
    refit reported `hypo_recall: 1.0` — the shape CLAUDE.md names: *"the model performs
    suspiciously well. Almost always leakage. Investigate."*

    It was leakage in the most literal form: the score being ranked was derived from the
    **truth** rather than from the prediction, so recall came back 1.0 no matter what the
    model did.

    Hypo recall is the metric Gate 1's beats-baseline condition turns on. A model that
    never predicts a low must score **0.0** — that is the whole point of measuring it.
    """
    from models.refit import score_predictions

    truth = np.array([3, 3, 2, 3, 1, 3, 4, 3, 2, 5], dtype=int)
    blind = np.full(truth.shape, 3, dtype=int)  # predicts "in range" every single time

    metrics = score_predictions(blind, truth)
    assert metrics["hypo_recall"] == 0.0, (
        "a model that never predicts a low scored above zero — the score is not coming "
        "from the prediction"
    )
    assert metrics["n_hypo_observed"] == 3


def test_a_model_that_finds_every_low_scores_one() -> None:
    from models.refit import score_predictions

    truth = np.array([3, 3, 2, 3, 1, 3, 4, 3, 2, 5], dtype=int)
    perfect = truth.copy()
    assert score_predictions(perfect, truth)["hypo_recall"] == 1.0


def test_recall_is_strictly_between_when_the_model_finds_some_lows() -> None:
    """★ The one that separates "computed from the prediction" from "hard-coded to a
    boundary". Both 0.0 and 1.0 are reachable by a broken implementation; a partial score
    is not."""
    from models.refit import score_predictions

    truth = np.array([3, 3, 2, 3, 1, 3, 4, 3, 2, 5], dtype=int)
    partial = np.array([3, 3, 2, 3, 3, 3, 4, 3, 3, 5], dtype=int)  # finds 1 of the 3 lows

    recall = score_predictions(partial, truth)["hypo_recall"]
    assert 0.0 < recall < 1.0, f"expected a partial recall, got {recall}"


def test_recall_is_none_when_there_are_no_lows_to_recall() -> None:
    from models.refit import score_predictions

    truth = np.array([3, 3, 4, 3, 5, 3, 4, 3, 3, 5], dtype=int)
    metrics = score_predictions(truth.copy(), truth)
    assert metrics["hypo_recall"] is None
    assert metrics["n_hypo_observed"] == 0
