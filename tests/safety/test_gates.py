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

import pytest

from core.safety import GateNotPassed
from prescribe.gates import (
    GATE1_MIN_VALID_MEALS,
    SHADOW_MIN_DAYS,
    gate1_status,
    require_gate1,
)

# --- Gate 1 / patient output (INV-2) ----------------------------------------


def test_149_valid_meals_keeps_gate1_closed() -> None:
    status = gate1_status(valid_meals=149, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                          is_promoted=True, shadow_days=120, calibration_ok=True)
    assert status.is_open is False
    with pytest.raises(GateNotPassed):
        require_gate1(status)


def test_150_valid_meals_beating_baseline_opens_gate1() -> None:
    status = gate1_status(valid_meals=150, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                          is_promoted=True, shadow_days=120, calibration_ok=True)
    assert status.is_open is True
    require_gate1(status)  # must not raise


def test_volume_alone_never_opens_gate1() -> None:
    """★ 200 valid meals but hypo recall below baseline ⇒ STILL CLOSED. The model must
    EARN patient visibility; it is not granted by row count."""
    below = gate1_status(valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50,
                         is_promoted=True, shadow_days=120, calibration_ok=True)
    assert below.is_open is False
    with pytest.raises(GateNotPassed):
        require_gate1(below)
    # a tie does not open it either — the model must strictly beat the baseline
    tie = gate1_status(valid_meals=200, model_hypo_recall=0.50, baseline_hypo_recall=0.50,
                       is_promoted=True, shadow_days=120, calibration_ok=True)
    assert tie.is_open is False


# --- live, not cached (ADR-7) -----------------------------------------------


def test_gate1_is_live_not_cached() -> None:
    """★ The gate result flips when the live input flips, within one process — no memo.
    A cached "open" is a silent safety failure (ADR-7)."""
    closed = gate1_status(valid_meals=10, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                          is_promoted=True, shadow_days=120, calibration_ok=True)
    assert closed.is_open is False
    reopened = gate1_status(valid_meals=200, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                            is_promoted=True, shadow_days=120, calibration_ok=True)
    assert reopened.is_open is True
    # and back again, same process — no memoisation anywhere
    assert gate1_status(
        valid_meals=10, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
        is_promoted=True, shadow_days=120, calibration_ok=True,
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


# --- S-1006 [SAFETY]: promotion is the LAST condition, never a bypass --------


def test_metrics_alone_do_not_open_gate1_without_promotion() -> None:
    """★ THE CASE THE SHIPPED CODE GOT WRONG.

    Volume ✓ and beats-baseline ✓ and **not promoted** ⇒ CLOSED. Before S-1006 this
    combination opened Gate 1, so she would have started seeing model output the moment
    hypo recall crossed the baseline — with no human deciding that she should.
    """
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=False, shadow_days=120, calibration_ok=True,
    )
    assert status.is_open is False
    assert status.meets_volume is True
    assert status.beats_baseline is True
    assert status.is_promoted is False
    with pytest.raises(GateNotPassed):
        require_gate1(status)


def test_promotion_alone_is_never_sufficient() -> None:
    """★ Promotion is the LAST condition, not a way around the others. A human saying yes
    does not conjure 150 meals or a model that beats the baseline."""
    too_few = gate1_status(
        valid_meals=149, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert too_few.is_open is False

    not_better = gate1_status(
        valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert not_better.is_open is False

    tie = gate1_status(
        valid_meals=200, model_hypo_recall=0.50, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert tie.is_open is False


def test_all_conditions_together_open_gate1() -> None:
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert status.is_open is True
    require_gate1(status)  # must not raise


def test_is_promoted_is_required_not_defaulted() -> None:
    """★ Pins that a future refactor cannot re-introduce a default and quietly restore the
    old behaviour. A default is a decision made once, for every future call site."""
    with pytest.raises(TypeError):
        gate1_status(  # type: ignore[call-arg]
            valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
            shadow_days=120, calibration_ok=True,
        )


# --- S-1007 [SAFETY]: the 90-day shadow clock (REQ-048) ----------------------


def test_89_shadow_days_keeps_gate1_closed_and_90_opens_it() -> None:
    """★ The boundary, exactly. REQ-048 has existed since the PRD and was enforced
    nowhere: every other condition could hold on day 3 and she would have been shown
    model output. 90 days of *predicting before knowing* is the only evidence that
    separates a model that generalises from one that memorised a retrospective split.
    """
    day89 = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=89, calibration_ok=True,
    )
    assert day89.is_open is False
    assert day89.meets_shadow_period is False
    assert day89.shadow_days == 89
    # every OTHER condition is satisfied — the shadow clock is the only thing holding it
    assert day89.meets_volume is True
    assert day89.beats_baseline is True
    assert day89.is_promoted is True
    with pytest.raises(GateNotPassed):
        require_gate1(day89)

    day90 = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=90, calibration_ok=True,
    )
    assert day90.is_open is True
    assert day90.meets_shadow_period is True
    require_gate1(day90)  # must not raise


def test_a_long_shadow_never_substitutes_for_the_other_conditions() -> None:
    """★ Time is not evidence. Waiting 500 days does not conjure 150 meals, does not
    make the model beat the baseline, and is not a human deciding she may see it.
    The shadow clock JOINS the other conditions; it never stands in for one.
    """
    too_few = gate1_status(
        valid_meals=149, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=500, calibration_ok=True,
    )
    assert too_few.is_open is False and too_few.meets_shadow_period is True

    not_better = gate1_status(
        valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=500, calibration_ok=True,
    )
    assert not_better.is_open is False and not_better.meets_shadow_period is True

    unpromoted = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=False, shadow_days=500, calibration_ok=True,
    )
    assert unpromoted.is_open is False and unpromoted.meets_shadow_period is True


def test_shadow_days_is_required_not_defaulted() -> None:
    """★ Same reasoning as `is_promoted` (S-1006): a default is a decision made once, by
    this function, on behalf of every future call site — and it would let a caller omit
    the question and still compile. Omission must be a type error, not a silent zero."""
    with pytest.raises(TypeError):
        gate1_status(  # type: ignore[call-arg]
            valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
            is_promoted=True, calibration_ok=True,
        )


def test_zero_and_negative_shadow_days_keep_gate1_closed() -> None:
    """Day one, and a clock that has gone backwards. Both resolve to *not yet*."""
    for days in (0, 1, -7):
        status = gate1_status(
            valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
            is_promoted=True, shadow_days=days, calibration_ok=True,
        )
        assert status.is_open is False, f"gate opened at shadow_days={days}"
        assert status.meets_shadow_period is False


def test_gate1_status_reports_the_countdown_for_the_dashboard() -> None:
    """The operator needs "day 61 of 90" rather than a bare "blocked" — a gate whose
    remaining distance is invisible invites someone to go looking for a bypass."""
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=61, calibration_ok=True,
    )
    assert status.shadow_days == 61
    assert SHADOW_MIN_DAYS == 90
    assert SHADOW_MIN_DAYS - status.shadow_days == 29


def test_no_env_var_shortens_the_shadow_period(monkeypatch: pytest.MonkeyPatch) -> None:
    """No bypass exists — not by config flag, not by env var (03 §3)."""
    for var in ("SHADOW_DAYS", "SHADOW_MIN_DAYS", "SKIP_SHADOW", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "0")
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=10, calibration_ok=True,
    )
    assert status.is_open is False


def test_no_env_var_promotes(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PROMOTE", "AUTO_PROMOTE", "IS_PROMOTED", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=False, shadow_days=120, calibration_ok=True,
    )
    assert status.is_open is False


# --- S-1012 [SAFETY]: the fifth condition — honest percentages (OQ-9, DL-042) ---


def test_dishonest_percentages_alone_keep_gate1_closed() -> None:
    """★ Everything earned EXCEPT calibration ⇒ CLOSED.

    A model can rank meals correctly and still be badly wrong about the magnitudes —
    saying 30% when the truth is 60%. She cannot feel a low, so the number IS the
    warning. The other three automatic conditions and promotion are asserted true so
    this test can only pass for the calibration reason.
    """
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=False,
    )
    assert status.is_open is False
    assert status.calibration_ok is False
    assert status.meets_volume is True
    assert status.beats_baseline is True
    assert status.meets_shadow_period is True
    assert status.is_promoted is True
    with pytest.raises(GateNotPassed):
        require_gate1(status)


def test_honest_percentages_never_substitute_for_the_others() -> None:
    """★ Being truthful about the numbers is not the same as being useful. A perfectly
    calibrated model that catches no more lows than the arithmetic she already does has
    earned nothing."""
    too_few = gate1_status(
        valid_meals=149, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert too_few.is_open is False

    not_better = gate1_status(
        valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert not_better.is_open is False

    too_soon = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=89, calibration_ok=True,
    )
    assert too_soon.is_open is False

    unpromoted = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=False, shadow_days=120, calibration_ok=True,
    )
    assert unpromoted.is_open is False


def test_calibration_ok_is_required_not_defaulted() -> None:
    """★ Third time this reasoning applies (is_promoted S-1006, shadow_days S-1007). A
    default is a decision made once, by this function, for every future call site — and
    it lets a caller omit the question and still compile."""
    with pytest.raises(TypeError):
        gate1_status(  # type: ignore[call-arg]
            valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
            is_promoted=True, shadow_days=120,
        )


def test_all_five_conditions_are_required_together() -> None:
    """★ The spec (03 §3) lists FIVE. Each one alone, held false, shuts the gate.

    This is the test that would have caught DL-041 — a spec condition that was never
    written into the signature at all, and so could never fail.
    """
    earned = dict(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=True,
    )
    assert gate1_status(**earned).is_open is True  # type: ignore[arg-type]

    for broken in (
        {"valid_meals": 149},
        {"model_hypo_recall": 0.50},      # a tie is not beating it
        {"shadow_days": 89},
        {"is_promoted": False},
        {"calibration_ok": False},
    ):
        status = gate1_status(**{**earned, **broken})  # type: ignore[arg-type]
        assert status.is_open is False, f"gate opened with {broken} unmet"


def test_no_env_var_declares_the_percentages_honest(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("CALIBRATION_OK", "SKIP_CALIBRATION", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50,
        is_promoted=True, shadow_days=120, calibration_ok=False,
    )
    assert status.is_open is False
