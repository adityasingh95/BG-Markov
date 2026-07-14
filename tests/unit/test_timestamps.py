"""S-202 — reported-timestamp derivations (SDET, written RED first).

Pure functions: the two most predictive features are computed here from
REPORTED datetimes only. Neither ever reads a clock.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from core.timestamps import bolus_offset_min, elapsed_min


@pytest.mark.parametrize(
    ("meal", "bolus", "expected"),
    [
        (datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 7, 45), -15),  # pre-bolus
        (datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 7, 30), -30),
        (datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 8, 0), 0),  # with food
        (datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 8, 10), 10),  # after eating
    ],
)
def test_bolus_offset_min_is_signed(meal: datetime, bolus: datetime, expected: int) -> None:
    assert bolus_offset_min(meal, bolus) == expected


def test_bolus_before_meal_is_negative_after_is_positive() -> None:
    meal = datetime(2026, 7, 1, 8, 0)
    assert bolus_offset_min(meal, datetime(2026, 7, 1, 7, 59)) < 0
    assert bolus_offset_min(meal, datetime(2026, 7, 1, 8, 1)) > 0


@pytest.mark.parametrize(
    ("meal", "post", "expected"),
    [
        (datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 10, 0), 120),
        (datetime(2026, 7, 1, 10, 0), datetime(2026, 7, 1, 11, 45), 105),
        (datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 10, 15), 135),
    ],
)
def test_elapsed_min(meal: datetime, post: datetime, expected: int) -> None:
    assert elapsed_min(meal, post) == expected


def test_elapsed_min_rounds_to_nearest_minute() -> None:
    meal = datetime(2026, 7, 1, 8, 0, 0)
    assert elapsed_min(meal, datetime(2026, 7, 1, 10, 0, 20)) == 120  # 120m 20s -> 120
    assert elapsed_min(meal, datetime(2026, 7, 1, 10, 0, 40)) == 121  # 120m 40s -> 121
