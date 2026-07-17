"""Gate enforcement — the gatekeeper (S-703, REQ-040/041, INV-1/INV-2, ADR-7).

Gate 1 decides whether she ever *sees* a model output (INV-2); Gate 2 decides whether the
machine is ever allowed near a *dose* (INV-1). Both are earned from **live data on every
call** — never a row count alone, never a cached "yes". The gate *status* is application
logic here; the raising invariants live (only) in ``core/safety.py``.

These are pure functions of their live arguments: no module-level flag, no ``lru_cache``,
no stored boolean. Each call recomputes from the inputs the caller reads fresh from the
DB/metrics, so a stale "open" can never persist (ADR-7). Every gate **fails closed**.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.safety import (
    inv1_prescriptive_requires_gate2,
    inv2_patient_output_requires_gate1,
)

# Gate 1's volume precondition (03 §) — necessary, NEVER sufficient. Kept consistent with
# data.adherence.GATE1_VALID_MEALS (asserted by a test).
GATE1_MIN_VALID_MEALS = 150


@dataclass(frozen=True)
class Gate1Status:
    """Gate 1 (patient-visible output). Open only when the volume floor is met **and**
    the model beats the clinical baseline on hypo recall."""

    is_open: bool
    valid_meals: int
    meets_volume: bool
    beats_baseline: bool
    model_hypo_recall: float
    baseline_hypo_recall: float


@dataclass(frozen=True)
class Gate2Status:
    """Gate 2 (prescriptive/bolus module). Open only with a confirmed ICR."""

    is_open: bool
    has_confirmed_icr: bool


def gate1_status(
    *, valid_meals: int, model_hypo_recall: float, baseline_hypo_recall: float
) -> Gate1Status:
    """Evaluate Gate 1 from live inputs. ``is_open`` iff there are ≥
    ``GATE1_MIN_VALID_MEALS`` valid meals **and** the model's hypo recall **strictly**
    beats the clinical baseline. Volume alone never opens it; a tie does not either."""
    meets_volume = valid_meals >= GATE1_MIN_VALID_MEALS
    beats_baseline = model_hypo_recall > baseline_hypo_recall
    return Gate1Status(
        is_open=meets_volume and beats_baseline,
        valid_meals=valid_meals,
        meets_volume=meets_volume,
        beats_baseline=beats_baseline,
        model_hypo_recall=model_hypo_recall,
        baseline_hypo_recall=baseline_hypo_recall,
    )


def gate2_status(*, icr: float | None) -> Gate2Status:
    """Evaluate Gate 2 from the live ICR. ``is_open`` iff a positive, confirmed ICR
    exists — ``icr = null`` (or non-positive) keeps the prescriptive module disabled."""
    confirmed = icr is not None and icr > 0.0
    return Gate2Status(is_open=confirmed, has_confirmed_icr=confirmed)


def require_gate1(status: Gate1Status) -> None:
    """Enforce Gate 1 (INV-2): raise ``GateNotPassed`` unless patient output is allowed."""
    inv2_patient_output_requires_gate1(status.is_open)


def require_gate2(status: Gate2Status) -> None:
    """Enforce Gate 2 (INV-1): raise ``GateNotPassed`` unless the prescriptive module is
    allowed."""
    inv1_prescriptive_requires_gate2(status.is_open)
