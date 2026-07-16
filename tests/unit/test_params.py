"""S-503 [SAFETY] — ICR/ISF constrained OLS (SDET, RED first).

Confounding by indication is the central hazard: bolus is chosen in response to
carbs and pre-BG, so observational data makes insulin look like it RAISES glucose.
The constrained fit forces β_ins ≥ 0 (INV-8); an unconstrained negative coefficient
is REPORTED, not swallowed; the correction-event ISF wins on disagreement. The
confounded test is the single most important test in the model epics. See
docs/stories/S-503.md.

RED: `models.params` does not exist yet.
"""

from __future__ import annotations

import logging

import pytest

from core.safety import SafetyViolation
from models.params import cross_check_isf, fit_icr_isf

# carbs / bolus varied independently so the design is not collinear.
_CB = [(40, 4), (60, 5), (30, 2), (80, 6), (50, 7), (70, 4), (45, 3), (90, 8), (35, 5), (65, 6)]


def _rows(delta_fn: object) -> list[tuple[float, float, float, float]]:
    rows = []
    for carbs, bolus in _CB:
        delta = delta_fn(carbs, bolus)  # type: ignore[operator]
        rows.append((120.0, float(carbs), float(bolus), 120.0 + delta))
    return rows


def test_clean_data_recovers_icr_and_isf() -> None:
    """delta = 3·carbs − 30·bolus ⇒ β_carb≈3, β_ins≈30 (ISF 30, ICR 10)."""
    fit = fit_icr_isf(_rows(lambda c, b: 3 * c - 30 * b))
    assert fit.beta_carb == pytest.approx(3.0, abs=1e-6)
    assert fit.beta_ins == pytest.approx(30.0, abs=1e-6)
    assert fit.isf == pytest.approx(30.0, abs=1e-6)
    assert fit.icr == pytest.approx(10.0, abs=1e-6)  # ISF/β_carb = 30/3
    assert fit.confounding_warning is False


def test_confounded_data_constrains_beta_ins_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """★ Bolus positively associated with post-BG (delta = 3·carbs + 10·bolus):
    the unconstrained fit wants β_ins < 0 (insulin 'raises' glucose). The applied
    fit must be β_ins ≥ 0 (INV-8) AND the confounding-by-indication warning fires."""
    with caplog.at_level(logging.WARNING):
        fit = fit_icr_isf(_rows(lambda c, b: 3 * c + 10 * b))

    assert fit.unconstrained_beta_ins < 0.0        # the naive fit is dangerous
    assert fit.beta_ins >= 0.0                      # INV-8 holds on the applied value
    assert fit.confounding_warning is True
    assert any(
        "confounding" in r.message.lower() for r in caplog.records
    ), "a prominent confounding-by-indication warning must be logged"


def test_beta_ins_is_non_negative_on_both_datasets() -> None:
    clean = fit_icr_isf(_rows(lambda c, b: 3 * c - 30 * b))
    conf = fit_icr_isf(_rows(lambda c, b: 3 * c + 10 * b))
    assert clean.beta_ins >= 0.0
    assert conf.beta_ins >= 0.0


def test_inv8_holds_for_the_applied_fit() -> None:
    """The applied β_ins never violates INV-8; a hypothetical negative would raise."""
    from core.safety import inv8_beta_insulin_non_negative

    fit = fit_icr_isf(_rows(lambda c, b: 3 * c + 10 * b))
    inv8_beta_insulin_non_negative(fit.beta_ins)  # must not raise
    with pytest.raises(SafetyViolation):
        inv8_beta_insulin_non_negative(-1.0)  # the guard still bites


def test_cross_check_prefers_correction_events_on_disagreement() -> None:
    chk = cross_check_isf(ols_isf=45.0, correction_isf=30.0)  # 50% off
    assert chk.flagged is True
    assert chk.chosen_isf == 30.0            # the unconfounded value wins
    assert chk.chosen_source == "correction_events"


def test_cross_check_agrees_within_tolerance() -> None:
    chk = cross_check_isf(ols_isf=31.0, correction_isf=30.0)  # ~3% off
    assert chk.flagged is False


def test_too_few_rows_raises() -> None:
    with pytest.raises(ValueError):
        fit_icr_isf([(120.0, 40.0, 4.0, 130.0), (120.0, 60.0, 5.0, 150.0)])
