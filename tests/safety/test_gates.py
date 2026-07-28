"""S-703 [SAFETY] — gate enforcement (SDET, written RED first).

Gate 1 decides whether she ever SEES a model output (INV-2). It must be earned from live
data every call — never a row count alone, never a cached "yes", never a flag anyone can
flip. These tests are adversarial: assume a future refactor will try to weaken them.
See docs/stories/S-703.md.

**S-1011 (DL-035): Gate 2 / INV-1 is RETIRED**, so its suite is gone from this file. The
ICR is now an ordinary input to `recommend_bolus` (a plain `ValueError` when missing or
<= 0) — those tests live in `test_bolus.py`. **Gate 1 below is untouched**: retiring one
gate must not erode the other, and this file is the guard on that.
"""

from __future__ import annotations

import inspect

import pytest

from core.safety import GateNotPassed, SafetyViolation
from prescribe.gates import (
    GATE1_MIN_VALID_MEALS,
    gate1_status,
    require_gate1,
)

# --- Gate 1 / patient output (INV-2) ----------------------------------------


def test_149_valid_meals_keeps_gate1_closed() -> None:
    status = gate1_status(valid_meals=149, model_hypo_recall=0.9, baseline_hypo_recall=0.5)
    assert status.is_open is False
    with pytest.raises(GateNotPassed):
        require_gate1(status)


def test_150_valid_meals_beating_baseline_opens_gate1() -> None:
    status = gate1_status(valid_meals=150, model_hypo_recall=0.9, baseline_hypo_recall=0.5)
    assert status.is_open is True
    require_gate1(status)  # must not raise


def test_volume_alone_never_opens_gate1() -> None:
    """★ 200 valid meals but hypo recall below baseline ⇒ STILL CLOSED. The model must
    EARN patient visibility; it is not granted by row count."""
    below = gate1_status(valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50)
    assert below.is_open is False
    with pytest.raises(GateNotPassed):
        require_gate1(below)
    # a tie does not open it either — the model must strictly beat the baseline
    tie = gate1_status(valid_meals=200, model_hypo_recall=0.50, baseline_hypo_recall=0.50)
    assert tie.is_open is False


# --- live, not cached (ADR-7) -----------------------------------------------


def test_gate1_is_live_not_cached() -> None:
    """★ The gate result flips when the live input flips, within one process — no memo.
    A cached "open" is a silent safety failure (ADR-7)."""
    closed = gate1_status(valid_meals=10, model_hypo_recall=0.9, baseline_hypo_recall=0.5)
    assert closed.is_open is False
    reopened = gate1_status(valid_meals=200, model_hypo_recall=0.9, baseline_hypo_recall=0.5)
    assert reopened.is_open is True
    # and back again, same process — no memoisation anywhere
    assert gate1_status(
        valid_meals=10, model_hypo_recall=0.9, baseline_hypo_recall=0.5
    ).is_open is False


def test_gate2_is_retired_and_gone() -> None:
    """★ Gate 2 must be ABSENT, not dormant (S-1011). A leftover gate helper is an
    invitation to re-wire it; Gate 1 must remain."""
    import prescribe.gates as gates

    for gone in ("gate2_status", "require_gate2", "Gate2Status"):
        assert not hasattr(gates, gone), f"{gone} survived the S-1011 retirement"
    assert hasattr(gates, "gate1_status") and hasattr(gates, "require_gate1")


def test_gate1_constant_matches_adherence() -> None:
    from data.adherence import GATE1_VALID_MEALS

    assert GATE1_MIN_VALID_MEALS == GATE1_VALID_MEALS == 150
