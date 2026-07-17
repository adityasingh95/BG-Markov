"""S-601 — the ordinal model (SDET, written RED first).

ONE proportional-odds ordinal logit. The states are ordered, so the ordering is the
whole point: off-by-one is minor, off-by-three is catastrophic, and a multinomial
classifier cannot tell those apart. The load-bearing test is **ordinal sanity** — as
`pre_bg` rises, `P(state ≥ 4)` must be non-decreasing. See docs/stories/S-601.md.

RED: `models.ordinal` does not exist yet.
"""

from __future__ import annotations

import numpy as np

from models.ordinal import (
    DEFAULT_HYPO_WEIGHT,
    HYPO_STATES,
    OrdinalFit,
    fit_ordinal,
    hypo_confidence_weights,
)
from models.state import bg_to_state

_BOUND = (54, 80, 181, 251)


def _make_data(n: int = 400, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic meals spanning all five states: a monotone latent BG in ``pre_bg``
    (+ carbs noise), binned by the real state boundaries. Standardised features."""
    rng = np.random.RandomState(seed)
    pre_bg = rng.uniform(40.0, 320.0, n)
    carbs = rng.uniform(0.0, 90.0, n)
    latent = 0.9 * pre_bg + 0.3 * carbs + rng.normal(0.0, 18.0, n)
    y_state = np.array([bg_to_state(v) for v in latent], dtype=int)
    x_raw = np.column_stack([pre_bg, carbs]).astype(float)
    x_z = (x_raw - x_raw.mean(axis=0)) / x_raw.std(axis=0)
    conf = rng.uniform(0.5, 1.0, n)
    return x_z, y_state, conf


def test_probabilities_sum_to_one() -> None:
    x, y, conf = _make_data()
    fit = fit_ordinal(x, y, confidence_weights=conf)
    proba = fit.predict_proba(x)
    assert proba.shape == (x.shape[0], 5)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_ordinal_sanity_p_state_ge_4_non_decreasing_in_pre_bg() -> None:
    """★ The defining property: as pre_bg rises (carbs at mean), P(state ≥ 4) is
    non-decreasing. A multinomial fit has no reason to preserve this."""
    rng = np.random.RandomState(0)
    n = 400
    pre_bg = rng.uniform(40.0, 320.0, n)
    carbs = rng.uniform(0.0, 90.0, n)
    latent = 0.9 * pre_bg + 0.3 * carbs + rng.normal(0.0, 18.0, n)
    y = np.array([bg_to_state(v) for v in latent], dtype=int)
    x_raw = np.column_stack([pre_bg, carbs]).astype(float)
    mu, sd = x_raw.mean(axis=0), x_raw.std(axis=0)
    x_z = (x_raw - mu) / sd
    conf = rng.uniform(0.5, 1.0, n)

    fit = fit_ordinal(x_z, y, confidence_weights=conf)

    grid = np.linspace(40.0, 320.0, 60)
    g_raw = np.column_stack([grid, np.full(60, carbs.mean())])
    g_z = (g_raw - mu) / sd
    p_ge4 = fit.prob_at_least(g_z, 4)
    diffs = np.diff(p_ge4)
    assert np.all(diffs >= -1e-8), f"P(state>=4) must be non-decreasing; min diff {diffs.min()}"


def test_hypo_weights_are_confidence_times_hypo_multiplier() -> None:
    """Multiplicative combination (07 §8): hypo states × macro-confidence."""
    states = np.array([1, 2, 3, 4, 5])
    conf = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
    w = hypo_confidence_weights(states, conf, hypo_weight=4.0)
    assert w.tolist() == [2.0, 2.0, 0.5, 0.5, 0.5]
    # EXACT — pins the hypo set so a refactor cannot silently add state 4/5 to the
    # up-weighted (low-BG) set. Membership-only checks would miss that. Re-tightened by
    # SDET after audit 2026-07-17-01 F1 (see DL-028); the up-weighted states ARE the
    # lows she cannot feel, so this assertion is owned by the test author, not loosened.
    assert frozenset({1, 2}) == HYPO_STATES


def test_hypo_weight_default_upweights_only_lows() -> None:
    states = np.array([1, 2, 3, 4, 5])
    conf = np.ones(5)
    w = hypo_confidence_weights(states, conf)
    assert w[0] == DEFAULT_HYPO_WEIGHT and w[1] == DEFAULT_HYPO_WEIGHT
    assert w[2] == 1.0 and w[3] == 1.0 and w[4] == 1.0


def test_l2_shrinks_feature_coefficients() -> None:
    x, y, conf = _make_data()
    weak = fit_ordinal(x, y, confidence_weights=conf, l2_alpha=0.0)
    strong = fit_ordinal(x, y, confidence_weights=conf, l2_alpha=50.0)
    assert np.linalg.norm(strong.feature_coefs) < np.linalg.norm(weak.feature_coefs)


def test_prob_at_least_above_top_state_is_zero() -> None:
    """P(state ≥ 6) is 0 everywhere — no observed state satisfies it.

    SDET-owned (adopted after audit 2026-07-17-01 F1; see DL-028)."""
    x, y, conf = _make_data()
    fit = fit_ordinal(x, y, confidence_weights=conf)
    p = fit.prob_at_least(x, 6)
    assert p.shape == (x.shape[0],)
    assert np.all(p == 0.0)


def test_one_model_covers_all_five_states() -> None:
    """A single OrdinalFit — not five per-state sub-models — and on full-range data
    its observed states are the complete ordered 1..5."""
    x, y, conf = _make_data()
    fit = fit_ordinal(x, y, confidence_weights=conf)
    assert isinstance(fit, OrdinalFit)
    assert fit.states == (1, 2, 3, 4, 5)
