"""S-901 [SAFETY] — the bolus calculator (SDET, written RED first).

This is the only place in the system that recommends putting insulin into a person who
cannot feel a low. It uses the clinical formula (no ML), refuses when she is already low,
treats an impossible carb entry as a typo not a lethal dose, and never doses past 15 U or
below 0. ICR 9 / ISF 30 / target 135 are the clinician-confirmed constants (DL-032).
See docs/stories/S-901.md.

RED: `BolusRecommendation` / the new `recommend_bolus` signature do not exist yet.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from core.safety import GateNotPassed, SafetyViolation
from prescribe.bolus import BolusRecommendation, recommend_bolus

_ICR = 9.0
_ISF = 30.0
_TARGET = 135.0


def _dose(carbs_g: float, current_bg: float, iob: float) -> BolusRecommendation:
    return recommend_bolus(
        icr=_ICR, isf=_ISF, carbs_g=carbs_g, current_bg=current_bg,
        target_bg=_TARGET, iob=iob,
    )


# --- INV-4: refuse below BG 80 ----------------------------------------------


def test_inv4_refuses_below_bg_80() -> None:
    """★ BG 79 ⇒ refuse ("treat the low first"); BG 80 ⇒ computes."""
    with pytest.raises(SafetyViolation):
        _dose(carbs_g=60.0, current_bg=79.0, iob=0.0)
    ok = _dose(carbs_g=60.0, current_bg=80.0, iob=0.0)  # boundary allowed
    assert ok.total_units >= 0.0


# --- INV-3: cap + flag, never negative --------------------------------------


def test_inv3_typo_is_capped_and_flagged_not_silently_dosed() -> None:
    """★ carbs_g = 900 (typo for 90) ⇒ capped at 15 U AND flagged implausible — a typo
    must never become a confident lethal dose."""
    rec = _dose(carbs_g=900.0, current_bg=180.0, iob=0.0)
    assert rec.total_units == 15.0
    assert rec.capped is True
    assert rec.implausible_input is True


def test_inv3_negative_computed_dose_returns_zero() -> None:
    """A below-target correction with no carbs ⇒ 0.0, never negative."""
    rec = _dose(carbs_g=0.0, current_bg=90.0, iob=0.0)  # (90-135)/30 = -1.5
    assert rec.total_units == 0.0


# --- INV-1: gate, no bypass -------------------------------------------------


def test_inv1_null_icr_raises_and_has_no_bypass() -> None:
    """★ icr = None ⇒ GateNotPassed; no override-style parameter exists."""
    with pytest.raises(GateNotPassed):
        recommend_bolus(
            icr=None, isf=_ISF, carbs_g=60.0, current_bg=150.0, target_bg=_TARGET, iob=0.0
        )
    params = set(inspect.signature(recommend_bolus).parameters)
    for lever in ("force", "override", "skip_gate", "bypass", "gate2_passed"):
        assert lever not in params


def test_inv1_no_env_var_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("FORCE_BOLUS", "SKIP_GATE", "GATE2_PASSED"):
        monkeypatch.setenv(var, "1")
    with pytest.raises(GateNotPassed):
        recommend_bolus(
            icr=None, isf=_ISF, carbs_g=60.0, current_bg=150.0, target_bg=_TARGET, iob=0.0
        )


# --- golden: 5 hand-computed doses ------------------------------------------


def test_golden_hand_computed_doses() -> None:
    """★ ICR 9, ISF 30, target 135. Five doses, hand-computed to 2 dp."""
    assert _dose(90.0, 180.0, 0.0).total_units == pytest.approx(11.50)  # 10 + 1.5
    assert _dose(45.0, 135.0, 0.0).total_units == pytest.approx(5.00)   # 5 + 0
    assert _dose(60.0, 200.0, 2.0).total_units == pytest.approx(6.83, abs=0.01)  # 6.667+2.167-2
    assert _dose(30.0, 120.0, 0.0).total_units == pytest.approx(2.83, abs=0.01)  # 3.333-0.5
    assert _dose(0.0, 90.0, 0.0).total_units == pytest.approx(0.00)     # max(0, -1.5)


# --- properties -------------------------------------------------------------


def test_dose_is_non_decreasing_in_carbs() -> None:
    prev = -1.0
    for carbs in (0.0, 20.0, 40.0, 60.0, 80.0):
        d = _dose(carbs, 160.0, 0.0).total_units
        assert d >= prev
        prev = d


def test_dose_is_non_increasing_in_iob() -> None:
    prev = 999.0
    for iob in (0.0, 1.0, 2.0, 4.0, 8.0):
        d = _dose(80.0, 200.0, iob).total_units
        assert d <= prev
        prev = d


# --- no ML in the dose path; shown + framed as review -----------------------


def test_no_model_import_in_the_dose_path() -> None:
    """★ The prescriptive path imports nothing from models/ — no ML touches the dose."""
    src = pathlib.Path(inspect.getfile(recommend_bolus)).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("models"):
            raise AssertionError(f"dose path imports from models: {node.module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("models"), alias.name


def test_full_arithmetic_shown_and_framed_as_a_suggestion() -> None:
    rec = _dose(90.0, 180.0, 0.0)
    assert rec.carb_dose == pytest.approx(10.0)
    assert rec.correction_dose == pytest.approx(1.5)
    assert rec.iob_subtracted == pytest.approx(0.0)
    assert rec.arithmetic.strip() != ""            # the working is shown
    assert "review" in rec.framing.lower()         # a suggestion, not an instruction
    assert "units" not in rec.framing.lower() or "review" in rec.framing.lower()
