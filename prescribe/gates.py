"""Gate enforcement — the gatekeeper (S-703, REQ-040, INV-2, ADR-7).

Gate 1 decides whether she ever *sees* a model output (INV-2). It is earned from **live
data on every call** — never a row count alone, never a cached "yes". The gate *status* is
application logic here; the raising invariant lives (only) in ``core/safety.py``.

**Gate 2 / INV-1 is retired** (S-1011, DL-035): the clinician-confirmed-ICR gate on the
prescriptive module was removed at the operator's direction. The ICR is now an ordinary
value read from the versioned ``patient_profile``, and ``prescribe.bolus`` raises a plain
``ValueError`` when it is missing or non-positive. Nothing here gates a dose any more.

These are pure functions of their live arguments: no module-level flag, no ``lru_cache``,
no stored boolean. Each call recomputes from the inputs the caller reads fresh from the
DB/metrics, so a stale "open" can never persist (ADR-7). Every gate **fails closed**.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.safety import inv2_patient_output_requires_gate1

# Gate 1's volume precondition (03 §) — necessary, NEVER sufficient. Kept consistent with
# data.adherence.GATE1_VALID_MEALS (asserted by a test).
GATE1_MIN_VALID_MEALS = 150

# REQ-048 — "shadow mode ≥ 90 days before patient-visible output". Named and traced
# deliberately: `90` as a literal inside a condition invites a future reader to tune it.
# Changing this number is changing a requirement, which is an escalation, not a code change.
SHADOW_MIN_DAYS = 90


@dataclass(frozen=True)
class Gate1Status:
    """Gate 1 (patient-visible output). Open only when **all four** preconditions hold:
    volume, beats-baseline, a long-enough shadow period, and deliberate promotion."""

    is_open: bool
    valid_meals: int
    meets_volume: bool
    beats_baseline: bool
    is_promoted: bool
    shadow_days: int
    meets_shadow_period: bool
    model_hypo_recall: float
    baseline_hypo_recall: float


def gate1_status(
    *,
    valid_meals: int,
    model_hypo_recall: float,
    baseline_hypo_recall: float,
    is_promoted: bool,
    shadow_days: int,
) -> Gate1Status:
    """Evaluate Gate 1 from live inputs (S-1006/S-1007, REQ-058, REQ-048).

    ``is_open`` iff **all four** hold: ≥ ``GATE1_MIN_VALID_MEALS`` valid meals, the model's
    hypo recall **strictly** beats the clinical baseline, ≥ ``SHADOW_MIN_DAYS`` days of
    shadow-mode operation, **and the operator has promoted the model on purpose**. Volume
    alone never opens it; a tie does not either; a long shadow period is not evidence of
    quality; and good metrics are a *precondition*, never permission (`07 §Retraining` —
    "Promotion is manual").

    ``is_promoted`` and ``shadow_days`` are **required, not defaulted**. A default would be a
    decision made once, by this function, on behalf of every future call site — and a caller
    could then omit the question entirely and still compile. Requiring them turns a silent
    omission into a type error. Both are read live: ``ModelArtifact.is_promoted`` via
    ``data.repositories.get_promoted_artifact``, and the shadow count via
    ``data.repositories.shadow_days`` — which derives it from ``prediction_log`` rather than
    reading a stored flag. Both fail closed.
    """
    meets_volume = valid_meals >= GATE1_MIN_VALID_MEALS
    beats_baseline = model_hypo_recall > baseline_hypo_recall
    meets_shadow_period = shadow_days >= SHADOW_MIN_DAYS
    return Gate1Status(
        is_open=meets_volume and beats_baseline and meets_shadow_period and is_promoted,
        valid_meals=valid_meals,
        meets_volume=meets_volume,
        beats_baseline=beats_baseline,
        is_promoted=is_promoted,
        shadow_days=shadow_days,
        meets_shadow_period=meets_shadow_period,
        model_hypo_recall=model_hypo_recall,
        baseline_hypo_recall=baseline_hypo_recall,
    )


def require_gate1(status: Gate1Status) -> None:
    """Enforce Gate 1 (INV-2): raise ``GateNotPassed`` unless patient output is allowed."""
    inv2_patient_output_requires_gate1(status.is_open)

