"""S-802 [SAFETY] — the prediction log, write-before-return (SDET, written RED first).

A prediction shown but not recorded is a silent low waiting to happen: no shadow-mode
analysis, no way to ever learn it was wrong. The ordering is absolute — write first,
return second — and it must be enforced, not incidental. These tests mock the persistence
layer to fail and assert NO prediction escapes. See docs/stories/S-802.md.

RED: `data.predictions` does not exist yet.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.safety import SafetyViolation
from data.predictions import ServedPrediction, record_prediction, serve_prediction
from data.tables import PredictionLog
from models.guardrails import guard_prediction

_STATES = (1, 2, 3, 4, 5)


def _confident(state: int, peak: float = 0.8) -> np.ndarray:
    p = np.full(5, (1.0 - peak) / 4.0)
    p[state - 1] = peak
    return p


def _fields() -> dict[str, object]:
    return dict(
        model_version="v-test",
        gate_state="gate1_open",
        input_features={"pre_bg": 120.0, "carbs_g": 40.0},
        predicted_distribution={"1": 0.05, "2": 0.05, "3": 0.8, "4": 0.05, "5": 0.05},
        baseline_state=3,
    )


def test_record_prediction_persists_before_returning(session: Session) -> None:
    row = record_prediction(session, **_fields())  # type: ignore[arg-type]
    assert row.prediction_id is not None
    # it is already in the DB by the time record_prediction returned
    found = session.scalars(
        select(PredictionLog).where(PredictionLog.prediction_id == row.prediction_id)
    ).one()
    assert found.model_version == "v-test"
    assert found.gate_state == "gate1_open"
    assert found.baseline_state == 3


def test_unpersisted_write_raises_inv9_and_returns_nothing() -> None:
    """★ A write that yields no prediction_id ⇒ INV-9 raises; no prediction escapes."""
    fake = MagicMock(spec=Session)
    fake.flush.return_value = None  # flush that does NOT assign a prediction_id
    with pytest.raises(SafetyViolation):
        record_prediction(fake, **_fields())  # type: ignore[arg-type]


def test_failed_flush_propagates_and_returns_nothing() -> None:
    """★ Mock the persistence layer to raise ⇒ the error propagates, nothing returned."""
    fake = MagicMock(spec=Session)
    fake.flush.side_effect = RuntimeError("db write failed")
    with pytest.raises(RuntimeError):
        record_prediction(fake, **_fields())  # type: ignore[arg-type]


def test_serve_prediction_persists_a_state_then_returns(session: Session) -> None:
    guarded = guard_prediction(
        proba=_confident(3), states=_STATES, predicted_bg=120.0, baseline_state=3,
        in_distribution=True, n_nearby_train=50,
    )
    served = serve_prediction(
        session, guarded, model_version="v-test", gate_state="gate1_open",
        input_features={"pre_bg": 120.0},
    )
    assert isinstance(served, ServedPrediction)
    assert served.guarded.state == 3
    row = session.scalars(
        select(PredictionLog).where(PredictionLog.prediction_id == served.prediction_id)
    ).one()
    assert row.guardrail_fired is None  # a confident state, no refusal


def test_serve_prediction_persists_a_refusal_with_guardrail_reason(session: Session) -> None:
    guarded = guard_prediction(
        proba=_confident(3), states=_STATES, predicted_bg=120.0, baseline_state=3,
        in_distribution=False, n_nearby_train=50,   # OOD refusal
    )
    served = serve_prediction(
        session, guarded, model_version="v-test", gate_state="gate1_open",
        input_features={"pre_bg": 120.0},
    )
    row = session.scalars(
        select(PredictionLog).where(PredictionLog.prediction_id == served.prediction_id)
    ).one()
    assert row.guardrail_fired == "out_of_distribution"


def test_serve_prediction_refuses_to_return_on_failed_write() -> None:
    """★ If the persist fails, serve_prediction returns no ServedPrediction."""
    fake = MagicMock(spec=Session)
    fake.flush.return_value = None
    guarded = guard_prediction(
        proba=_confident(3), states=_STATES, predicted_bg=120.0, baseline_state=3,
        in_distribution=True, n_nearby_train=50,
    )
    with pytest.raises(SafetyViolation):
        serve_prediction(
            fake, guarded, model_version="v-test", gate_state="gate1_open",
            input_features={"pre_bg": 120.0},
        )
