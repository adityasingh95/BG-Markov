"""S-804 [SAFETY] — the patient risk readout (SDET, written RED first).

This is the first thing she actually sees, possibly while low. It leads with the one
question that matters (is a hypo likely?), a refusal is a rendered answer not a blank, it
NEVER tells her to dose, and it does not exist until Gate 1 is earned — with no lever to
force it open. See docs/stories/S-804.md.

RED: `prescribe.readout` does not exist yet.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from core.safety import GateNotPassed
from models.guardrails import guard_prediction
from prescribe.gates import gate1_status
from prescribe.readout import (
    PatientReadout,
    ReadoutKind,
    build_patient_readout,
)

_STATES = (1, 2, 3, 4, 5)
_OPEN = gate1_status(valid_meals=200, model_hypo_recall=0.9, baseline_hypo_recall=0.5)
_CLOSED_149 = gate1_status(valid_meals=149, model_hypo_recall=0.9, baseline_hypo_recall=0.5)


def _guarded(state: int, *, peak: float = 0.8, baseline_state: int | None = None,
             in_distribution: bool = True, n_nearby_train: int = 50):  # type: ignore[no-untyped-def]
    p = np.full(5, (1.0 - peak) / 4.0)
    p[state - 1] = peak
    return guard_prediction(
        proba=p, states=_STATES, predicted_bg=120.0,
        baseline_state=state if baseline_state is None else baseline_state,
        in_distribution=in_distribution, n_nearby_train=n_nearby_train,
    )


def _readout(**overrides: object) -> PatientReadout:
    kwargs: dict[str, object] = dict(
        gate1=_OPEN, guarded=_guarded(3), kill_switch_tripped=False, baseline_state=3
    )
    kwargs.update(overrides)
    return build_patient_readout(**kwargs)  # type: ignore[arg-type]


def test_gate1_closed_at_149_makes_the_surface_raise() -> None:
    """★ INV-2: no patient-visible output before Gate 1 — 149 valid meals raises."""
    with pytest.raises(GateNotPassed):
        _readout(gate1=_CLOSED_149)


def test_no_bypass_parameter_exists() -> None:
    """★ No lever forces the surface open."""
    params = set(inspect.signature(build_patient_readout).parameters)
    for lever in ("force", "override", "skip_gate", "bypass", "gate1_passed"):
        assert lever not in params


def test_no_env_var_opens_the_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("BGMARKOV_FORCE_READOUT", "SKIP_GATE", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    with pytest.raises(GateNotPassed):
        _readout(gate1=_CLOSED_149)


def test_hypo_risk_is_the_headline() -> None:
    low = _readout(guarded=_guarded(2))
    assert low.hypo_risk == "elevated"
    assert low.severity == "high"
    assert "hypo" in low.headline.lower() or "low" in low.headline.lower()

    in_range = _readout(guarded=_guarded(3))
    assert in_range.hypo_risk == "in_range"
    assert "hypo" in in_range.headline.lower() or "low" in in_range.headline.lower()


def test_high_state_frames_hypo_risk_as_reduced() -> None:
    """A confident hyper prediction (State 5) still leads with hypo risk — reduced."""
    high = _readout(guarded=_guarded(5, baseline_state=5))  # agree, no conflict
    assert high.kind is ReadoutKind.PREDICTION
    assert high.state == 5
    assert high.hypo_risk == "reduced"
    assert high.severity == "moderate"
    assert "hypo" in high.headline.lower()


def test_refusal_is_a_rendered_state_not_a_blank() -> None:
    refused = _readout(guarded=_guarded(3, in_distribution=False))
    assert refused.kind is ReadoutKind.REFUSAL
    assert refused.state is None
    assert refused.hypo_risk == "unknown"
    assert refused.body.strip() != ""


def test_readout_never_carries_advice() -> None:
    """★ A risk readout can never carry a dosing instruction."""
    r = _readout()
    for banned in ("advice", "dose", "bolus", "units", "recommendation"):
        assert not hasattr(r, banned), f"readout must not expose '{banned}'"
    # and no dosing directive slips into the free text
    for r2 in (_readout(), _readout(guarded=_guarded(2)), _readout(kill_switch_tripped=True)):
        low = r2.body.lower()
        assert "units" not in low and "inject" not in low
        assert "take insulin" not in low and "give insulin" not in low


def test_kill_switch_shows_the_baseline() -> None:
    r = _readout(kill_switch_tripped=True, baseline_state=2)
    assert r.kind is ReadoutKind.BASELINE_FALLBACK
    assert r.baseline_state == 2
    assert "baseline" in r.body.lower() or "paused" in r.body.lower()


def test_conflict_shows_both_and_picks_no_winner() -> None:
    conflict = _readout(guarded=_guarded(5, baseline_state=3))
    assert conflict.kind is ReadoutKind.CONFLICT
    assert conflict.state is None
    assert conflict.model_state == 5 and conflict.baseline_state == 3


def test_signal_is_textual_not_colour_only() -> None:
    r = _readout(guarded=_guarded(2))
    assert isinstance(r.severity, str) and r.severity != ""
    assert isinstance(r.hypo_risk, str) and r.hypo_risk != ""
