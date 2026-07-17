"""S-602 — Brant test for proportional odds (SDET, written RED first).

The ordinal model (S-601) assumes one slope vector shared across every threshold.
That is testable and here it is plausibly wrong — exercise can act non-monotonically
across the BG thresholds. This suite pins the after-every-fit Brant check: PO-satisfying
data passes; threshold-varying data is rejected AND the escalation fires (a raised
ProportionalOddsViolation naming the offending predictors). See docs/stories/S-602.md.

RED: `models.brant` does not exist yet.
"""

from __future__ import annotations

import numpy as np
import pytest

from models.brant import (
    BrantResult,
    ProportionalOddsViolation,
    brant_test,
    check_proportional_odds,
)
from models.state import bg_to_state


def _po_data(n: int = 600, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Proportional-odds data: one latent, common slope, binned by state boundaries."""
    rng = np.random.RandomState(seed)
    x1 = rng.uniform(40.0, 320.0, n)
    x2 = rng.uniform(0.0, 90.0, n)
    latent = 0.9 * x1 + 0.3 * x2 + rng.logistic(0.0, 20.0, n)
    y = np.array([bg_to_state(v) for v in latent], dtype=int)
    x_raw = np.column_stack([x1, x2]).astype(float)
    x_z = (x_raw - x_raw.mean(axis=0)) / x_raw.std(axis=0)
    return x_z, y


def _threshold_varying_data(n: int = 600, seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Non-PO data: x1's slope changes across thresholds (γ=[3,1,1,-3]); x2 is inert."""
    rng = np.random.RandomState(seed)
    x1 = rng.uniform(-2.0, 2.0, n)
    x2 = rng.uniform(-2.0, 2.0, n)  # inert — not in the generative model
    u = rng.uniform(0.0, 1.0, n)
    y = np.ones(n, dtype=int)
    for alpha, gamma in zip((2.0, 1.0, -1.0, -2.0), (3.0, 1.0, 1.0, -3.0), strict=True):
        prob = 1.0 / (1.0 + np.exp(-(alpha + gamma * x1)))
        y += (u <= prob).astype(int)
    x_raw = np.column_stack([x1, x2]).astype(float)
    return x_raw, y


def test_proportional_odds_data_passes() -> None:
    x, y = _po_data()
    res = brant_test(x, y)
    assert isinstance(res, BrantResult)
    assert res.holds is True
    assert res.omnibus_p >= 0.05
    # the gate returns the result and does NOT raise on PO-satisfying data
    assert check_proportional_odds(x, y) is not None


def test_threshold_varying_data_fails_and_escalates() -> None:
    """★ The load-bearing test: a non-PO fit must be rejected and the escalation fire."""
    x, y = _threshold_varying_data()
    res = brant_test(x, y)
    assert res.holds is False
    assert res.omnibus_p < 0.05
    with pytest.raises(ProportionalOddsViolation):
        check_proportional_odds(x, y)


def test_escalation_carries_the_violating_predictors() -> None:
    """The raised violation names which slopes a partial-PO fit would free."""
    x, y = _threshold_varying_data()
    try:
        check_proportional_odds(x, y)
    except ProportionalOddsViolation as exc:
        assert 0 in exc.result.violators          # x1 is non-proportional
        assert 1 not in exc.result.violators      # x2 is inert → proportional
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("expected ProportionalOddsViolation")


def test_too_few_states_raises() -> None:
    """A Brant test needs >= 3 states (>= 2 thresholds) to compare slopes across."""
    x = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8]])
    y = np.array([1, 1, 2, 2])  # only two states
    with pytest.raises(ValueError):
        brant_test(x, y)


def test_result_shapes_and_degrees_of_freedom() -> None:
    x, y = _po_data()
    res = brant_test(x, y)
    n_predictors = x.shape[1]
    n_states = len(set(y.tolist()))
    assert res.omnibus_df == n_predictors * (n_states - 2)
    assert len(res.per_predictor) == n_predictors
    for pp in res.per_predictor:
        assert pp.df == n_states - 2
