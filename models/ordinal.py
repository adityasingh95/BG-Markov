"""The ordinal model — one proportional-odds ordinal logit (S-601, REQ-031, 07 §8).

The clinical states are **ordered**: predicting State 4 when the truth is State 1 is
catastrophic, while off-by-one is minor. A multinomial classifier rates those two
mistakes equally and is therefore the wrong model class. This module fits **one**
ordinal logistic regression with ``pre_bg`` continuous, L2-penalised feature
coefficients, and the hypo states up-weighted (multiplicatively with the
macro-confidence weights) because they are rare and they are the ones that matter.

Deviation (DL-025): 07 §8 specifies ``method="lbfgs"``; under the pinned
``statsmodels==0.14.4`` / ``scipy==1.18.0`` that call raises
``TypeError: fmin_l_bfgs_b() got an unexpected keyword argument 'disp'``. We use
``method="bfgs"`` — the same maximum-likelihood objective by a different quasi-Newton
step. It is not a modelling change.

Absent-class hazard (DL-025): on a tiny single-patient fold a state may be entirely
unobserved. Forcing all five categories makes the missing threshold unidentifiable
(the fit diverges; probabilities stop summing to 1). We therefore model the
**observed** ordered states and report them via ``OrdinalFit.states`` — we never
fabricate a zero-probability column for an unseen state, which for a hypo state would
silently assert "this low cannot happen". The full 5-vector mapping and the refusal
that must accompany a missing hypo class belong to the gate/risk stories (S-703/S-804).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from statsmodels.miscmodels.ordinal_model import OrderedModel

HYPO_STATES: frozenset[int] = frozenset({1, 2})
DEFAULT_HYPO_WEIGHT: float = 4.0
DEFAULT_L2_ALPHA: float = 1.0

_FloatArray = npt.NDArray[np.float64]


class _WeightedL2OrderedModel(OrderedModel):  # type: ignore[misc]  # statsmodels is untyped
    """``OrderedModel`` with per-observation weights and an L2 ridge on the **feature**
    coefficients only (never the thresholds).

    ``loglikeobs`` is scaled by the sample weights; ``loglike`` is their sum minus
    ``l2_alpha·‖β_features‖²``. The base class supplies numeric gradients by
    differentiating this ``loglike``, so the penalty is honoured by the optimiser.
    """

    def __init__(
        self,
        endog: object,
        exog: object,
        *,
        weights: _FloatArray,
        l2_alpha: float,
        **kwargs: object,
    ) -> None:
        super().__init__(endog, exog, **kwargs)
        self._weights = np.asarray(weights, dtype=float)
        self._l2_alpha = float(l2_alpha)
        self._n_feature_coefs = int(self.k_vars)  # exog coefs precede the thresholds

    def loglikeobs(self, params: _FloatArray) -> _FloatArray:
        base = np.asarray(super().loglikeobs(params), dtype=float)
        return np.asarray(self._weights * base, dtype=float)

    def loglike(self, params: _FloatArray) -> float:
        ll = float(self.loglikeobs(params).sum())
        betas = np.asarray(params[: self._n_feature_coefs], dtype=float)
        return ll - self._l2_alpha * float(np.sum(betas**2))


@dataclass(frozen=True)
class OrdinalFit:
    """A fitted ordinal model. ``states`` gives the meaning of each probability column
    (the observed ordered states, e.g. ``(1, 2, 3, 4, 5)``)."""

    states: tuple[int, ...]
    feature_coefs: _FloatArray  # β on the features (L2-penalised), threshold-free
    _model: _WeightedL2OrderedModel
    _params: _FloatArray

    def predict_proba(self, x: npt.ArrayLike) -> _FloatArray:
        """Per-state probabilities, shape ``(n, len(states))``; rows sum to 1."""
        proba = self._model.predict(self._params, exog=np.asarray(x, dtype=float))
        return np.asarray(proba, dtype=float)

    def to_params(self) -> dict[str, Any]:
        """The fitted model as plain, inspectable numbers (S-1014).

        Round-tripping lives **next to the model** because the threshold parameterisation is
        an internal detail of this module: statsmodels stores the first cutpoint raw and the
        rest as log-increments. A serialiser in `data/` would have to reach in here, and
        would break quietly the next time statsmodels changed.

        Never a pickle (DL-052) — unpickling executes code, and a blob cannot answer *"what
        does this model do?"*.
        """
        return {
            "kind": "ordinal_po",
            "states": [int(v) for v in self.states],
            "params": [float(v) for v in self._params],
            "n_features": int(self._model.k_vars),
        }

    def prob_at_least(self, x: npt.ArrayLike, state: int) -> _FloatArray:
        """``P(state ≥ ``state``)`` — the monotone ordinal quantity (sum of the
        columns whose observed state is ``≥ state``)."""
        proba = self.predict_proba(x)
        cols = [i for i, s in enumerate(self.states) if s >= state]
        if not cols:
            return np.zeros(proba.shape[0], dtype=float)
        return np.asarray(proba[:, cols].sum(axis=1), dtype=float)


def hypo_confidence_weights(
    y_state: npt.ArrayLike,
    confidence_weights: npt.ArrayLike,
    *,
    hypo_weight: float = DEFAULT_HYPO_WEIGHT,
) -> _FloatArray:
    """The observation weights (07 §8): ``confidence × hypo_weight`` for hypo states
    (1, 2), ``confidence × 1`` otherwise — up-weighting combined **multiplicatively**
    with the macro-confidence weights."""
    states = np.asarray(y_state)
    conf = np.asarray(confidence_weights, dtype=float)
    multiplier = np.where(np.isin(states, list(HYPO_STATES)), hypo_weight, 1.0)
    return np.asarray(conf * multiplier, dtype=float)


def fit_ordinal(
    x: npt.ArrayLike,
    y_state: npt.ArrayLike,
    *,
    confidence_weights: npt.ArrayLike,
    hypo_weight: float = DEFAULT_HYPO_WEIGHT,
    l2_alpha: float = DEFAULT_L2_ALPHA,
) -> OrdinalFit:
    """Fit **one** proportional-odds ordinal logit over the (already-scaled) feature
    matrix ``x`` and integer states ``y_state``.

    ``pre_bg`` is expected to be a continuous column of ``x`` (never binned as an
    input). Observations are weighted by ``hypo_confidence_weights`` and the feature
    coefficients are L2-penalised by ``l2_alpha``.
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y_state)
    weights = hypo_confidence_weights(y_arr, confidence_weights, hypo_weight=hypo_weight)

    model = _WeightedL2OrderedModel(
        y_arr, x_arr, weights=weights, l2_alpha=l2_alpha, distr="logit"
    )
    # DL-025: bfgs, not the spec's lbfgs (statsmodels 0.14.4 / scipy 1.18.0 incompat).
    result = model.fit(method="bfgs", maxiter=2000, disp=False)
    params = np.asarray(result.params, dtype=float)

    states = tuple(int(s) for s in sorted(set(int(v) for v in y_arr.tolist())))
    feature_coefs = params[: int(model.k_vars)].copy()
    return OrdinalFit(
        states=states, feature_coefs=feature_coefs, _model=model, _params=params
    )


def ordinal_from_params(stored: dict[str, Any]) -> OrdinalFit:
    """Rebuild an :class:`OrdinalFit` from :meth:`OrdinalFit.to_params` (S-1014).

    A model shell of the right shape is reconstructed and the saved ``params`` are supplied
    to ``predict``; nothing is re-fitted, so the reloaded model is the fitted one rather than
    an approximation of it.
    """
    if stored.get("kind") != "ordinal_po":
        raise ValueError(f"unknown stored model kind: {stored.get('kind')!r}")
    states = tuple(int(s) for s in stored["states"])
    params = np.asarray(stored["params"], dtype=float)
    n_features = int(stored["n_features"])

    # A shell with the right shape: `predict` needs the model's threshold bookkeeping, which
    # is derived from the number of levels and features, not from the training rows.
    n_rows = max(len(states), 2)
    endog = np.array([states[i % len(states)] for i in range(n_rows)], dtype=int)
    exog = np.zeros((n_rows, n_features), dtype=float)
    shell = _WeightedL2OrderedModel(
        endog, exog, weights=np.ones(n_rows), l2_alpha=0.0, distr="logit"
    )
    return OrdinalFit(
        states=states,
        feature_coefs=params[:n_features].copy(),
        _model=shell,
        _params=params,
    )
