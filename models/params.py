"""ICR/ISF from sign-constrained OLS — the confounding-by-indication guard
(S-503, REQ-032, INV-8).

Bolus is chosen in response to carbs and pre-meal BG, so observational data makes
higher insulin correlate with higher post-meal glucose — a naive fit learns that
insulin *raises* glucose, and inverting that into a dose is a hypo pathway. The
applied fit is therefore sign-constrained (`β_ins ≥ 0`, INV-8); when the
unconstrained fit wants a negative coefficient, that is **reported** (a prominent
warning + a flag), never silently accepted; and the confounded OLS ISF is
cross-checked against the unconfounded correction-event ISF, which wins on
disagreement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import lsq_linear

from core.safety import inv8_beta_insulin_non_negative

_log = logging.getLogger(__name__)

_MIN_ROWS = 3  # intercept + 2 coefficients
_ZERO = 1e-9


@dataclass(frozen=True)
class IcrIsfFit:
    beta_carb: float             # >= 0 (constrained) — mg/dL per g carb
    beta_ins: float              # >= 0 (constrained) — ISF, mg/dL per unit
    intercept: float
    isf: float                   # = beta_ins
    icr: float | None            # = isf / beta_carb (None if beta_carb ~ 0)
    unconstrained_beta_ins: float
    confounding_warning: bool    # True iff the unconstrained fit wanted beta_ins < 0


@dataclass(frozen=True)
class IsfCrossCheck:
    flagged: bool                # True iff OLS and correction-event ISF disagree
    chosen_isf: float
    chosen_source: str           # "correction_events" on disagreement, else "ols"


def fit_icr_isf(rows: list[tuple[float, float, float, float]]) -> IcrIsfFit:
    """Sign-constrained OLS of ``(post_bg − pre_bg)`` on ``[carbs_g, total_bolus, 1]``.

    ``rows = [(pre_bg, carbs_g, total_bolus, post_bg), …]``. Applies ``β_carb ≥ 0``
    and ``β_ins ≥ 0``; reports (and logs) when the unconstrained fit wanted
    ``β_ins < 0``.
    """
    if len(rows) < _MIN_ROWS:
        raise ValueError(f"fit_icr_isf needs >= {_MIN_ROWS} rows, got {len(rows)}")

    y = np.array([post - pre for pre, _c, _b, post in rows], dtype=float)
    a = np.array([[carbs, bolus, 1.0] for _pre, carbs, bolus, _post in rows], dtype=float)

    unc, *_ = np.linalg.lstsq(a, y, rcond=None)
    unconstrained_beta_ins = float(-unc[1])

    lower = np.array([0.0, -np.inf, -np.inf])   # b_carb >= 0, b_bolus <= 0, intercept free
    upper = np.array([np.inf, 0.0, np.inf])
    con = lsq_linear(a, y, bounds=(lower, upper)).x
    beta_carb = float(con[0])
    beta_ins = float(-con[1])
    intercept = float(con[2])

    inv8_beta_insulin_non_negative(beta_ins)  # INV-8 on the value actually used

    confounding = unconstrained_beta_ins < 0.0
    if confounding:
        _log.warning(
            "S-503: confounding by indication — the unconstrained fit gives "
            "beta_ins=%.3f < 0 (insulin appears to RAISE glucose). Applying the "
            "beta_ins >= 0 constraint (INV-8); do NOT accept the negative coefficient.",
            unconstrained_beta_ins,
        )

    icr = beta_ins / beta_carb if beta_carb > _ZERO else None
    return IcrIsfFit(
        beta_carb=beta_carb,
        beta_ins=beta_ins,
        intercept=intercept,
        isf=beta_ins,
        icr=icr,
        unconstrained_beta_ins=unconstrained_beta_ins,
        confounding_warning=confounding,
    )


def cross_check_isf(
    *, ols_isf: float, correction_isf: float, tol_frac: float = 0.20
) -> IsfCrossCheck:
    """Cross-check the (confounded) OLS ISF against the (unconfounded) correction-
    event ISF. On material disagreement (> ``tol_frac``) the correction value wins
    and the result is flagged (07 §7)."""
    disagree = abs(ols_isf - correction_isf) / correction_isf > tol_frac
    if disagree:
        return IsfCrossCheck(True, correction_isf, "correction_events")
    return IsfCrossCheck(False, ols_isf, "ols")
