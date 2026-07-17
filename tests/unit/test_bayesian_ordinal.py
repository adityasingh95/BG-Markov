"""S-603 [SAFETY] — Bayesian ordinal (SDET, written RED first).

At single-patient sample sizes a point estimate is false precision; the honest object
is a posterior with credible intervals. INV-8 lives in the prior: a half-normal
(support ≥ 0) prior on the insulin coefficient gives zero density to "insulin raises
glucose" before any data is seen, so no confounded likelihood can move the posterior
across zero. This suite pins that the constraint survives into the posterior, that the
output is an interval (not a point), and that the interval widens as data thins.
See docs/stories/S-603.md.

RED: `models.bayesian_ordinal` does not exist yet.

These tests sample (NUTS); they are slower than the rest of the unit suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.safety import SafetyViolation
from models.bayesian_ordinal import (
    MIN_BAYESIAN_N,
    BayesianOrdinalFit,
    bayesian_gate_open,
    fit_bayesian_ordinal,
)
from models.state import bg_to_state

_INSULIN_COL = 1  # column order below: [carbs, insulin]


def _confounded_data(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Glucose rises with carbs, falls with insulin; insulin is correlated with carbs
    (confounding by indication), so the likelihood alone would pull β_insulin negative
    in the eta parameterisation. Standardised features; states via the binner."""
    rng = np.random.RandomState(seed)
    carbs = rng.uniform(0.0, 90.0, n)
    insulin = 0.08 * carbs + rng.uniform(0.0, 6.0, n)
    latent = 120.0 + 2.2 * (carbs - 45.0) - 24.0 * (insulin - 4.0) + rng.normal(0.0, 25.0, n)
    y = np.array([bg_to_state(v) for v in latent], dtype=int)
    x_raw = np.column_stack([carbs, insulin]).astype(float)
    x_z = (x_raw - x_raw.mean(axis=0)) / x_raw.std(axis=0)
    return x_z, y


@pytest.fixture(scope="module")
def _big_fit() -> BayesianOrdinalFit:
    x, y = _confounded_data(240, seed=0)
    return fit_bayesian_ordinal(
        x, y, insulin_col=_INSULIN_COL, draws=500, tune=500, chains=2, seed=1
    )


def test_posterior_insulin_support_is_one_sided(_big_fit: BayesianOrdinalFit) -> None:
    """★ Every β_insulin draw is ≥ 0 — the sign constraint survives into the posterior
    even on confounded data."""
    draws = _big_fit.insulin_draws
    assert draws.ndim == 1 and draws.size > 100
    assert np.all(draws >= 0.0)


def test_output_is_a_credible_interval_not_a_point(_big_fit: BayesianOrdinalFit) -> None:
    ci = _big_fit.credible_interval("beta_insulin", hdi_prob=0.94)
    assert ci.upper > ci.lower          # a genuine interval
    assert ci.width > 0.0
    assert ci.lower >= 0.0              # still one-sided


def test_intervals_widen_as_n_shrinks(_big_fit: BayesianOrdinalFit) -> None:
    """Thin data → wider credible interval (honest uncertainty, not false precision)."""
    x_small, y_small = _confounded_data(60, seed=2)
    small = fit_bayesian_ordinal(
        x_small, y_small, insulin_col=_INSULIN_COL, draws=500, tune=500, chains=2, seed=3
    )
    big_w = _big_fit.credible_interval("beta_insulin").width
    small_w = small.credible_interval("beta_insulin").width
    assert small_w > big_w


def test_inv8_is_wired_on_the_draws(_big_fit: BayesianOrdinalFit) -> None:
    from core.safety import inv8_beta_insulin_non_negative

    inv8_beta_insulin_non_negative(float(_big_fit.insulin_draws.min()))  # must not raise
    with pytest.raises(SafetyViolation):
        inv8_beta_insulin_non_negative(-1.0)                             # guard still bites


def test_insulin_col_out_of_range_raises() -> None:
    """Guard fires before any sampling — a bad column index is a programming error."""
    x, y = _confounded_data(30, seed=9)
    with pytest.raises(ValueError):
        fit_bayesian_ordinal(x, y, insulin_col=5)


def test_too_few_states_raises() -> None:
    """An ordinal model needs >= 3 states; fewer raises before sampling."""
    x = np.tile(np.array([[0.1, 0.2], [0.3, 0.4]]), (10, 1))
    y = np.array([1, 2] * 10)  # only two states
    with pytest.raises(ValueError):
        fit_bayesian_ordinal(x, y, insulin_col=1)


def test_bayesian_gate_opens_only_at_200() -> None:
    assert MIN_BAYESIAN_N == 200
    assert bayesian_gate_open(199) is False
    assert bayesian_gate_open(200) is True
    assert bayesian_gate_open(500) is True
