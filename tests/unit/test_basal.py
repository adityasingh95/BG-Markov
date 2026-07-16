"""S-402 — effective basal (Tresiba EWMA) + titration lockout. SDET, RED first.

Today's degludec dose is NOT today's effect (~42 h duration, 3–4 day steady
state). The effective dose is an EWMA (half-life 25 h); a dose change is
uninterpretable for 3 days (lockout). The step-change test is the one that proves
the multi-day carryover is modelled, not stepped. See docs/stories/S-402.md.

RED: `features.basal` does not exist yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from features.basal import (
    BASAL_HALFLIFE,
    TITRATION_LOCKOUT_DAYS,
    effective_basal,
    in_titration_lockout,
)

_D0 = datetime(2026, 1, 1, 8, 0)


def _daily(values: list[float]) -> list[tuple[datetime, float]]:
    return [(_D0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_halflife_is_25h() -> None:
    assert BASAL_HALFLIFE == "25h"
    assert TITRATION_LOCKOUT_DAYS == 3


def test_flat_series_returns_the_constant_dose() -> None:
    eff = effective_basal(_daily([24.0] * 7))
    for v in eff:
        assert v == pytest.approx(24.0, abs=1e-6)


def test_step_change_ramps_over_days_not_instantly() -> None:
    """★ Step 24 → 30 U on day 3. The effect must RAMP: strictly between 24 and 30
    a day after, near 30 several days later — the multi-day carryover, not a step."""
    doses = _daily([24.0, 24.0, 24.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0])
    eff = effective_basal(doses)

    # +1 day after the change (index 4): strictly between 24 and 30.
    assert 24.0 < eff[4] < 30.0, f"expected a ramp at +1 day, got {eff[4]}"
    # +5 days after the change (index 8): steady state, within 0.5 of 30.
    assert abs(eff[8] - 30.0) <= 0.5, f"expected ~30 at +5 days, got {eff[8]}"
    # and the raw-dose shortcut would read exactly 30 at +1 day — this is not that.
    assert eff[4] != pytest.approx(30.0, abs=1e-6)


def test_effective_basal_empty_is_empty() -> None:
    assert effective_basal([]) == []


# --- titration lockout ------------------------------------------------------


def test_lockout_flags_three_days_after_a_change() -> None:
    """Change on day 3 (24 -> 30). Days +1..+3 locked; +4 clear; change day locked."""
    doses = _daily([24.0, 24.0, 24.0, 30.0, 30.0, 30.0, 30.0, 30.0])
    change_day = _D0 + timedelta(days=3)

    assert in_titration_lockout(doses, change_day) is True  # the change day itself
    assert in_titration_lockout(doses, change_day + timedelta(days=1)) is True
    assert in_titration_lockout(doses, change_day + timedelta(days=2)) is True
    assert in_titration_lockout(doses, change_day + timedelta(days=3)) is True
    assert in_titration_lockout(doses, change_day + timedelta(days=4)) is False


def test_no_change_is_never_locked() -> None:
    doses = _daily([24.0] * 7)
    for i in range(7):
        assert in_titration_lockout(doses, _D0 + timedelta(days=i)) is False


def test_before_any_change_is_not_locked() -> None:
    doses = _daily([24.0, 24.0, 24.0, 30.0, 30.0])
    assert in_titration_lockout(doses, _D0 + timedelta(days=1)) is False  # pre-change
