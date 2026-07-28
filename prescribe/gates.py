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


def require_gate1(status: Gate1Status) -> None:
    """Enforce Gate 1 (INV-2): raise ``GateNotPassed`` unless patient output is allowed."""
    inv2_patient_output_requires_gate1(status.is_open)

