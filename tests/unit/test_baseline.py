"""S-501 — the baseline predictor (SDET, written RED first).

The bar the ML must beat: carbs + insulin arithmetic (07 §4). Pure, directional,
and — because it produces a *predicted BG* — INV-6 bounded. See
docs/stories/S-501.md.

RED: `models.baseline` does not exist yet.
"""

from __future__ import annotations

import pytest

from core.safety import SafetyViolation
from models.baseline import predict_baseline_bg, predict_baseline_state

_ICR = 8.3
_ISF = 30.0


def _bg(pre_bg: float, carbs: float, mb: float, corr: float, iob: float) -> float:
    return predict_baseline_bg(
        pre_bg=pre_bg, carbs_g=carbs, meal_bolus_units=mb,
        correction_bolus_units=corr, iob_at_meal=iob, icr=_ICR, isf=_ISF,
    )


def test_zero_carbs_bolus_iob_gives_post_equals_pre() -> None:
    assert _bg(120, 0, 0.0, 0.0, 0.0) == 120.0
    assert _bg(88, 0, 0.0, 0.0, 0.0) == 88.0


def test_doubling_carbs_raises_the_prediction() -> None:
    low = _bg(120, 30, 4.0, 0.0, 0.0)
    high = _bg(120, 60, 4.0, 0.0, 0.0)
    assert high > low


def test_doubling_meal_bolus_lowers_the_prediction() -> None:
    less = _bg(160, 60, 3.0, 0.0, 0.0)
    more = _bg(160, 60, 6.0, 0.0, 0.0)
    assert more < less


def test_more_iob_lowers_the_prediction() -> None:
    assert _bg(160, 60, 4.0, 0.0, 2.0) < _bg(160, 60, 4.0, 0.0, 0.0)


# Golden: (pre_bg, carbs, meal_bolus, corr, iob) -> (predicted_bg, state).
_GOLDEN = [
    ((120, 60, 6.0, 0.0, 1.0), 126.87, 3),
    ((100, 0, 0.0, 0.0, 0.0), 100.00, 3),
    ((180, 45, 3.0, 0.0, 0.0), 252.65, 5),
    ((200, 30, 2.0, 0.0, 0.0), 248.43, 4),
    ((100, 0, 1.5, 0.0, 0.0), 55.00, 2),
]


@pytest.mark.parametrize("inp,expected_bg,expected_state", _GOLDEN)
def test_golden_predictions(
    inp: tuple[float, float, float, float, float], expected_bg: float, expected_state: int
) -> None:
    bg = _bg(*inp)
    assert bg == pytest.approx(expected_bg, abs=5e-3)
    assert predict_baseline_state(
        pre_bg=inp[0], carbs_g=inp[1], meal_bolus_units=inp[2],
        correction_bolus_units=inp[3], iob_at_meal=inp[4], icr=_ICR, isf=_ISF,
    ) == expected_state


def test_inv6_raises_on_impossibly_low_prediction() -> None:
    """Over-correction predicting ~8 mg/dL is an INV-6 hard error, not silent."""
    with pytest.raises(SafetyViolation):
        _bg(140, 30, 5.0, 1.0, 2.0)  # -> ~8.43


def test_inv6_raises_on_impossibly_high_prediction() -> None:
    with pytest.raises(SafetyViolation):
        _bg(400, 100, 0.0, 0.0, 0.0)  # -> ~761


def test_in_range_prediction_does_not_raise() -> None:
    assert 20.0 <= _bg(120, 60, 6.0, 0.0, 1.0) <= 600.0  # no raise
