"""Brant test for the proportional-odds assumption (S-602, REQ-031, 07 §8).

The ordinal model (S-601) assumes one slope vector shared across every threshold. That
assumption is testable and plausibly wrong here — exercise can act non-monotonically
across the BG thresholds — so we run a Brant test after every fit and **escalate** on
rejection rather than silently accepting a mis-specified model.

Implementation notes:
- The per-threshold binary logits are fit with a small, deterministic Newton–Raphson.
  ``statsmodels``' discrete ``Logit`` is unusable under the pinned toolchain
  (``import statsmodels.api`` fails: ``scipy 1.18`` removed ``_lazywhere``; see
  DL-026), so we avoid that import path entirely.
- The covariance of the stacked slope estimates is the Brant (1990) sandwich; the
  omnibus and per-predictor statistics are Wald contrasts against a shared slope.

This module imports nothing from the project — it is a pure statistical routine.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import stats

_FloatArray = npt.NDArray[np.float64]

_DEFAULT_ALPHA = 0.05
_RIDGE = 1e-8       # Hessian stabiliser for the binary Newton step
_MAX_ITER = 100
_TOL = 1e-9


@dataclass(frozen=True)
class PredictorBrant:
    """Per-predictor proportional-odds test (does this feature share one slope?)."""

    index: int
    stat: float
    df: int
    p_value: float
    holds: bool


@dataclass(frozen=True)
class BrantResult:
    omnibus_stat: float
    omnibus_df: int
    omnibus_p: float
    holds: bool                          # omnibus_p >= alpha
    per_predictor: tuple[PredictorBrant, ...]
    violators: tuple[int, ...]           # predictor indices with per-predictor p < alpha
    alpha: float


class ProportionalOddsViolation(Exception):
    """Escalation (07 §8 step 2): the proportional-odds assumption was rejected.

    Carries the :class:`BrantResult` so the operator sees the evidence — which
    predictors violate — and can move to a partial-proportional-odds fit that frees
    exactly those slopes. Raising this is the escalation: the model is **not** accepted
    silently.
    """

    def __init__(self, result: BrantResult) -> None:
        self.result = result
        viol = ", ".join(str(i) for i in result.violators) or "none"
        super().__init__(
            f"Proportional-odds assumption rejected (Brant omnibus "
            f"chi2={result.omnibus_stat:.2f}, df={result.omnibus_df}, "
            f"p={result.omnibus_p:.2e} < alpha={result.alpha}). Non-proportional "
            f"predictors: [{viol}]. Escalate to partial proportional odds (07 §8)."
        )


def _fit_binary_logit(x_design: _FloatArray, z: _FloatArray) -> tuple[_FloatArray, _FloatArray]:
    """MLE of a binary logit (design ``x_design`` already includes an intercept column).

    Returns ``(beta, fitted_probs)``. Newton–Raphson with a ridge-stabilised Hessian so
    a near-separated fold does not blow up.
    """
    n, k = x_design.shape
    beta = np.zeros(k, dtype=float)
    ridge = _RIDGE * np.eye(k)
    for _ in range(_MAX_ITER):
        eta = x_design @ beta
        prob = 1.0 / (1.0 + np.exp(-eta))
        w = prob * (1.0 - prob)
        gradient = x_design.T @ (z - prob)
        hessian = (x_design * w[:, None]).T @ x_design + ridge
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if float(np.max(np.abs(step))) < _TOL:
            break
    prob = 1.0 / (1.0 + np.exp(-(x_design @ beta)))
    return beta, prob


def brant_test(
    x: npt.ArrayLike, y: npt.ArrayLike, *, alpha: float = _DEFAULT_ALPHA
) -> BrantResult:
    """Brant test of proportional odds for the ordinal fit over features ``x``.

    ``x`` is ``(n, p)`` (no intercept column); ``y`` is the integer state per row.
    ``holds`` is ``True`` when the omnibus test does not reject at ``alpha``.
    """
    x_raw = np.asarray(x, dtype=float)
    y_arr = np.asarray(y)
    n, p = x_raw.shape

    cats = np.array(sorted({int(v) for v in y_arr.tolist()}))
    thresholds = cats[:-1]                 # J-1 binary splits
    m = int(thresholds.shape[0])
    if m < 2:
        raise ValueError("Brant test needs >= 3 observed states (>= 2 thresholds)")

    x_design = np.column_stack([np.ones(n), x_raw])   # n x (p+1)
    kk = p + 1

    slope_betas: list[_FloatArray] = []
    probs: list[_FloatArray] = []
    for t in thresholds:
        z = (y_arr > t).astype(float)
        beta, prob = _fit_binary_logit(x_design, z)
        slope_betas.append(beta[1:])       # drop intercept
        probs.append(prob)
    beta_stack = np.concatenate(slope_betas)          # length m*p

    # Brant (1990) covariance of the stacked (intercept-inclusive) estimates.
    xtwx_inv = [
        np.linalg.inv((x_design * (pi * (1.0 - pi))[:, None]).T @ x_design) for pi in probs
    ]
    cov = np.zeros((m * kk, m * kk), dtype=float)
    for a in range(m):
        for b in range(m):
            lo, hi = (a, b) if a <= b else (b, a)
            w_cross = probs[hi] * (1.0 - probs[lo])   # Cov(z_lo, z_hi) = pi_hi(1-pi_lo)
            cross = (x_design * w_cross[:, None]).T @ x_design
            cov[a * kk:(a + 1) * kk, b * kk:(b + 1) * kk] = xtwx_inv[a] @ cross @ xtwx_inv[b]

    # Restrict to the slope coefficients (drop each block's intercept row/col).
    slope_idx = [a * kk + j for a in range(m) for j in range(1, kk)]
    cov_slopes = cov[np.ix_(slope_idx, slope_idx)]

    omnibus_stat, omnibus_df = _wald_equal_slopes(beta_stack, cov_slopes, m, p, cols=range(p))
    omnibus_p = float(stats.chi2.sf(omnibus_stat, omnibus_df))

    per_predictor: list[PredictorBrant] = []
    violators: list[int] = []
    for j in range(p):
        stat_j, df_j = _wald_equal_slopes(beta_stack, cov_slopes, m, p, cols=(j,))
        p_j = float(stats.chi2.sf(stat_j, df_j))
        holds_j = p_j >= alpha
        per_predictor.append(PredictorBrant(j, float(stat_j), df_j, p_j, holds_j))
        if not holds_j:
            violators.append(j)

    return BrantResult(
        omnibus_stat=float(omnibus_stat),
        omnibus_df=int(omnibus_df),
        omnibus_p=omnibus_p,
        holds=omnibus_p >= alpha,
        per_predictor=tuple(per_predictor),
        violators=tuple(violators),
        alpha=alpha,
    )


def _wald_equal_slopes(
    beta_stack: _FloatArray,
    cov_slopes: _FloatArray,
    m: int,
    p: int,
    *,
    cols: Iterable[int],
) -> tuple[float, int]:
    """Wald statistic for ``β_k[j] = β_{m-1}[j]`` across thresholds ``k``, for the
    predictor columns in ``cols``. Returns ``(chi2, df)``."""
    col_list = list(cols)
    rows: list[_FloatArray] = []
    for k in range(m - 1):
        for j in col_list:
            contrast = np.zeros(m * p, dtype=float)
            contrast[k * p + j] = 1.0
            contrast[(m - 1) * p + j] = -1.0
            rows.append(contrast)
    d = np.array(rows, dtype=float)                    # (df, m*p)
    diff = d @ beta_stack
    middle = d @ cov_slopes @ d.T
    stat = float(diff @ np.linalg.solve(middle, diff))
    return stat, len(rows)


def check_proportional_odds(
    x: npt.ArrayLike, y: npt.ArrayLike, *, alpha: float = _DEFAULT_ALPHA
) -> BrantResult:
    """The after-every-fit gate: run the Brant test; **raise**
    :class:`ProportionalOddsViolation` (the escalation) when PO is rejected, otherwise
    return the result."""
    result = brant_test(x, y, alpha=alpha)
    if not result.holds:
        raise ProportionalOddsViolation(result)
    return result
