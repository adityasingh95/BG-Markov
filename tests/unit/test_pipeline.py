"""S-404 — feature pipeline assembly (SDET, written RED first).

Builds the model's feature vector (07 §5) from the meal + EPIC-4 derived features.
pre_bg is CONTINUOUS; macro_confidence/100 is the sample_weight; the OUTCOME
(post_bg, elapsed_min) is never a feature. See docs/stories/S-404.md.

RED: `features.pipeline` does not exist yet.
"""

from __future__ import annotations

from datetime import datetime

from data.tables import ExIntensity, LoggedBy, MealEvent, MealType
from features.pipeline import (
    CONTINUOUS_FEATURES,
    FEATURE_NAMES,
    feature_vector,
    sample_weight,
)


def _meal(**over: object) -> MealEvent:
    fields: dict[str, object] = {
        "datetime": datetime(2026, 3, 1, 8, 0),
        "logged_at": datetime(2026, 3, 1, 8, 30),
        "logged_by": LoggedBy.patient,
        "meal_type": MealType.lunch,
        "pre_bg": 142,
        "pre_bg_time": datetime(2026, 3, 1, 7, 55),
        "meal_bolus_units": 6.0,
        "correction_bolus_units": 1.0,
        "bolus_offset_min": -15,
        "carbs_g": 45.0,
        "protein_g": 12.0,
        "fat_g": 8.0,
        "fiber_g": 5.0,
        "macro_confidence": 95,
        "ex_intensity": ExIntensity.light,
        "ex_duration_min": 30,
        "ex_offset_min": 20,
        "pre_ex_intensity": ExIntensity.none,
        "pre_ex_duration_min": 0,
    }
    fields.update(over)
    return MealEvent(**fields)


def _fv(meal: MealEvent) -> dict[str, float]:
    return feature_vector(
        meal, iob_at_meal=1.2, effective_basal=26.0, minutes_since_last_bolus=200.0
    )


def test_feature_vector_keys_are_exactly_feature_names() -> None:
    fv = _fv(_meal())
    assert set(fv) == set(FEATURE_NAMES)
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))  # no dupes


def test_pre_bg_is_continuous_raw_value() -> None:
    fv = _fv(_meal(pre_bg=63))
    assert fv["pre_bg"] == 63.0  # the raw number, not a bin index


def test_net_carbs_is_floored_carbs_minus_fiber() -> None:
    fv = _fv(_meal(carbs_g=45.0, fiber_g=5.0))
    assert fv["net_carbs_g"] == 40.0
    fv2 = _fv(_meal(carbs_g=10.0, fiber_g=40.0))
    assert fv2["net_carbs_g"] == 0.0  # floored, never negative


def test_meal_type_one_hot_breakfast_is_baseline() -> None:
    lunch = _fv(_meal(meal_type=MealType.lunch))
    assert (lunch["meal_type_lunch"], lunch["meal_type_dinner"]) == (1.0, 0.0)
    bkfst = _fv(_meal(meal_type=MealType.breakfast))
    assert (bkfst["meal_type_lunch"], bkfst["meal_type_dinner"]) == (0.0, 0.0)


def test_derived_values_pass_through() -> None:
    fv = _fv(_meal())
    assert fv["iob_at_meal"] == 1.2
    assert fv["effective_basal"] == 26.0
    assert fv["minutes_since_last_bolus"] == 200.0
    assert fv["bolus_offset_min"] == -15.0  # signed


def test_exercise_features_present_and_interacted() -> None:
    fv = _fv(_meal(ex_intensity=ExIntensity.light, ex_duration_min=30))
    assert fv["ex_light"] == 1.0
    assert fv["ex_intense"] == 0.0
    assert fv["ex_duration_min"] == 30.0
    assert fv["ex_light_x_duration"] == 30.0
    assert fv["ex_intense_x_duration"] == 0.0


def test_null_ex_offset_is_zero() -> None:
    fv = _fv(_meal(ex_offset_min=None))
    assert fv["ex_offset_min"] == 0.0


def test_sample_weight_is_macro_confidence_over_100() -> None:
    assert sample_weight(_meal(macro_confidence=95)) == 0.95
    assert sample_weight(_meal(macro_confidence=50)) == 0.5


def test_continuous_features_are_a_subset_of_feature_names() -> None:
    assert set(CONTINUOUS_FEATURES) <= set(FEATURE_NAMES)
    # indicators are NOT standardised
    for ind in ("ex_light", "ex_intense", "meal_type_lunch", "pre_ex_light"):
        assert ind not in CONTINUOUS_FEATURES
