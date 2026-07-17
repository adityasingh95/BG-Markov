"""S-801 [SAFETY] — output guardrails (SDET, written RED first).

A guess is worse than a refusal, and infinitely more dangerous to someone who cannot feel
a low. When the model is out of its depth — unseen meal, thin data, an indecisive
posterior, a clash with the baseline, or an impossible number — the correct output is NOT
a bare state. These tests pin the five conditions and prove the arg-max shortcut cannot
survive. See docs/stories/S-801.md.

RED: `models.guardrails` does not exist yet.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.safety import SafetyViolation
from models.guardrails import (
    CONFIDENCE_THRESHOLD,
    SPARSE_MIN_NEIGHBORS,
    GuardedPrediction,
    RefusalReason,
    guard_prediction,
)

_STATES = (1, 2, 3, 4, 5)


def _confident_proba(state: int, peak: float = 0.8) -> np.ndarray:
    """A proba vector peaked on ``state`` at ``peak``, rest spread evenly."""
    p = np.full(5, (1.0 - peak) / 4.0)
    p[state - 1] = peak
    return p


def _guard(**overrides: object) -> GuardedPrediction:
    kwargs: dict[str, object] = dict(
        proba=_confident_proba(3),
        states=_STATES,
        predicted_bg=120.0,
        baseline_state=3,
        in_distribution=True,
        n_nearby_train=50,
    )
    kwargs.update(overrides)
    return guard_prediction(**kwargs)  # type: ignore[arg-type]


def test_clean_confident_agreeing_prediction_is_returned() -> None:
    g = _guard()
    assert g.refused is False and g.conflict is False
    assert g.state == 3


def test_out_of_distribution_refuses() -> None:
    g = _guard(in_distribution=False)
    assert g.refused is True
    assert g.reason is RefusalReason.OUT_OF_DISTRIBUTION
    assert g.state is None


def test_sparse_region_refuses() -> None:
    assert SPARSE_MIN_NEIGHBORS == 10
    g = _guard(n_nearby_train=9)
    assert g.refused is True and g.reason is RefusalReason.SPARSE_REGION
    assert _guard(n_nearby_train=10).refused is False  # exactly 10 is dense enough


def test_diffuse_posterior_boundary() -> None:
    """★ No state exceeds 40% ⇒ refuse ("not confident"); 41% ⇒ a state."""
    assert CONFIDENCE_THRESHOLD == 0.40
    diffuse = _guard(proba=_confident_proba(3, peak=0.39))
    assert diffuse.refused is True
    assert diffuse.reason is RefusalReason.DIFFUSE_POSTERIOR
    assert "confident" in diffuse.message.lower()
    assert diffuse.state is None

    confident = _guard(proba=_confident_proba(3, peak=0.41))
    assert confident.refused is False
    assert confident.state == 3


def test_baseline_conflict_shows_both_and_picks_no_winner() -> None:
    """★ Baseline State 3, model State 5 ⇒ BOTH shown, flagged, NO winner."""
    g = _guard(proba=_confident_proba(5, peak=0.8), baseline_state=3)
    assert g.refused is False
    assert g.conflict is True
    assert g.model_state == 5 and g.baseline_state == 3
    assert g.state is None  # the system does NOT pick a winner


def test_one_state_apart_is_not_a_conflict() -> None:
    g = _guard(proba=_confident_proba(4, peak=0.8), baseline_state=3)
    assert g.conflict is False
    assert g.state == 4


def test_physiologically_absurd_prediction_is_a_hard_error() -> None:
    """★ Predicted BG outside [20, 600] raises (INV-6); the boundaries do not."""
    with pytest.raises(SafetyViolation):
        _guard(predicted_bg=601.0)
    with pytest.raises(SafetyViolation):
        _guard(predicted_bg=19.0)
    # boundaries are valid — no raise
    _guard(predicted_bg=600.0)
    _guard(predicted_bg=20.0)


def test_absurd_is_checked_before_a_refusal_can_mask_it() -> None:
    """An impossible BG must raise even when another refusal condition also holds — it is
    a hard error, never quietly downgraded to a refusal message."""
    with pytest.raises(SafetyViolation):
        _guard(predicted_bg=650.0, in_distribution=False)
