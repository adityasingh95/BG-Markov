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
    gate1_status,
    require_gate1,
)

# --- Gate 1 / patient output (INV-2) ----------------------------------------


def test_149_valid_meals_keeps_gate1_closed() -> None:
    status = gate1_status(valid_meals=149, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                          is_promoted=True)
    assert status.is_open is False
    with pytest.raises(GateNotPassed):
        require_gate1(status)


def test_150_valid_meals_beating_baseline_opens_gate1() -> None:
    status = gate1_status(valid_meals=150, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                          is_promoted=True)
    assert status.is_open is True
    require_gate1(status)  # must not raise


def test_volume_alone_never_opens_gate1() -> None:
    """★ 200 valid meals but hypo recall below baseline ⇒ STILL CLOSED. The model must
    EARN patient visibility; it is not granted by row count."""
    below = gate1_status(valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50,
                         is_promoted=True)
    assert below.is_open is False
    with pytest.raises(GateNotPassed):
        require_gate1(below)
    # a tie does not open it either — the model must strictly beat the baseline
    tie = gate1_status(valid_meals=200, model_hypo_recall=0.50, baseline_hypo_recall=0.50,
                       is_promoted=True)
    assert tie.is_open is False


# --- live, not cached (ADR-7) -----------------------------------------------


def test_gate1_is_live_not_cached() -> None:
    """★ The gate result flips when the live input flips, within one process — no memo.
    A cached "open" is a silent safety failure (ADR-7)."""
    closed = gate1_status(valid_meals=10, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                          is_promoted=True)
    assert closed.is_open is False
    reopened = gate1_status(valid_meals=200, model_hypo_recall=0.9, baseline_hypo_recall=0.5,
                            is_promoted=True)
    assert reopened.is_open is True
    # and back again, same process — no memoisation anywhere
    assert gate1_status(
        valid_meals=10, model_hypo_recall=0.9, baseline_hypo_recall=0.5, is_promoted=True
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
        is_promoted=False,
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
        valid_meals=149, model_hypo_recall=0.90, baseline_hypo_recall=0.50, is_promoted=True
    )
    assert too_few.is_open is False

    not_better = gate1_status(
        valid_meals=200, model_hypo_recall=0.40, baseline_hypo_recall=0.50, is_promoted=True
    )
    assert not_better.is_open is False

    tie = gate1_status(
        valid_meals=200, model_hypo_recall=0.50, baseline_hypo_recall=0.50, is_promoted=True
    )
    assert tie.is_open is False


def test_all_conditions_together_open_gate1() -> None:
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50, is_promoted=True
    )
    assert status.is_open is True
    require_gate1(status)  # must not raise


def test_is_promoted_is_required_not_defaulted() -> None:
    """★ Pins that a future refactor cannot re-introduce a default and quietly restore the
    old behaviour. A default is a decision made once, for every future call site."""
    with pytest.raises(TypeError):
        gate1_status(  # type: ignore[call-arg]
            valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50
        )


def test_no_env_var_promotes(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PROMOTE", "AUTO_PROMOTE", "IS_PROMOTED", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    status = gate1_status(
        valid_meals=200, model_hypo_recall=0.90, baseline_hypo_recall=0.50, is_promoted=False
    )
    assert status.is_open is False
