"""S-805 — the shadow-mode dashboard (SDET, written RED first).

Gate 1 is opened by the operator looking at the evidence, not by a row count. This report
is where the evidence lives: calibration, hypo recall @ FAR, the Clarke danger grid,
predictions vs actuals, and the β_insulin < 0 confounding alarm. It composes the honest
S-702 metrics — never a plain-accuracy headline. See docs/stories/S-805.md.

RED: `models.shadow` does not exist yet.
"""

from __future__ import annotations

import numpy as np
import pytest

from models.metrics import clarke_zone
from models.shadow import ShadowReport, build_shadow_report

_STATES = (1, 2, 3, 4, 5)


def _report(**overrides: object) -> ShadowReport:
    kwargs: dict[str, object] = dict(
        hypo_score=np.array([0.9, 0.8, 0.7, 0.3, 0.2, 0.1]),
        is_hypo=np.array([1, 1, 1, 0, 0, 0], dtype=bool),
        predicted_bg=np.array([100.0, 150.0, 60.0, 300.0]),
        reference_bg=np.array([110.0, 140.0, 55.0, 290.0]),
        pred_states=np.array([3, 3, 1, 5]),
        actual_states=np.array([3, 4, 1, 5]),
        unconstrained_beta_insulin=30.0,
    )
    kwargs.update(overrides)
    return build_shadow_report(**kwargs)  # type: ignore[arg-type]


def test_report_aggregates_the_metric_suite() -> None:
    r = _report()
    assert isinstance(r, ShadowReport)
    assert 0.0 <= r.hypo_recall.recall <= 1.0
    assert r.hypo_recall.far <= r.hypo_recall.target_far + 1e-9
    assert len(r.calibration) >= 1
    assert r.mae_mgdl == pytest.approx(np.mean([10.0, 10.0, 5.0, 10.0]))
    assert sum(r.clarke.values()) == 4


def test_predictions_vs_actuals_confusion_matrix() -> None:
    r = _report()
    assert r.n_predictions == 4
    # (3,3), (3,4), (1,1), (5,5)
    assert r.predictions_vs_actuals[(3, 3)] == 1
    assert r.predictions_vs_actuals[(3, 4)] == 1
    assert r.predictions_vs_actuals[(1, 1)] == 1
    assert r.predictions_vs_actuals[(5, 5)] == 1
    assert sum(r.predictions_vs_actuals.values()) == r.n_predictions
    # one off-by-one (3 vs 4), no severe errors here
    assert r.off_by_one == pytest.approx(1 / 4)
    assert r.severe_error == pytest.approx(0.0)


def test_beta_insulin_negative_raises_the_confounding_warning() -> None:
    """★ The most dangerous data-quality signal is surfaced, not hidden."""
    confounded = _report(unconstrained_beta_insulin=-5.7)
    assert confounded.beta_insulin_confounding is True
    assert confounded.unconstrained_beta_insulin == -5.7

    healthy = _report(unconstrained_beta_insulin=30.0)
    assert healthy.beta_insulin_confounding is False


def test_multiclass_brier_when_a_distribution_is_supplied() -> None:
    """When a full predictive distribution is logged, Brier is the multiclass score."""
    proba = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
    r = _report(
        proba=proba,
        pred_states=np.array([1, 2, 3, 1]),
        actual_states=np.array([1, 2, 3, 1]),  # perfect one-hot ⇒ Brier 0
        states=(1, 2, 3),
    )
    assert r.brier == pytest.approx(0.0)


def test_clarke_danger_zone_is_preserved() -> None:
    """A truly-low, predicted-normal pair must land in Clarke zone D on the dashboard."""
    r = _report(
        predicted_bg=np.array([120.0]),   # predicted normal
        reference_bg=np.array([50.0]),    # truly low — failure to detect
        pred_states=np.array([3]),
        actual_states=np.array([1]),
    )
    assert clarke_zone(50.0, 120.0) == "D"
    assert r.clarke["D"] == 1
