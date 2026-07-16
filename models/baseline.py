"""The baseline predictor — the bar the ML must beat (S-501, 07 §4).

Pure carbs + insulin arithmetic. Also the fallback when the kill switch trips, the
guardrail-4 conflict check, and the ICR/ISF estimator. Because it produces a
*predicted BG*, INV-6 is enforced on the prediction: a value outside [20, 600]
raises rather than silently becoming State 5.
"""

from __future__ import annotations

from core.safety import inv6_predicted_bg_in_range
from models.state import bg_to_state


def predict_baseline_bg(
    *,
    pre_bg: float,
    carbs_g: float,
    meal_bolus_units: float,
    correction_bolus_units: float,
    iob_at_meal: float,
    icr: float,
    isf: float,
) -> float:
    """``pre_bg + (carbs_g/ICR)·ISF − (meal_bolus + correction + iob)·ISF`` (07 §4).

    ``icr`` / ``isf`` come from ``patient_profile``. INV-6 bounds the result.
    """
    predicted = (
        pre_bg
        + (carbs_g / icr) * isf
        - meal_bolus_units * isf
        - correction_bolus_units * isf
        - iob_at_meal * isf
    )
    inv6_predicted_bg_in_range(predicted)  # INV-6 — a predicted BG out of range is a hard error
    return predicted


def predict_baseline_state(
    *,
    pre_bg: float,
    carbs_g: float,
    meal_bolus_units: float,
    correction_bolus_units: float,
    iob_at_meal: float,
    icr: float,
    isf: float,
) -> int:
    """The baseline's predicted clinical state — bins the predicted BG (output)."""
    predicted = predict_baseline_bg(
        pre_bg=pre_bg,
        carbs_g=carbs_g,
        meal_bolus_units=meal_bolus_units,
        correction_bolus_units=correction_bolus_units,
        iob_at_meal=iob_at_meal,
        icr=icr,
        isf=isf,
    )
    return bg_to_state(predicted)
