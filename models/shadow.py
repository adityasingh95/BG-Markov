"""The shadow-mode dashboard report — the operator's Gate-1 evidence (S-805, REQ-048).

Gate 1 is opened by the operator looking at the evidence, not by a row count. This report
composes the honest S-702 metrics — calibration, hypo recall @ a fixed false-alarm rate,
the Clarke danger grid, predictions vs actuals — and puts the ``β_insulin < 0``
confounding alarm on the same screen, so a confounded or miscalibrated model cannot look
ready to the operator deciding on Gate 1. It never headlines a plain-accuracy number
(that metric is forbidden; see S-702).

Operator-only: this is the pre-Gate-1 review surface. It composes ``models.metrics`` and
imports no ``core`` — it computes nothing new, it aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from models.metrics import (
    CalibrationBin,
    HypoRecallResult,
    brier_score,
    clarke_grid,
    hypo_recall_at_far,
    mae_mgdl,
    off_by_one_rate,
    reliability_curve,
    severe_state_error_rate,
)


@dataclass(frozen=True)
class ShadowReport:
    hypo_recall: HypoRecallResult
    calibration: tuple[CalibrationBin, ...]
    brier: float
    mae_mgdl: float
    clarke: dict[str, int]
    predictions_vs_actuals: dict[tuple[int, int], int]  # (predicted, actual) -> count
    off_by_one: float
    severe_error: float
    n_predictions: int
    beta_insulin_confounding: bool          # True iff the unconstrained fit wanted β_ins < 0
    unconstrained_beta_insulin: float


def _confusion(
    pred_states: npt.NDArray[np.int_], actual_states: npt.NDArray[np.int_]
) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for pred, actual in zip(pred_states.tolist(), actual_states.tolist(), strict=True):
        key = (int(pred), int(actual))
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_shadow_report(
    *,
    hypo_score: npt.ArrayLike,
    is_hypo: npt.ArrayLike,
    predicted_bg: npt.ArrayLike,
    reference_bg: npt.ArrayLike,
    pred_states: npt.ArrayLike,
    actual_states: npt.ArrayLike,
    unconstrained_beta_insulin: float,
    proba: npt.ArrayLike | None = None,
    states: tuple[int, ...] = (1, 2, 3, 4, 5),
    target_far: float = 0.10,
    n_bins: int = 10,
) -> ShadowReport:
    """Assemble the operator's shadow-mode report from the S-702 metric suite plus the
    ``β_insulin < 0`` confounding alarm.

    ``proba``/``actual_states`` (with ``states``) feed the multiclass Brier when a full
    predictive distribution is available; otherwise Brier is computed against the hypo
    score as a binary event.
    """
    hypo_arr = np.asarray(hypo_score, dtype=float)
    is_hypo_arr = np.asarray(is_hypo, dtype=bool)
    pred_states_arr = np.asarray(pred_states, dtype=int)
    actual_states_arr = np.asarray(actual_states, dtype=int)

    if proba is not None:
        brier = brier_score(proba, actual_states_arr, states=states)
    else:
        # Binary Brier on the hypo event when no full distribution is logged.
        brier = float(np.mean((hypo_arr - is_hypo_arr.astype(float)) ** 2))

    return ShadowReport(
        hypo_recall=hypo_recall_at_far(hypo_arr, is_hypo_arr, target_far=target_far),
        calibration=reliability_curve(hypo_arr, is_hypo_arr, n_bins=n_bins),
        brier=brier,
        mae_mgdl=mae_mgdl(predicted_bg, reference_bg),
        clarke=clarke_grid(reference_bg, predicted_bg),
        predictions_vs_actuals=_confusion(pred_states_arr, actual_states_arr),
        off_by_one=off_by_one_rate(pred_states_arr, actual_states_arr),
        severe_error=severe_state_error_rate(pred_states_arr, actual_states_arr),
        n_predictions=int(pred_states_arr.shape[0]),
        beta_insulin_confounding=unconstrained_beta_insulin < 0.0,
        unconstrained_beta_insulin=float(unconstrained_beta_insulin),
    )
