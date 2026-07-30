"""Scoring the promoted model against what actually happened (S-1009, DL-049).

The DB boundary between `prediction_log` and the S-805 shadow report. It reads what was
predicted and what was observed, and computes nothing itself — the metrics live in
`models.metrics`, composed by `models.shadow`.

★ **It fails closed at every step.** No promoted model, no scored predictions, or
predictions from a *different* model version, all produce nothing rather than something
approximate. The operator opens Gate 1 on this evidence, so a page that fills itself in from
thin material is more dangerous than a page that stays empty.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.tables import PredictionLog

# The canonical set lives in models.ordinal and is pinned exactly by the F1/DL-028
# tests. Re-declaring {1, 2} here is precisely the drift those tests exist to catch.
from models.ordinal import HYPO_STATES

# Fewer than this and the metrics are noise wearing a report's clothes: a hypo recall over
# three predictions is a fraction with a denominator of one or two.
MIN_SCORED_PREDICTIONS: int = 10


@dataclass(frozen=True)
class ScoredPredictions:
    """Aligned predicted / observed arrays for one model version."""

    hypo_score: npt.NDArray[np.float64]   # P(state ∈ {1,2}) as logged
    is_hypo: npt.NDArray[np.bool_]
    pred_states: npt.NDArray[np.int_]
    actual_states: npt.NDArray[np.int_]

    def __len__(self) -> int:
        return int(self.actual_states.shape[0])


def _as_probability(value: object) -> float:
    """A logged JSON value as a probability, or 0.0.

    `predicted_distribution` is a JSON column, so its values are `object` as far as the type
    system is concerned. A row written by an older schema, or with a null, is a real
    historical row — it reads as 0.0 rather than raising, because refusing to read it would
    blank the dashboard for a reason that has nothing to do with the model.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _hypo_probability(distribution: dict[str, object]) -> float:
    """``P(low)`` from a logged distribution: the mass on states 1 and 2.

    A missing state contributes 0.0 rather than raising — a distribution logged before a
    state was ever observed is a real historical row, and refusing to read it would make the
    dashboard blank for a reason that has nothing to do with the model.
    """
    return sum(_as_probability(distribution.get(str(s))) for s in HYPO_STATES)


def _argmax_state(distribution: dict[str, object]) -> int:
    best_state, best_p = 3, -1.0
    for key, value in distribution.items():
        try:
            state = int(key)
        except (TypeError, ValueError):
            continue
        p = _as_probability(value)
        if p > best_p:
            best_state, best_p = state, p
    return best_state


def scored_predictions(session: Session, *, model_version: str) -> ScoredPredictions | None:
    """Predictions made by ``model_version`` whose outcome is known, or ``None``.

    ★ **Scoped to one version.** A prediction made by last month's model is not evidence
    about this month's; mixing them would let a retired model's record flatter — or damn —
    the one the operator is actually deciding about.

    ★ **Requires a backfilled ``actual_state``.** Until DL-049's backfill has run there is
    no outcome to compare against, and a row with a NULL outcome is *unknown*, not *in
    range*. Returns ``None`` below ``MIN_SCORED_PREDICTIONS``.
    """
    rows = list(
        session.scalars(
            select(PredictionLog)
            .where(
                PredictionLog.model_version == model_version,
                PredictionLog.actual_state.is_not(None),
                # ★ A REFUSAL is not a prediction. A guarded refusal carries no usable
                # distribution, so scoring it reads as "the model predicted no low" — which
                # is a different statement from "the model declined to predict", and it is
                # the model's record that gets the blame. Refusals are auditable (S-801/
                # S-802) and separately countable; they are not evidence about accuracy.
                PredictionLog.guardrail_fired.is_(None),
            )
            .order_by(PredictionLog.created_at)
        )
    )
    if len(rows) < MIN_SCORED_PREDICTIONS:
        return None

    actual = np.array([int(r.actual_state or 0) for r in rows], dtype=int)
    is_hypo = np.isin(actual, list(HYPO_STATES))
    # ★ Both classes must be present. Hypo recall is undefined without lows to recall — and
    # without non-lows there is no false-alarm rate to hold it at. That is not a corner case
    # to paper over: Gate 1's beats-baseline condition IS a hypo-recall comparison, so a
    # window containing no lows cannot support the decision this page exists for. Saying so
    # is more useful than a report whose headline metric is a fraction over zero.
    if not is_hypo.any() or is_hypo.all():
        return None

    return ScoredPredictions(
        hypo_score=np.array([_hypo_probability(r.predicted_distribution) for r in rows]),
        is_hypo=is_hypo,
        pred_states=np.array(
            [_argmax_state(r.predicted_distribution) for r in rows], dtype=int
        ),
        actual_states=actual,
    )
