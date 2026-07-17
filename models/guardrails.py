"""Output guardrails — refuse rather than guess (S-801, REQ-044/046, INV-6, 07 §10).

A guess is worse than a refusal, and infinitely more dangerous to someone who cannot feel
a low. When the model is out of its depth, the correct output is not a bare state: an
out-of-distribution meal, a thin data region, and an indecisive posterior each **refuse**;
a **baseline conflict** shows both with no winner picked; and a physiologically **absurd**
predicted BG is a **hard error** (INV-6). Never fill the silence with a number.

Pure — imports only ``core.safety`` (for INV-6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt

from core.safety import inv6_predicted_bg_in_range

# A state must EXCEED this probability to be predicted (07 §10, condition 3).
CONFIDENCE_THRESHOLD = 0.40
# Fewer than ~this many nearby training meals ⇒ refuse (condition 2).
SPARSE_MIN_NEIGHBORS = 10
# A baseline/model divergence STRICTLY greater than this many states is a conflict.
_CONFLICT_STATE_GAP = 1


class RefusalReason(StrEnum):
    OUT_OF_DISTRIBUTION = "out_of_distribution"
    SPARSE_REGION = "sparse_region"
    DIFFUSE_POSTERIOR = "diffuse_posterior"


REFUSAL_MESSAGES: dict[RefusalReason, str] = {
    RefusalReason.OUT_OF_DISTRIBUTION: "This meal is unlike anything in the training data.",
    RefusalReason.SPARSE_REGION: "Too few similar meals to predict this one reliably.",
    RefusalReason.DIFFUSE_POSTERIOR: "Not confident enough to predict this one.",
}


@dataclass(frozen=True)
class GuardedPrediction:
    """A prediction after the output guardrails. ``state`` is set only for a confident,
    non-conflicting prediction; every uncertainty path leaves it ``None``."""

    refused: bool
    reason: RefusalReason | None
    state: int | None
    max_confidence: float
    conflict: bool
    model_state: int
    baseline_state: int
    message: str


def _refusal(
    reason: RefusalReason, *, model_state: int, baseline_state: int, max_confidence: float
) -> GuardedPrediction:
    return GuardedPrediction(
        refused=True,
        reason=reason,
        state=None,
        max_confidence=max_confidence,
        conflict=False,
        model_state=model_state,
        baseline_state=baseline_state,
        message=REFUSAL_MESSAGES[reason],
    )


def guard_prediction(
    *,
    proba: npt.ArrayLike,
    states: tuple[int, ...],
    predicted_bg: float,
    baseline_state: int,
    in_distribution: bool,
    n_nearby_train: int,
) -> GuardedPrediction:
    """Apply the five output guardrails (07 §10) to a raw prediction.

    Raises ``SafetyViolation`` (INV-6) when ``predicted_bg`` is physiologically absurd —
    checked **first**, so an impossible number can never be downgraded to a refusal. OOD,
    sparse, and diffuse each return a refusal (`state=None`); a baseline conflict returns
    both states flagged with no winner; otherwise a confident, agreeing state.
    """
    # 5. Physiologically absurd — a HARD ERROR, checked first (INV-6).
    inv6_predicted_bg_in_range(predicted_bg)

    p = np.asarray(proba, dtype=float)
    model_state = int(states[int(np.argmax(p))])
    max_confidence = float(p.max())

    # 1. Out of distribution — refuse.
    if not in_distribution:
        return _refusal(
            RefusalReason.OUT_OF_DISTRIBUTION,
            model_state=model_state,
            baseline_state=baseline_state,
            max_confidence=max_confidence,
        )

    # 2. Sparse region — refuse.
    if n_nearby_train < SPARSE_MIN_NEIGHBORS:
        return _refusal(
            RefusalReason.SPARSE_REGION,
            model_state=model_state,
            baseline_state=baseline_state,
            max_confidence=max_confidence,
        )

    # 3. Diffuse posterior — no state EXCEEDS the threshold ⇒ refuse ("not confident").
    if max_confidence <= CONFIDENCE_THRESHOLD:
        return _refusal(
            RefusalReason.DIFFUSE_POSTERIOR,
            model_state=model_state,
            baseline_state=baseline_state,
            max_confidence=max_confidence,
        )

    # 4. Baseline conflict — show BOTH, flag it, pick NO winner.
    if abs(model_state - baseline_state) > _CONFLICT_STATE_GAP:
        return GuardedPrediction(
            refused=False,
            reason=None,
            state=None,  # the system does NOT pick a winner
            max_confidence=max_confidence,
            conflict=True,
            model_state=model_state,
            baseline_state=baseline_state,
            message=(
                f"Baseline says State {baseline_state}, model says State {model_state} — "
                "they disagree by more than one state. Both are shown; no winner is picked."
            ),
        )

    # Confident and agreeing — return the state.
    return GuardedPrediction(
        refused=False,
        reason=None,
        state=model_state,
        max_confidence=max_confidence,
        conflict=False,
        model_state=model_state,
        baseline_state=baseline_state,
        message=f"State {model_state}",
    )
