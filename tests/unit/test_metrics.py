"""S-702 — the metric suite (SDET, written RED first).

The metric decides what "good" means. On this imbalanced 5-class problem plain accuracy
rewards predicting the majority state while never catching a low, so it is NOT reported.
The headline is hypo recall at a fixed false-alarm rate; the Clarke grid weights errors
by clinical danger (D = failure to detect a low). See docs/stories/S-702.md.

RED: `models.metrics` does not exist yet.
"""

from __future__ import annotations

import numpy as np
import pytest

from models.metrics import (
    CalibrationBin,
    HypoRecallResult,
    brier_score,
    clarke_grid,
    clarke_zone,
    hypo_recall_at_far,
    mae_mgdl,
    off_by_one_rate,
    reliability_curve,
    severe_state_error_rate,
)

# --- hypo recall @ fixed FAR (PRIMARY) --------------------------------------


def test_hypo_recall_at_far_picks_threshold_and_reports_recall() -> None:
    # 4 hypo events (high scores), 6 non-hypo. One non-hypo has a moderately high score.
    hypo_score = np.array([0.9, 0.8, 0.7, 0.6, 0.55, 0.3, 0.2, 0.1, 0.05, 0.02])
    is_hypo = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
    res = hypo_recall_at_far(hypo_score, is_hypo, target_far=0.20)
    assert isinstance(res, HypoRecallResult)
    assert res.far <= 0.20 + 1e-9          # FAR held under target
    assert res.recall == 1.0                # all four lows caught at FAR 0 here
    assert res.target_far == 0.20


def test_hypo_recall_perfect_vs_useless() -> None:
    is_hypo = np.array([1, 1, 0, 0, 0, 0], dtype=bool)
    perfect = hypo_recall_at_far(np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0]), is_hypo, target_far=0.10)
    assert perfect.recall == 1.0 and perfect.far == 0.0
    # a "flag nothing" constant score cannot exceed the FAR budget by flagging, so recall 0
    useless = hypo_recall_at_far(np.zeros(6), is_hypo, target_far=0.0)
    assert useless.recall == 0.0


# --- Brier ------------------------------------------------------------------


def test_brier_perfect_predictions_score_zero() -> None:
    proba = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    y = np.array([1, 2, 3])
    assert brier_score(proba, y, states=(1, 2, 3)) == pytest.approx(0.0)


def test_brier_golden() -> None:
    # one row, p=[0.7,0.2,0.1], truth=state1 -> (0.3^2+0.2^2+0.1^2)=0.14
    proba = np.array([[0.7, 0.2, 0.1]])
    y = np.array([1])
    assert brier_score(proba, y, states=(1, 2, 3)) == pytest.approx(0.14, abs=1e-9)


# --- reliability / calibration ----------------------------------------------


def test_reliability_curve_is_well_calibrated_on_calibrated_data() -> None:
    rng = np.random.RandomState(0)
    prob = rng.uniform(0.0, 1.0, 4000)
    is_event = rng.uniform(0.0, 1.0, 4000) < prob  # event happens with prob p
    bins = reliability_curve(prob, is_event, n_bins=10)
    assert all(isinstance(b, CalibrationBin) for b in bins)
    for b in bins:
        assert abs(b.mean_predicted - b.observed_frequency) < 0.08


# --- MAE --------------------------------------------------------------------


def test_mae_golden() -> None:
    pred = np.array([100.0, 150.0, 200.0, 80.0, 300.0])
    true = np.array([110.0, 140.0, 190.0, 100.0, 280.0])
    # |−10|+|10|+|10|+|−20|+|20| = 70 /5 = 14
    assert mae_mgdl(pred, true) == pytest.approx(14.0)


# --- Clarke error grid (golden) ---------------------------------------------


def test_clarke_zone_reference_pairs_land_in_documented_zones() -> None:
    golden = {
        (100, 100): "A", (100, 105): "A", (70, 70): "A", (250, 260): "A",
        (50, 200): "E", (250, 60): "E",
        (100, 215): "C",
        (300, 150): "D",   # ★ truly high, predicted normal — failure to detect
        (50, 120): "D",    # ★ truly LOW, predicted normal — the low she cannot feel
        (100, 150): "B", (160, 60): "B",
    }
    for (ref, pred), zone in golden.items():
        assert clarke_zone(ref, pred) == zone, f"({ref},{pred}) expected {zone}"


def test_clarke_grid_counts_zones() -> None:
    reference = np.array([100, 100, 50, 300])
    predicted = np.array([100, 150, 120, 150])   # A, B, D, D
    grid = clarke_grid(reference, predicted)
    assert grid["A"] == 1 and grid["B"] == 1 and grid["D"] == 2
    assert sum(grid.values()) == 4


# --- ordinal error rates (no plain accuracy) --------------------------------


def test_off_by_one_and_severe_rates() -> None:
    pred = np.array([3, 4, 5, 3, 1])
    true = np.array([3, 3, 3, 4, 3])   # Δ = 0, 1, 2, 1, 2
    assert off_by_one_rate(pred, true) == pytest.approx(2 / 5)      # two off by exactly 1
    assert severe_state_error_rate(pred, true) == pytest.approx(2 / 5)  # two off by >= 2


def test_module_reports_no_plain_accuracy() -> None:
    """Plain accuracy / exact-match is the forbidden metric — it must not be exposed."""
    import models.metrics as m

    for banned in ("accuracy", "accuracy_score", "exact_match", "exact_match_rate"):
        assert not hasattr(m, banned), f"{banned} must not be a reported metric"
