"""INV-1..9 — the single, dependency-free source of every safety invariant.

Why this module is the way it is (CLAUDE.md "Safety invariants"):

1. **One named function per invariant, one file.** Every invariant is defined
   exactly once, here. No other module re-implements one (a grep/AST test in
   ``tests/safety/`` fails the build if it does).
2. **Raise ``SafetyViolation`` — never ``assert``.** ``python -O`` strips
   ``assert``, which would silently disable every check in production. A static
   AST test proves no ``assert`` exists here; a behavioural test runs a negative
   case under ``python -O`` and confirms it still raises.
3. **Zero internal project imports (ADR-6).** This module imports only
   stdlib/typing. Nothing from ``core/features/models/...`` may be imported, so
   no import cycle can be introduced that lets a downstream module shadow or
   weaken an invariant.
4. **No bypass.** Each function takes only the data it checks — no config flag,
   no env var, no ``force=`` kwarg. There is no argument that disables a check.

Callers pass primitives (bools/floats/ids), never domain objects, so ADR-6
holds. Gate booleans (INV-1/2) must be evaluated from **live** data on every
call by the caller (ADR-7); this module never caches them.
"""

from __future__ import annotations

from collections.abc import Iterable

# --- The single source of every safety threshold ---------------------------
MAX_BOLUS_U: float = 15.0
BOLUS_BG_FLOOR: float = 80.0
PREDICTED_BG_MIN: float = 20.0
PREDICTED_BG_MAX: float = 600.0


class SafetyViolation(Exception):
    """A safety invariant was violated. Loud, never swallowed."""


class GateNotPassed(SafetyViolation):
    """A gated feature was reached before its gate opened (INV-1, INV-2).

    Maps to ``403 GATE_NOT_PASSED`` at the API boundary.
    """


def inv1_prescriptive_requires_gate2(gate2_passed: bool) -> None:
    """INV-1 — the prescriptive module is disabled until Gate 2 passes.

    ``gate2_passed`` must be evaluated from live data on every call (ADR-7).
    """
    if not gate2_passed:
        raise GateNotPassed(
            "INV-1: prescriptive/bolus module is disabled until Gate 2 passes"
        )


def inv2_patient_output_requires_gate1(gate1_passed: bool) -> None:
    """INV-2 — no patient-visible model output until Gate 1 passes."""
    if not gate1_passed:
        raise GateNotPassed(
            "INV-2: no patient-visible model output until Gate 1 passes"
        )


def inv3_bolus_within_bounds(dose_u: float) -> None:
    """INV-3 — a recommended bolus is never negative and never exceeds 15 U.

    This is the final bound check on a value about to be returned. Capping and
    the *implausible-input* flag are the caller's responsibility (S-901); if a
    bug lets an unclamped value through, this raises rather than dose it.
    """
    if dose_u < 0.0:
        raise SafetyViolation(f"INV-3: recommended bolus is negative ({dose_u} U)")
    if dose_u > MAX_BOLUS_U:
        raise SafetyViolation(
            f"INV-3: recommended bolus {dose_u} U exceeds MAX_BOLUS_U ({MAX_BOLUS_U} U)"
        )


def inv4_bolus_allowed_at_bg(current_bg: float) -> None:
    """INV-4 — no bolus is recommended when ``current_bg < 80``.

    The boundary is inclusive: BG 80 is allowed, BG 79 is refused
    (``08`` scenario). The caller translates this into ``BG_TOO_LOW_FOR_BOLUS``.
    """
    if current_bg < BOLUS_BG_FLOOR:
        raise SafetyViolation(
            f"INV-4: BG {current_bg} < {BOLUS_BG_FLOOR}; treat the low first, no dose"
        )


def inv5_monitoring_not_reduced(
    current_tests_per_day: int, recommended_tests_per_day: int
) -> None:
    """INV-5 — the system never recommends reducing fingerstick frequency."""
    if recommended_tests_per_day < current_tests_per_day:
        raise SafetyViolation(
            "INV-5: recommending reduced fingerstick frequency "
            f"({current_tests_per_day} -> {recommended_tests_per_day}/day) is forbidden"
        )


def inv6_predicted_bg_in_range(predicted_bg: float) -> None:
    """INV-6 — a predicted BG outside [20, 600] mg/dL is a hard error."""
    if predicted_bg < PREDICTED_BG_MIN or predicted_bg > PREDICTED_BG_MAX:
        raise SafetyViolation(
            f"INV-6: predicted BG {predicted_bg} outside "
            f"[{PREDICTED_BG_MIN}, {PREDICTED_BG_MAX}] mg/dL"
        )


def inv7_rescued_excluded_and_retained(
    training_meal_ids: Iterable[int],
    hypo_event_ids: Iterable[int],
    rescued_meal_ids: Iterable[int],
) -> None:
    """INV-7 — hypo-rescued meals are excluded from the outcome-regression
    training set but retained as hypo events.

    Raises if a rescued meal leaked into training (contaminates the outcome
    regression) OR if a rescued meal is missing from the hypo events (the
    catastrophic refactor that silently deletes the lows the system exists to
    predict).
    """
    training = set(training_meal_ids)
    hypo = set(hypo_event_ids)
    rescued = set(rescued_meal_ids)

    leaked = rescued & training
    if leaked:
        raise SafetyViolation(
            f"INV-7: rescued meals {sorted(leaked)} leaked into the training set"
        )
    dropped = rescued - hypo
    if dropped:
        raise SafetyViolation(
            f"INV-7: rescued meals {sorted(dropped)} were not retained as hypo events"
        )


def inv8_beta_insulin_non_negative(beta_insulin: float) -> None:
    """INV-8 — ``β_insulin`` is constrained ≥ 0 in every fitted model.

    Insulin cannot raise glucose; a negative coefficient is confounding by
    indication (07 §7). The unconstrained-fit warning is the caller's job
    (S-503); this enforces the sign of the value that is actually used.
    """
    if beta_insulin < 0.0:
        raise SafetyViolation(
            f"INV-8: beta_insulin {beta_insulin} < 0 (insulin cannot raise glucose)"
        )


def inv9_prediction_persisted(prediction_id: int | None) -> None:
    """INV-9 — every prediction is written to ``prediction_log`` before it is
    returned.

    The caller persists the prediction, then passes the resulting row id here
    before returning it. ``None`` means the write did not produce a row, so no
    prediction may be returned.
    """
    if prediction_id is None:
        raise SafetyViolation(
            "INV-9: prediction was not persisted before return; refusing to return it"
        )
