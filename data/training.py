"""The DB → features assembler (S-1009, REQ-060).

**Nothing has ever assembled a feature vector from `meal_event` rows.** Every consumer to
date either tested a pure function over a hand-built list (S-402, S-404) or fabricated the
derived inputs in memory (`scripts/demo_end_to_end.py`). That gap is why `basal_log` went
three epics without a writer (DL-046) and why `prediction_log.actual_state` went five
without one (DL-049): *a feature nobody has sourced end-to-end is a feature nobody has
checked exists.*

This module is that bridge, and it is deliberately thin — it composes existing engines and
computes nothing new:

- **`get_training_set`**, never its own `select(MealEvent)`. That function is where INV-7 is
  wired: a rescued meal cannot leak into training, and every rescued meal must remain a hypo
  event. A private query here would be one line shorter and would route around the invariant
  entirely.
- **`iob_at_start_at`** for IOB — derived from `bolus_log`, never entered.
- **`effective_basal`** for the basal feature — the EWMA in force at the meal, never the raw
  daily dose. Degludec runs ~42 h with a 3–4 day steady state, so today's dose is not today's
  effect, and the raw figure as a feature is a forbidden pattern with an AST guard.
- **`bg_to_state(post_bg)`** for the label — binning the **outcome**, which is the sanctioned
  direction. `pre_bg` goes in continuous; binning it as an input is separately forbidden.
"""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.repositories import basal_doses, get_training_set, iob_at_start_at
from data.tables import BolusLog, MealEvent
from features.basal import effective_basal
from features.pipeline import FEATURE_NAMES, feature_vector, sample_weight
from models.state import bg_to_state

# `07 §Retraining`: "trailing 6 months". 183 days, not "6 × 30" and not a calendar-month
# walk — the window is a duration, and a duration that changes length with the month is a
# window nobody can reproduce.
TRAILING_WINDOW_DAYS: int = 183

# Below this a 23-feature ordinal fit is fitting noise, not signal.
MIN_TRAINING_ROWS: int = 20


@dataclass(frozen=True)
class TrainingData:
    """What the model layer consumes, assembled from the database."""

    feature_names: list[str]
    x: npt.NDArray[np.float64]
    y_state: npt.NDArray[np.int_]
    confidence_weights: npt.NDArray[np.float64]
    dates: list[dt.datetime]
    meal_ids: list[int]

    def __len__(self) -> int:
        return len(self.meal_ids)


def _basal_at(smoothed: list[tuple[dt.datetime, float]], at: dt.datetime) -> float:
    """The effective basal **in force at** ``at`` — the most recent smoothed value at or
    before the meal.

    Strictly at-or-before: a dose taken after the meal has not acted yet, and letting it
    into the feature would be leakage from the future dressed as a background level.
    Returns ``0.0`` when no dose precedes the meal, which is the truth rather than a guess.
    """
    times = [when for when, _ in smoothed]
    idx = bisect.bisect_right(times, at) - 1
    return smoothed[idx][1] if idx >= 0 else 0.0


def _minutes_since_last_bolus(session: Session, at: dt.datetime) -> float:
    """Minutes from the most recent injection **strictly before** ``at``.

    A bolus logged at the same instant is the meal's own bolus, not prior insulin — the same
    strictly-before rule ``boluses_before`` uses for IOB.
    """
    last = session.scalars(
        select(BolusLog.datetime)
        .where(BolusLog.datetime < at)
        .order_by(BolusLog.datetime.desc())
        .limit(1)
    ).first()
    if last is None:
        return 0.0
    return (at - last).total_seconds() / 60.0


def derive_meal_features(session: Session, meal: MealEvent) -> dict[str, float]:
    """The feature vector for **one** meal, derived from the database (S-1009, S-1015).

    ★ **The single derivation, used by both the training assembler and the live prediction
    path.** A parallel implementation for serving would drift from the one used for fitting,
    and the drift shows up as a model that scores well and predicts badly — the single most
    dangerous failure this system has.

    It is deliberately independent of whether the meal has an outcome yet: a meal being
    predicted has no ``post_bg``, and needs exactly the same inputs as one being trained on.
    Filtering by outcome belongs to the *training set*, not to feature derivation.
    """
    doses = basal_doses(session)
    smoothed = list(zip([when for when, _ in doses], effective_basal(doses), strict=True))
    return feature_vector(
        meal,
        iob_at_meal=iob_at_start_at(session, meal.datetime),
        effective_basal=_basal_at(smoothed, meal.datetime),
        minutes_since_last_bolus=_minutes_since_last_bolus(session, meal.datetime),
    )


def assemble_training_data(
    session: Session,
    *,
    as_of: dt.datetime,
    window_days: int = TRAILING_WINDOW_DAYS,
) -> TrainingData:
    """Assemble the trailing-window training matrix from the database.

    ``as_of`` is **injected** (ADR-8): the project has one sanctioned wall-clock reader, and
    a training set whose contents depend on when the refit happened to run is a training set
    nobody can reproduce.

    Meals without a ``post_bg`` are absent rather than defaulted — no outcome means no label,
    and inventing one would teach the model an outcome that was never observed.
    """
    cutoff = as_of - dt.timedelta(days=window_days)
    # ★ Through get_training_set: this is where INV-7 is wired. It raises if a rescued meal
    # leaked into training or a recorded rescue is missing from the hypo events.
    meals = [
        m
        for m in get_training_set(session)
        if m.post_bg is not None and cutoff <= m.datetime <= as_of
    ]

    rows = [
        [v[name] for name in FEATURE_NAMES]
        for v in (derive_meal_features(session, m) for m in meals)
    ]

    return TrainingData(
        feature_names=list(FEATURE_NAMES),
        x=np.array(rows, dtype=float).reshape(len(rows), len(FEATURE_NAMES)),
        # The OUTCOME is binned (sanctioned); pre_bg stays continuous in x (forbidden to bin).
        y_state=np.array(
            [bg_to_state(float(m.post_bg)) for m in meals if m.post_bg is not None], dtype=int
        ),
        confidence_weights=np.array([sample_weight(m) for m in meals], dtype=float),
        dates=[m.datetime for m in meals],
        meal_ids=[m.meal_id for m in meals],
    )
