"""S-501 — the shared BG→state binner (SDET, written RED first).

One binning function, one boundary set (03 §), used by the baseline, the ordinal
model, and the risk readout. Ordering is load-bearing: predicting State 4 when the
truth is State 1 is catastrophic, so the states must be correctly ordered and the
boundaries exact. See docs/stories/S-501.md.

RED: `models.state` does not exist yet.
"""

from __future__ import annotations

import pytest

from models.state import STATE_BOUNDARIES, bg_to_state

# (bg, expected state) at and around every boundary [54, 80, 181, 251].
_CASES = [
    (20, 1), (53, 1), (53.9, 1),
    (54, 2), (70, 2), (79, 2), (79.9, 2),
    (80, 3), (120, 3), (180, 3), (180.9, 3),
    (181, 4), (220, 4), (250, 4), (250.9, 4),
    (251, 5), (400, 5), (600, 5),
]


def test_boundaries_are_the_clinical_set() -> None:
    assert STATE_BOUNDARIES == (54, 80, 181, 251)


@pytest.mark.parametrize("bg,expected", _CASES)
def test_bg_to_state_bins_correctly(bg: float, expected: int) -> None:
    assert bg_to_state(bg) == expected


def test_state_is_monotone_non_decreasing_in_bg() -> None:
    """Ordering is load-bearing — a higher BG never maps to a lower state."""
    prev = 0
    bg = 20.0
    while bg <= 600.0:
        s = bg_to_state(bg)
        assert s >= prev, f"state decreased at bg={bg}: {s} < {prev}"
        assert 1 <= s <= 5
        prev = s
        bg += 1.0
