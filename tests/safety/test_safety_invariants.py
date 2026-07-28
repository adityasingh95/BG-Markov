"""S-104 [SAFETY] — INV-1..9 behaviour (SDET, written RED first).

Positive AND negative per invariant, boundary cases, the exception hierarchy,
and the no-bypass guarantee. These are adversarial: assume a future refactor
tries to weaken them.
"""

from __future__ import annotations

import inspect

import pytest

from core import safety
from core.safety import GateNotPassed, SafetyViolation

# --- Exception hierarchy ---------------------------------------------------


def test_gatenotpassed_is_a_safetyviolation() -> None:
    assert issubclass(GateNotPassed, SafetyViolation)
    assert issubclass(SafetyViolation, Exception)


# --- INV-1: RETIRED (S-1011, DL-035) ---------------------------------------
# Gate 2 / INV-1 was removed at the operator's direction; the ICR is now an
# ordinary profile value and `recommend_bolus` raises a plain ValueError when it
# is missing or <= 0. `GateNotPassed` remains in use by INV-2 (Gate 1).


def test_inv1_is_retired_and_gone() -> None:
    """★ INV-1 must be ABSENT, not merely unused — a dormant gate function is an
    invitation to re-wire it. `GateNotPassed` itself must remain (INV-2 uses it)."""
    assert not hasattr(safety, "inv1_prescriptive_requires_gate2")
    assert issubclass(GateNotPassed, SafetyViolation)


# --- INV-2: no patient output until Gate 1 ---------------------------------


def test_inv2_passes_when_gate1_open() -> None:
    safety.inv2_patient_output_requires_gate1(True)


def test_inv2_blocks_when_gate1_closed() -> None:
    with pytest.raises(GateNotPassed):
        safety.inv2_patient_output_requires_gate1(False)


# --- INV-3: bolus in [0, 15] -----------------------------------------------


@pytest.mark.parametrize("dose", [0.0, 0.1, 7.5, 14.99, 15.0])
def test_inv3_accepts_in_bounds(dose: float) -> None:
    safety.inv3_bolus_within_bounds(dose)


@pytest.mark.parametrize("dose", [-0.01, -1.0, 15.01, 900.0])
def test_inv3_rejects_out_of_bounds(dose: float) -> None:
    with pytest.raises(SafetyViolation):
        safety.inv3_bolus_within_bounds(dose)


def test_inv3_ceiling_is_fifteen() -> None:
    assert safety.MAX_BOLUS_U == 15.0


# --- INV-4: no bolus below BG 80 -------------------------------------------


@pytest.mark.parametrize("bg", [80.0, 80.1, 120.0, 250.0])
def test_inv4_allows_at_or_above_floor(bg: float) -> None:
    safety.inv4_bolus_allowed_at_bg(bg)


@pytest.mark.parametrize("bg", [79.99, 74.0, 55.0, 0.0])
def test_inv4_refuses_below_floor(bg: float) -> None:
    with pytest.raises(SafetyViolation):
        safety.inv4_bolus_allowed_at_bg(bg)


def test_inv4_boundary_80_ok_79_raises() -> None:
    safety.inv4_bolus_allowed_at_bg(80.0)  # boundary is inclusive (08 scenario)
    with pytest.raises(SafetyViolation):
        safety.inv4_bolus_allowed_at_bg(79.0)


# --- INV-5: never recommend reducing fingerstick frequency -----------------


@pytest.mark.parametrize(("cur", "rec"), [(6, 6), (6, 8), (4, 10)])
def test_inv5_allows_same_or_more_monitoring(cur: int, rec: int) -> None:
    safety.inv5_monitoring_not_reduced(cur, rec)


@pytest.mark.parametrize(("cur", "rec"), [(6, 5), (8, 0), (4, 3)])
def test_inv5_refuses_reduced_monitoring(cur: int, rec: int) -> None:
    with pytest.raises(SafetyViolation):
        safety.inv5_monitoring_not_reduced(cur, rec)


# --- INV-6: predicted BG in [20, 600] --------------------------------------


@pytest.mark.parametrize("bg", [20.0, 20.1, 135.0, 599.9, 600.0])
def test_inv6_accepts_in_range(bg: float) -> None:
    safety.inv6_predicted_bg_in_range(bg)


@pytest.mark.parametrize("bg", [19.99, 0.0, 600.01, 620.0])
def test_inv6_rejects_out_of_range(bg: float) -> None:
    with pytest.raises(SafetyViolation):
        safety.inv6_predicted_bg_in_range(bg)


# --- INV-7: rescued excluded from training, retained as hypo events --------


def test_inv7_valid_partition_passes() -> None:
    training = [1, 2, 3, 4]
    rescued = [5, 6]
    hypo = [5, 6, 7]  # rescued present as hypo events; extras allowed
    safety.inv7_rescued_excluded_and_retained(training, hypo, rescued)


def test_inv7_raises_when_rescued_leaks_into_training() -> None:
    # The exact silent-deletion inverse: a rescued meal in the training set.
    with pytest.raises(SafetyViolation):
        safety.inv7_rescued_excluded_and_retained(
            training_meal_ids=[1, 2, 5], hypo_event_ids=[5, 6], rescued_meal_ids=[5, 6]
        )


def test_inv7_raises_when_rescued_dropped_from_hypo_events() -> None:
    # The catastrophic refactor: rescued rows deleted entirely (not retained).
    with pytest.raises(SafetyViolation):
        safety.inv7_rescued_excluded_and_retained(
            training_meal_ids=[1, 2], hypo_event_ids=[6], rescued_meal_ids=[5, 6]
        )


# --- INV-8: beta_insulin >= 0 ----------------------------------------------


@pytest.mark.parametrize("beta", [0.0, 0.5, 3.0, 100.0])
def test_inv8_accepts_non_negative(beta: float) -> None:
    safety.inv8_beta_insulin_non_negative(beta)


@pytest.mark.parametrize("beta", [-1e-9, -0.5, -10.0])
def test_inv8_rejects_negative(beta: float) -> None:
    with pytest.raises(SafetyViolation):
        safety.inv8_beta_insulin_non_negative(beta)


# --- INV-9: prediction persisted before return -----------------------------


def test_inv9_passes_with_a_persisted_id() -> None:
    safety.inv9_prediction_persisted(42)


def test_inv9_raises_when_not_persisted() -> None:
    with pytest.raises(SafetyViolation):
        safety.inv9_prediction_persisted(None)


# --- No bypass -------------------------------------------------------------

_INVARIANTS = [
    safety.inv2_patient_output_requires_gate1,
    safety.inv3_bolus_within_bounds,
    safety.inv4_bolus_allowed_at_bg,
    safety.inv5_monitoring_not_reduced,
    safety.inv6_predicted_bg_in_range,
    safety.inv7_rescued_excluded_and_retained,
    safety.inv8_beta_insulin_non_negative,
    safety.inv9_prediction_persisted,
]

_BYPASS_WORDS = {"force", "skip", "bypass", "override", "disable", "enable", "unsafe", "debug"}


@pytest.mark.parametrize("fn", _INVARIANTS)
def test_no_invariant_exposes_a_bypass_parameter(fn: object) -> None:
    params = {p.lower() for p in inspect.signature(fn).parameters}  # type: ignore[arg-type]
    assert not (params & _BYPASS_WORDS), f"{fn.__name__} exposes a bypass param"  # type: ignore[attr-defined]


def test_env_vars_cannot_bypass_a_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("BYPASS_SAFETY", "DEBUG", "SKIP_GATES", "UNSAFE", "DISABLE_INV2"):
        monkeypatch.setenv(var, "1")
    with pytest.raises(GateNotPassed):
        safety.inv2_patient_output_requires_gate1(False)
