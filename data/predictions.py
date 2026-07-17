"""The prediction log — write before return (S-802, REQ-045, INV-9).

A prediction shown but not recorded is a silent low waiting to happen: no shadow-mode
analysis, no accountability, no way to ever learn it was wrong. So the ordering is
absolute — **write first, return second** — and it is enforced here, not left to hope: the
row is flushed to ``prediction_log`` and its id confirmed via INV-9 **before** any value is
returned. A failed write raises; it never degrades into an unlogged prediction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from core.safety import inv9_prediction_persisted
from data.tables import PredictionLog
from models.guardrails import GuardedPrediction


def record_prediction(
    session: Session,
    *,
    model_version: str,
    gate_state: str,
    input_features: dict[str, Any],
    predicted_distribution: dict[str, Any],
    baseline_state: int,
    meal_id: int | None = None,
    guardrail_fired: str | None = None,
) -> PredictionLog:
    """Persist a prediction to ``prediction_log`` and return the row — **only after** the
    write is confirmed (INV-9).

    The ``flush`` writes the row and assigns ``prediction_id``; ``inv9_prediction_persisted``
    raises if the write produced no row. The ``return`` is physically after both, so no
    unpersisted prediction can escape.
    """
    row = PredictionLog(
        meal_id=meal_id,
        model_version=model_version,
        gate_state=gate_state,
        input_features=input_features,
        predicted_distribution=predicted_distribution,
        baseline_state=baseline_state,
        guardrail_fired=guardrail_fired,
    )
    session.add(row)
    session.flush()  # WRITE to the DB and assign prediction_id — before any return
    # INV-9: refuse to return an unpersisted prediction.
    inv9_prediction_persisted(row.prediction_id)
    return row


@dataclass(frozen=True)
class ServedPrediction:
    """What a caller receives — constructed only *after* the prediction is persisted."""

    prediction_id: int
    guarded: GuardedPrediction


def _distribution(guarded: GuardedPrediction) -> dict[str, Any]:
    return {
        "refused": guarded.refused,
        "reason": guarded.reason.value if guarded.reason is not None else None,
        "state": guarded.state,
        "conflict": guarded.conflict,
        "model_state": guarded.model_state,
        "baseline_state": guarded.baseline_state,
        "max_confidence": guarded.max_confidence,
    }


def serve_prediction(
    session: Session,
    guarded: GuardedPrediction,
    *,
    model_version: str,
    gate_state: str,
    input_features: dict[str, Any],
    meal_id: int | None = None,
) -> ServedPrediction:
    """Persist a guarded prediction (S-801) and return it — **write before return**.

    Maps the ``GuardedPrediction`` to the log fields, calls ``record_prediction`` first,
    and builds the ``ServedPrediction`` only from the persisted row — so a prediction that
    was not written first can never be handed back.
    """
    row = record_prediction(
        session,
        model_version=model_version,
        gate_state=gate_state,
        input_features=input_features,
        predicted_distribution=_distribution(guarded),
        baseline_state=guarded.baseline_state,
        meal_id=meal_id,
        guardrail_fired=guarded.reason.value if guarded.reason is not None else None,
    )
    return ServedPrediction(prediction_id=row.prediction_id, guarded=guarded)
