"""S-401 [SAFETY] — IOB engine (Fiasp exponential curve). SDET, written RED first.

IOB is derived, never entered. The curve must be bounded [0,1], strictly decaying
on (0, td) — insulin only clears — and locked to hard-coded golden values so a
refactor cannot silently reshape it. A non-monotone or mis-peaked curve biases a
correction upward toward a low she cannot feel. See docs/stories/S-401.md.

RED: `features.iob` does not exist yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from features.iob import TD_MIN, TP_MIN, iob_at, iob_fraction

# Golden anchors — the exponential activity curve for tp=55, td=240, to 4 dp.
# (Computed independently from the LoopKit/OpenAPS model; Dev must match these.)
_GOLDEN = [
    (0.0, 1.0000),
    (30.0, 0.8763),
    (55.0, 0.6839),
    (120.0, 0.2394),
    (180.0, 0.0449),
    (240.0, 0.0000),
]


def test_parameters_are_fiasp() -> None:
    assert TP_MIN == 55.0
    assert TD_MIN == 240.0


def test_boundary_values() -> None:
    assert iob_fraction(0.0) == pytest.approx(1.0, abs=1e-9)
    assert iob_fraction(TD_MIN) == pytest.approx(0.0, abs=1e-9)


def test_pre_injection_and_clock_skew_clamp_to_full() -> None:
    """t <= 0 (a bolus 'in the future' from clock skew) is full IOB, not >1 or NaN."""
    assert iob_fraction(-5.0) == 1.0
    assert iob_fraction(-1000.0) == 1.0


def test_after_duration_is_zero() -> None:
    assert iob_fraction(TD_MIN) == 0.0
    assert iob_fraction(300.0) == 0.0


def test_in_range_zero_to_one() -> None:
    for i in range(-100, 3001):
        t = i / 10.0  # -10.0 .. 300.0 in 0.1 steps
        f = iob_fraction(t)
        assert 0.0 <= f <= 1.0, f"iob_fraction({t}) = {f} out of [0,1]"


def test_strictly_monotone_decreasing_on_open_interval() -> None:
    """★ The core correctness property: insulin only clears, never re-accumulates."""
    prev = iob_fraction(0.001)
    t = 0.5
    while t < TD_MIN:
        cur = iob_fraction(t)
        assert cur < prev, f"not decreasing at t={t}: {cur} !< {prev}"
        prev = cur
        t += 0.5


@pytest.mark.parametrize("t,expected", _GOLDEN)
def test_golden_curve_values(t: float, expected: float) -> None:
    assert iob_fraction(t) == pytest.approx(expected, abs=5e-5)


def test_iob_at_is_additive_over_boluses() -> None:
    """Linear in units: two 5 U boluses at one instant == one 10 U bolus =="
    10 * iob_fraction(elapsed)."""
    injected = datetime(2026, 7, 1, 8, 0)
    at = injected + timedelta(minutes=90)
    two_fives = iob_at(at, [(injected, 5.0), (injected, 5.0)])
    one_ten = iob_at(at, [(injected, 10.0)])
    assert two_fives == pytest.approx(one_ten, abs=1e-9)
    assert one_ten == pytest.approx(10.0 * iob_fraction(90.0), abs=1e-9)


def test_iob_at_sums_multiple_injections_at_their_own_ages() -> None:
    at = datetime(2026, 7, 1, 9, 0)
    boluses = [
        (datetime(2026, 7, 1, 8, 0), 6.0),   # 60 min old
        (datetime(2026, 7, 1, 8, 30), 4.0),  # 30 min old
    ]
    expected = 6.0 * iob_fraction(60.0) + 4.0 * iob_fraction(30.0)
    assert iob_at(at, boluses) == pytest.approx(expected, abs=1e-9)


def test_iob_at_ignores_fully_decayed_and_future_boluses() -> None:
    at = datetime(2026, 7, 1, 12, 0)
    boluses = [
        (datetime(2026, 7, 1, 7, 0), 8.0),    # 300 min old -> fully decayed (0)
        (datetime(2026, 7, 1, 13, 0), 5.0),   # in the future -> full fraction (1)
    ]
    assert iob_at(at, boluses) == pytest.approx(0.0 * 8.0 + 1.0 * 5.0, abs=1e-9)
