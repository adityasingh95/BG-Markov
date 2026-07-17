"""The patient risk readout — the first patient-reachable INV-2 surface (S-804, REQ-040).

This is the first thing she actually sees, possibly while low. It leads with the one
question that matters — is a hypo likely? — in plain language, never colour alone; a
refusal (or a gated/suppressed state) is a rendered answer, not a blank; it **never** tells
her to dose (that is the prescriptive module, behind Gate 2); and it does not exist at all
until Gate 1 is earned, with no lever to force it open.

Imports ``prescribe.gates`` (INV-2) and ``models.guardrails`` (the guarded result). It
carries no ``advice``/``dose``/``bolus`` field — by construction a risk screen cannot
carry a dosing instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from models.guardrails import GuardedPrediction
from prescribe.gates import Gate1Status, require_gate1

# States 1–2 are BG < 80 (hypo). Kept local so this patient-facing module does not import
# the heavy model stack; matches models.state's boundaries and models.ordinal.HYPO_STATES.
_HYPO_STATES = frozenset({1, 2})


class ReadoutKind(StrEnum):
    PREDICTION = "prediction"
    REFUSAL = "refusal"
    CONFLICT = "conflict"
    BASELINE_FALLBACK = "baseline_fallback"


@dataclass(frozen=True)
class PatientReadout:
    """What the patient sees. ``hypo_risk`` and ``severity`` are **text** labels (never
    colour-only). There is deliberately no ``advice``/``dose``/``bolus`` field."""

    kind: ReadoutKind
    headline: str          # always hypo-risk-first
    hypo_risk: str         # "elevated" | "reduced" | "in_range" | "unknown"
    severity: str          # "high" | "moderate" | "low" | "none" | "unknown"
    body: str              # plain language
    state: int | None
    model_state: int | None
    baseline_state: int | None


def _hypo_framing(state: int) -> tuple[str, str]:
    """(hypo_risk, severity) text labels for a clinical state — hypo framing first."""
    if state in _HYPO_STATES:
        return "elevated", "high"
    if state == 3:
        return "in_range", "low"
    return "reduced", "moderate"  # states 4–5 are hyper, not hypo


def _headline(hypo_risk: str) -> str:
    return f"Hypoglycaemia risk: {hypo_risk.replace('_', ' ')}"


def build_patient_readout(
    *,
    gate1: Gate1Status,
    guarded: GuardedPrediction,
    kill_switch_tripped: bool,
    baseline_state: int,
) -> PatientReadout:
    """Assemble the patient risk readout — **behind Gate 1, with no bypass**.

    Raises ``GateNotPassed`` if Gate 1 is closed (INV-2). A tripped kill switch shows the
    baseline; a refusal or conflict is a rendered state; otherwise the predicted state's
    hypo risk is the headline. Never carries a dose.
    """
    # INV-2, first line, no bypass: no patient-visible output before Gate 1.
    require_gate1(gate1)

    # Kill switch tripped ⇒ ML suppressed, show the baseline (fail-safe).
    if kill_switch_tripped:
        hypo_risk, severity = _hypo_framing(baseline_state)
        return PatientReadout(
            kind=ReadoutKind.BASELINE_FALLBACK,
            headline=_headline(hypo_risk),
            hypo_risk=hypo_risk,
            severity=severity,
            body=(
                "The prediction model is paused; showing the baseline estimate. "
                f"Baseline state: {baseline_state}."
            ),
            state=None,
            model_state=guarded.model_state,
            baseline_state=baseline_state,
        )

    # A refusal is a rendered state, never a blank.
    if guarded.refused:
        return PatientReadout(
            kind=ReadoutKind.REFUSAL,
            headline=_headline("unknown"),
            hypo_risk="unknown",
            severity="unknown",
            body=guarded.message,
            state=None,
            model_state=guarded.model_state,
            baseline_state=guarded.baseline_state,
        )

    # A conflict shows both and picks no winner; frame hypo risk from the MORE cautious
    # (lower / closer-to-hypo) of the two states.
    if guarded.conflict:
        cautious = min(guarded.model_state, guarded.baseline_state)
        hypo_risk, severity = _hypo_framing(cautious)
        return PatientReadout(
            kind=ReadoutKind.CONFLICT,
            headline=_headline(hypo_risk),
            hypo_risk=hypo_risk,
            severity=severity,
            body=(
                f"The two methods disagree — model: State {guarded.model_state}, "
                f"baseline: State {guarded.baseline_state}. Both are shown; no single "
                "answer is chosen."
            ),
            state=None,
            model_state=guarded.model_state,
            baseline_state=guarded.baseline_state,
        )

    # A confident, agreeing prediction — for this path guarded.state == model_state.
    hypo_risk, severity = _hypo_framing(guarded.model_state)
    return PatientReadout(
        kind=ReadoutKind.PREDICTION,
        headline=_headline(hypo_risk),
        hypo_risk=hypo_risk,
        severity=severity,
        body=f"Predicted state: {guarded.model_state}.",
        state=guarded.model_state,
        model_state=guarded.model_state,
        baseline_state=guarded.baseline_state,
    )
