"""Feature pipeline — assembling the model's input vector (S-404, 07 §5).

Builds the feature vector from the meal record plus the EPIC-4 derived features
(IOB, effective basal, exercise). Rules that keep the model honest:

- ``pre_bg`` is **continuous** — never binned as an input (binning discards exactly
  the low-BG resolution the model needs to predict a low).
- The **outcome** (``post_bg``, ``elapsed_min``) is never a feature — that is target
  leakage.
- ``macro_confidence / 100`` is the ``sample_weight``.
- Continuous features are standardised with a ``StandardScaler`` that must be fit on
  **training folds only** (see ``features.cv``) — fitting on all rows leaks test
  statistics into scaling.
"""

from __future__ import annotations

from sklearn.preprocessing import StandardScaler

from data.tables import MealEvent, MealType
from features.exercise import encode_exercise

# The feature vector, in a fixed order (07 §5). post_bg / elapsed_min (the outcome)
# are absent by construction — target leakage cannot happen here.
FEATURE_NAMES: list[str] = [
    "pre_bg",
    "carbs_g", "net_carbs_g", "protein_g", "fat_g", "fiber_g",
    "meal_bolus_units", "correction_bolus_units",
    "bolus_offset_min",
    "iob_at_meal",
    "effective_basal",
    "minutes_since_last_bolus",
    "meal_type_lunch", "meal_type_dinner",
    "ex_light", "ex_intense", "ex_duration_min", "ex_offset_min",
    "ex_light_x_duration", "ex_intense_x_duration",
    "pre_ex_light", "pre_ex_intense", "pre_ex_duration_min",
]

# Binary indicators are NOT standardised; everything else is continuous.
_INDICATORS = {
    "meal_type_lunch", "meal_type_dinner",
    "ex_light", "ex_intense", "pre_ex_light", "pre_ex_intense",
}
CONTINUOUS_FEATURES: list[str] = [f for f in FEATURE_NAMES if f not in _INDICATORS]


def feature_vector(
    meal: MealEvent,
    *,
    iob_at_meal: float,
    effective_basal: float,
    minutes_since_last_bolus: float,
) -> dict[str, float]:
    """The feature vector for one meal (keys == ``FEATURE_NAMES``).

    ``iob_at_meal`` / ``effective_basal`` / ``minutes_since_last_bolus`` are the
    derived quantities the caller computes from the IOB / basal engines and
    ``bolus_log``. ``net_carbs`` is computed here (floored) so the vector does not
    depend on the DB-computed column.
    """
    net_carbs = max(float(meal.carbs_g) - float(meal.fiber_g), 0.0)
    ex = encode_exercise(meal.ex_intensity, meal.ex_duration_min, prefix="ex")
    pre_ex = encode_exercise(
        meal.pre_ex_intensity, meal.pre_ex_duration_min, prefix="pre_ex"
    )
    return {
        "pre_bg": float(meal.pre_bg),  # CONTINUOUS — never binned as an input
        "carbs_g": float(meal.carbs_g),
        "net_carbs_g": net_carbs,
        "protein_g": float(meal.protein_g),
        "fat_g": float(meal.fat_g),
        "fiber_g": float(meal.fiber_g),
        "meal_bolus_units": float(meal.meal_bolus_units),
        "correction_bolus_units": float(meal.correction_bolus_units),
        "bolus_offset_min": float(meal.bolus_offset_min),  # SIGNED
        "iob_at_meal": float(iob_at_meal),
        "effective_basal": float(effective_basal),
        "minutes_since_last_bolus": float(minutes_since_last_bolus),
        "meal_type_lunch": 1.0 if meal.meal_type == MealType.lunch else 0.0,
        "meal_type_dinner": 1.0 if meal.meal_type == MealType.dinner else 0.0,
        "ex_light": ex["ex_light"],
        "ex_intense": ex["ex_intense"],
        "ex_duration_min": float(meal.ex_duration_min),
        "ex_offset_min": float(meal.ex_offset_min if meal.ex_offset_min is not None else 0),
        "ex_light_x_duration": ex["ex_light_min"],
        "ex_intense_x_duration": ex["ex_intense_min"],
        "pre_ex_light": pre_ex["pre_ex_light"],
        "pre_ex_intense": pre_ex["pre_ex_intense"],
        "pre_ex_duration_min": float(meal.pre_ex_duration_min),
    }


def sample_weight(meal: MealEvent) -> float:
    """``macro_confidence / 100`` — low-confidence macros count less (07 §5)."""
    return float(meal.macro_confidence) / 100.0


def make_scaler() -> StandardScaler:
    """A fresh ``StandardScaler`` to be fit **inside** CV on a train fold only.

    Never fit on the full set — that leaks test-fold statistics into the scaling
    (see the leakage tests).
    """
    return StandardScaler()
