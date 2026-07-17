"""Bayesian ordinal model — the honest form at n ≥ 200 (S-603, REQ-031, INV-8, 07 §8).

At single-patient sample sizes a point estimate is false precision. This module fits a
Bayesian proportional-odds ordinal model (``PyMC`` ``OrderedLogistic``) and reports
**credible intervals**. INV-8 is encoded where it belongs — in the prior: the insulin
coefficient has a ``HalfNormal`` (support ≥ 0) prior and enters the linear predictor
with a negative sign, so the posterior gives **zero** density to "insulin raises
glucose" for any data, however confounded. The invariant is still asserted on the
sampled draws — the constraint is never merely assumed.

This module imports only ``core.safety`` (the invariant) — no other project code.
"""

from __future__ import annotations

from dataclasses import dataclass

import arviz as az
import numpy as np
import numpy.typing as npt
import pymc as pm
from pymc.distributions.transforms import ordered

from core.safety import inv8_beta_insulin_non_negative

_FloatArray = npt.NDArray[np.float64]

# 07 §8: the Bayesian ordinal is the production model at n >= 200.
MIN_BAYESIAN_N = 200

_DEFAULT_DRAWS = 500
_DEFAULT_TUNE = 500
_DEFAULT_CHAINS = 2
_PRIOR_SIGMA_INSULIN = 1.0
_PRIOR_SIGMA_OTHER = 1.0
_PRIOR_SIGMA_CUT = 5.0
_HDI_PROB = 0.94


def bayesian_gate_open(n: int) -> bool:
    """The 07 §8 production gate: use the Bayesian ordinal only once ``n >= 200``."""
    return n >= MIN_BAYESIAN_N


@dataclass(frozen=True)
class CredibleInterval:
    lower: float
    upper: float

    @property
    def width(self) -> float:
        return self.upper - self.lower


@dataclass(frozen=True)
class BayesianOrdinalFit:
    """A fitted Bayesian ordinal model. ``insulin_draws`` are the posterior draws of the
    (non-negative) insulin sensitivity coefficient; ``idata`` is the full arviz trace."""

    n: int
    insulin_draws: _FloatArray
    idata: az.InferenceData

    def credible_interval(
        self, name: str = "beta_insulin", hdi_prob: float = _HDI_PROB
    ) -> CredibleInterval:
        """Highest-density credible interval for a parameter (default the insulin
        coefficient) — an interval, never a point estimate."""
        hdi = az.hdi(self.idata, var_names=[name], prob=hdi_prob)
        bounds = np.asarray(hdi[name].values, dtype=float).ravel()
        return CredibleInterval(lower=float(bounds[0]), upper=float(bounds[1]))


def fit_bayesian_ordinal(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    *,
    insulin_col: int,
    draws: int = _DEFAULT_DRAWS,
    tune: int = _DEFAULT_TUNE,
    chains: int = _DEFAULT_CHAINS,
    seed: int = 0,
) -> BayesianOrdinalFit:
    """Fit the Bayesian ordinal over standardised features ``x`` and integer states
    ``y``. ``insulin_col`` is the column carrying the INV-8-constrained coefficient.

    The insulin coefficient has a ``HalfNormal`` prior (support ≥ 0) and enters ``eta``
    with a negative sign, so a non-negative draw means insulin can only *lower* the
    predicted state. INV-8 is asserted on the minimum draw.
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y)
    n, p = x_arr.shape
    if not 0 <= insulin_col < p:
        raise ValueError(f"insulin_col {insulin_col} out of range for {p} features")

    cats = sorted({int(v) for v in y_arr.tolist()})
    n_states = len(cats)
    if n_states < 3:
        raise ValueError("Bayesian ordinal needs >= 3 observed states")
    # 0-index the observed states so OrderedLogistic sees 0..n_states-1.
    remap = {c: i for i, c in enumerate(cats)}
    y0 = np.array([remap[int(v)] for v in y_arr.tolist()], dtype=int)

    other_cols = [j for j in range(p) if j != insulin_col]
    x_insulin = x_arr[:, insulin_col]
    x_other = x_arr[:, other_cols] if other_cols else np.zeros((n, 0))

    with pm.Model():
        beta_insulin = pm.HalfNormal("beta_insulin", sigma=_PRIOR_SIGMA_INSULIN)
        eta = -beta_insulin * x_insulin  # insulin can only LOWER the state
        if other_cols:
            beta_other = pm.Normal(
                "beta_other", mu=0.0, sigma=_PRIOR_SIGMA_OTHER, shape=len(other_cols)
            )
            eta = eta + pm.math.dot(x_other, beta_other)
        cutpoints = pm.Normal(
            "cutpoints",
            mu=0.0,
            sigma=_PRIOR_SIGMA_CUT,
            shape=n_states - 1,
            transform=ordered,
            initval=np.linspace(-2.0, 2.0, n_states - 1),
        )
        pm.OrderedLogistic("y_obs", eta=eta, cutpoints=cutpoints, observed=y0)
        idata = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            cores=1,
            random_seed=seed,
            progressbar=False,
            compute_convergence_checks=False,
        )

    insulin_draws = np.asarray(
        idata.posterior["beta_insulin"].values, dtype=float
    ).ravel()
    # INV-8 asserted on the sampled minimum — the guard bites if the prior is ever
    # swapped for an unconstrained one. It cannot fire under HalfNormal, by construction.
    inv8_beta_insulin_non_negative(float(insulin_draws.min()))

    return BayesianOrdinalFit(n=n, insulin_draws=insulin_draws, idata=idata)
