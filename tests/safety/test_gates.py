"""S-703 [SAFETY] — gate enforcement (SDET, written RED first).

The gates are why the system is safe to build: Gate 1 decides whether she ever SEES a
model output (INV-2); Gate 2 decides whether the machine is ever allowed near a DOSE
(INV-1). Both must be earned from live data every call — never a row count alone, never a
cached "yes", never a flag anyone can flip. These tests are adversarial: assume a future
refactor (or a 2am EPIC-9 shortcut) will try to weaken them. See docs/stories/S-703.md.

RED: `prescribe.gates` / `prescribe.bolus` do not exist yet.
"""

from __future__ import annotations

import inspect

import pytest

from core.safety import GateNotPassed, SafetyViolation
from prescribe.bolus import recommend_bolus
from prescribe.gates import (
    GATE1_MIN_VALID_MEALS,
    gate1_status,
    gate2_status,
    require_gate1,
    require_gate2,
)

# --- Gate 2 / prescriptive (INV-1) ------------------------------------------

# Full clinical inputs for the S-901 calculator; ``icr`` is supplied per-test.
_DOSE = dict(isf=30.0, carbs_g=60.0, current_bg=150.0, target_bg=135.0, iob=0.0)


def test_null_icr_blocks_bolus_recommendation() -> None:
    """★ icr is null ⇒ recommend_bolus() raises GateNotPassed (INV-1)."""
    with pytest.raises(GateNotPassed):
        recommend_bolus(icr=None, **_DOSE)


def test_gate_not_passed_is_a_safety_violation() -> None:
    assert issubclass(GateNotPassed, SafetyViolation)
    with pytest.raises(SafetyViolation):
        recommend_bolus(icr=None, **_DOSE)


def test_no_bypass_parameter_exists() -> None:
    """★ No fixture/flag lever: recommend_bolus has no override-style parameter."""
    params = set(inspect.signature(recommend_bolus).parameters)
    for lever in ("force", "override", "skip_gate", "bypass", "gate2_passed", "allow"):
        assert lever not in params, f"recommend_bolus must not expose a '{lever}' bypass"


def test_no_env_var_can_bypass_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """★ Setting bypass-looking environment variables does NOT open the gate."""
    for var in ("BGMARKOV_FORCE_BOLUS", "FORCE_BOLUS", "SKIP_GATE", "GATE2_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    with pytest.raises(GateNotPassed):
        recommend_bolus(icr=None, **_DOSE)


def test_confirmed_icr_passes_gate2_and_computes_a_dose() -> None:
    """With a confirmed ICR the gate OPENS and recommend_bolus computes a real dose
    (S-901), NOT GateNotPassed and no longer the EPIC-9 placeholder."""
    assert gate2_status(icr=9.0).is_open is True
    rec = recommend_bolus(icr=9.0, **_DOSE)
    assert rec.total_units >= 0.0


def test_gate2_closed_on_null_or_nonpositive_icr() -> None:
    assert gate2_status(icr=None).is_open is False
    assert gate2_status(icr=0.0).is_open is False
    with pytest.raises(GateNotPassed):
        require_gate2(gate2_status(icr=None))


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


def test_gates_are_live_not_cached() -> None:
    """The gate result flips when the live input flips, within one process — no memo."""
    assert gate2_status(icr=None).is_open is False
    assert gate2_status(icr=9.0).is_open is True
    # recommend_bolus reflects the live icr on each call
    with pytest.raises(GateNotPassed):
        recommend_bolus(icr=None, **_DOSE)
    assert recommend_bolus(icr=9.0, **_DOSE).total_units >= 0.0  # gate open ⇒ computes


def test_gate1_constant_matches_adherence() -> None:
    from data.adherence import GATE1_VALID_MEALS

    assert GATE1_MIN_VALID_MEALS == GATE1_VALID_MEALS == 150
