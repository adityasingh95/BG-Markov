"""The monthly refit (S-1009, REQ-060, `07 §Retraining`).

*"Monthly refit, trailing 6 months, older data down-weighted. Promotion is manual, on hypo
recall."* This orchestrates the pieces that already exist — it fits nothing new — and writes
a **new, unpromoted** artifact.

★ **The artifact is always unpromoted.** REQ-060: *"promotion never carries over."* Promotion
is a deliberate, audited operator act about **one specific model**; a refit that inherited it
would swap the model she is being shown out from under a decision that was made about a
different one. There is no parameter to override this — the flag is not an argument.

Three forbidden patterns converge here, and each would look like ordinary engineering:
a **random train/test split** (the ecosystem default; basal is constant within a day, so it
leaks at the day level), the **raw daily basal dose** as a feature (one line, wrong for a
42-hour insulin), and **dropping low-weight old rows** (reads as an optimisation, deletes old
lows). The first is avoided by using `temporal_cv`; the second lives in `data.training`; the
third is what `composite_weights` is written to prevent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

import numpy as np
import numpy.typing as npt
from sqlalchemy.orm import Session

from data.tables import ModelArtifact
from data.training import MIN_TRAINING_ROWS, TRAILING_WINDOW_DAYS, TrainingData
from data.training import assemble_training_data as assemble_training_data
from models.metrics import hypo_recall_at_far, off_by_one_rate, severe_state_error_rate
from models.ordinal import DEFAULT_HYPO_WEIGHT, fit_ordinal, hypo_confidence_weights
from models.recency import recency_weights
from models.validation import temporal_cv

__all__ = [
    "MIN_TRAINING_ROWS",
    "fittable_columns",
    "TRAILING_WINDOW_DAYS",
    "composite_weights",
    "run_refit",
]

_CV_SPLITS = 3

# Below this many varying columns there is not enough left to call a model.
_MIN_FITTABLE_FEATURES = 2


def fittable_columns(x: npt.NDArray[np.float64]) -> list[int]:
    """The column indices that carry information **beyond an intercept** (S-1009).

    `statsmodels`' `OrderedModel` refuses a design matrix whose column span contains a
    constant — *"There should not be a constant in the model"* — because the model supplies
    its own thresholds. Two ways a real six-month window trips that, neither exotic:

    1. **A constant column.** If she does no intense exercise in the window, `ex_intense`,
       `ex_intense_x_duration` and `pre_ex_intense` are zero throughout.
    2. **A constant *combination*.** `net_carbs_g` is `carbs_g - fiber_g`; across any stretch
       where fibre does not move, those two columns differ by a fixed amount and their span
       contains a constant even though neither column is constant.

    A plain "is this column constant?" check catches only the first. This keeps a column iff
    it raises the rank of ``[1 | kept-so-far]`` — i.e. iff it explains something the
    intercept and the already-kept columns do not. Both cases fall out of the one rule.

    Left unhandled, the monthly refit dies with a statsmodels message that says nothing about
    her data, on the day it is first run against a real six months.

    Dropping is not information loss: **a column that adds no rank cannot explain anything.**
    It is not silent either — the names go on the artifact, because *"this model never saw an
    intense-exercise meal"* is exactly what an operator needs before trusting it about one.
    """
    n_rows = x.shape[0]
    basis = np.ones((n_rows, 1), dtype=float)
    rank = 1
    keep: list[int] = []
    for i in range(x.shape[1]):
        trial = np.hstack([basis, x[:, [i]]])
        trial_rank = int(np.linalg.matrix_rank(trial))
        if trial_rank > rank:
            keep.append(i)
            basis, rank = trial, trial_rank
    return keep


def composite_weights(
    data: TrainingData,
    *,
    as_of: dt.datetime,
    hypo_weight: float = DEFAULT_HYPO_WEIGHT,
) -> npt.NDArray[np.float64]:
    """``macro_confidence × hypo up-weight × recency`` — all three, multiplied.

    Recency **multiplies into** the S-601 weights; it does not replace them. The composition
    is the point: an implementation that returned recency alone, or that dropped the hypo
    up-weight while adding decay, would still look like "weights that decay with age".

    ★ **Nothing is floored to zero and no row is dropped.** An old rescued low is
    down-weighted and still present, with its hypo up-weight intact — *a rescued low from
    five months ago is still a low*. Recency changes how much it counts, not whether it
    happened.
    """
    base = hypo_confidence_weights(
        data.y_state, data.confidence_weights, hypo_weight=hypo_weight
    )
    return np.asarray(base * recency_weights(data.dates, as_of=as_of), dtype=float)


def _data_hash(data: TrainingData) -> str:
    """A fingerprint of what was fitted — the manifest field that answers *"is this the same
    training set?"* months later, when the meals themselves have moved on."""
    payload = json.dumps(
        {
            "meal_ids": sorted(data.meal_ids),
            "features": data.feature_names,
            "y": data.y_state.tolist(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _score(
    x: npt.NDArray[np.float64],
    data: TrainingData,
    weights: npt.NDArray[np.float64],
) -> dict[str, Any]:
    """Out-of-sample metrics via forward-chaining temporal CV.

    ★ **Never a random split.** Basal is constant within a day, so a random split puts rows
    from the same day on both sides and leaks at the day level — the model then looks better
    than it is, which is the single most dangerous way for this system to fail.

    Plain accuracy is absent, and deliberately: it is meaningless on an imbalanced 5-class
    problem and it is a forbidden metric to headline.
    """

    def fit_predict(
        x_train: npt.NDArray[np.float64],
        y_train: npt.NDArray[np.int_],
        x_test: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        # ★ Re-checked PER FOLD, not once globally. A column can carry rank across the
        # whole window and still be redundant inside an early expanding-window fold — she
        # may not have exercised at all in the first two months. Filtering only globally
        # would leave that fold rank-deficient and statsmodels would raise mid-refit.
        keep = fittable_columns(x_train)
        idx = np.arange(len(y_train))
        fit = fit_ordinal(
            x_train[:, keep], y_train, confidence_weights=weights[idx]
        )
        proba = fit.predict_proba(x_test[:, keep])
        states = np.asarray(fit.states, dtype=int)
        return np.asarray(states[np.argmax(proba, axis=1)], dtype=float)

    result = temporal_cv(x, data.y_state, data.dates, fit_predict, n_splits=_CV_SPLITS)
    pred = np.asarray(result.oos_predictions(), dtype=int)
    truth = result.oos_truth()
    if pred.size == 0:
        return {"hypo_recall": None, "n_scored": 0, "n_hypo_observed": 0}

    # A hard predicted state is a degenerate "score": 1.0 for a predicted hypo, else 0.0.
    is_hypo = np.isin(truth, (1, 2))
    n_hypo = int(is_hypo.sum())

    # ★ Hypo recall is UNDEFINED when the window contains no lows — or no non-lows. Recorded
    # as null, never as 0.0: a recall of zero reads as "it missed every low", and a window
    # with no lows in it is a completely different, and far more important, statement. It
    # means the model has never seen the event it exists to predict, and Gate 1's
    # beats-baseline condition has nothing to compare. Failing closed here keeps that
    # visible instead of laundering it into a number.
    recall: float | None = None
    if 0 < n_hypo < len(truth):
        recall = float(hypo_recall_at_far(is_hypo.astype(float), is_hypo).recall)

    return {
        "hypo_recall": recall,
        "off_by_one": float(off_by_one_rate(pred, truth)),
        "severe_error": float(severe_state_error_rate(pred, truth)),
        "n_scored": int(pred.size),
        "n_hypo_observed": n_hypo,
    }


def run_refit(
    session: Session,
    *,
    as_of: dt.datetime,
    window_days: int = TRAILING_WINDOW_DAYS,
) -> ModelArtifact:
    """Refit over the trailing window and write a **new, unpromoted** artifact.

    ``as_of`` is injected (ADR-8) so the window and the recency weights are reproducible.

    **Refuses** a training set below ``MIN_TRAINING_ROWS``. An artifact fitted on eight meals
    looks exactly like one fitted on eight hundred — same row, same manifest, same dashboard —
    and refusing is the honest output. This raises `ValueError`, not `SafetyViolation`: too
    little data is a state of the world, not a breached invariant.
    """
    data = assemble_training_data(session, as_of=as_of, window_days=window_days)
    if len(data) < MIN_TRAINING_ROWS:
        raise ValueError(
            f"refit needs at least {MIN_TRAINING_ROWS} valid meals in the trailing "
            f"{window_days} days; found {len(data)}"
        )

    keep = fittable_columns(data.x)
    dropped = [n for i, n in enumerate(data.feature_names) if i not in set(keep)]
    if len(keep) < _MIN_FITTABLE_FEATURES:
        raise ValueError(
            f"refit needs at least {_MIN_FITTABLE_FEATURES} features that vary across the "
            f"training set; {len(keep)} do"
        )
    x = data.x[:, keep]
    fitted_features = [data.feature_names[i] for i in keep]

    weights = composite_weights(data, as_of=as_of)
    # Fit on the full window so the artifact reflects everything; score out-of-sample.
    fit_ordinal(x, data.y_state, confidence_weights=weights)
    metrics = _score(x, data, weights)

    artifact = ModelArtifact(
        version=f"refit-{as_of:%Y%m%dT%H%M%S}",
        fit_date=as_of,
        data_hash=_data_hash(data),
        n_rows=len(data),
        # What was ACTUALLY fitted, not what was offered. An operator reading this manifest
        # months later is asking "what did this model see?" — and the answer has to be true.
        feature_list=fitted_features,
        metrics={**metrics, "dropped_constant_features": dropped},
        # ★ REQ-060 — `is_promoted` is deliberately NOT passed here. The column defaults to
        # False, and the S-1001b AST guard forbids any production module outside
        # `data.promotion` from writing the flag at all — including writing it False. Passing
        # `is_promoted=False` would read as harmless and would open the door in the diff where
        # someone later changes the value rather than adding a line. Not writing it means this
        # module *cannot* mint a promoted artifact, rather than choosing not to.
    )
    session.add(artifact)
    session.flush()
    return artifact
