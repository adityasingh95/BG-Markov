"""Live per-meal prediction wiring (S-1008, REQ-059).

**Pure orchestration — no model logic lives here.** Every component is already built and
tested; this module only fixes the *order* they run in, because the order is where INV-9
and INV-2 either hold or quietly stop holding.

```
features → promoted model → guardrails → persist (INV-9) → serve
```

**Prediction is not gated; display is.** Shadow mode means the model predicts and every
prediction is logged while *nothing* is shown to her — that is the only mechanism by which
the 90 days of evidence Gate 1 requires ever accumulates. So this module deliberately takes
**no gate argument** and never calls ``require_gate1``: INV-2 is enforced on the readout
(S-1002/S-804), where display actually happens.

Getting that backwards fails in both directions. Gating prediction here would stop the
shadow clock from accruing evidence, so Gate 1 could never legitimately open — and the
deadlock would look like caution. Gating nothing at all would breach INV-2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from data.predictions import ServedPrediction, serve_prediction
from data.repositories import get_promoted_artifact
from models.guardrails import guard_prediction


class _ProbabilityModel(Protocol):
    """The slice of a fitted model this module needs. Structural, so the orchestration
    depends on a shape rather than on `models.ordinal` — and cannot grow model logic."""

    states: tuple[int, ...]

    def predict_proba(self, x: Any) -> Any: ...


@dataclass(frozen=True)
class MealPrediction:
    """The outcome of serving one meal.

    ``served is None`` means **no model was promoted**, so only the clinical baseline is
    available — the readout renders that. It never means "a model ran but we dropped it".
    """

    baseline_state: int
    served: ServedPrediction | None
    model_version: str | None


def serve_meal_prediction(
    session: Session,
    *,
    model: _ProbabilityModel | None,
    features: Any,
    baseline_state: int,
    predicted_bg: float,
    in_distribution: bool,
    n_nearby_train: int,
    input_features: dict[str, Any],
    meal_id: int | None = None,
    gate_state: str = "shadow",
) -> MealPrediction:
    """Run the live path for one meal and return a persisted, guarded prediction.

    The baseline is computed by the caller and passed in — it is causal, always available,
    and is also the kill-switch fallback (S-803), so every return carries a usable answer
    even when the model path refuses.

    Raises rather than degrading: a guardrail-detected absurd BG raises ``SafetyViolation``
    (INV-6), and a failed ``prediction_log`` write propagates so that **nothing is served**
    (INV-9). Neither is caught here — catching them is what would turn a hard error into a
    silent, unlogged prediction.
    """
    promoted = get_promoted_artifact(session)
    if promoted is None or model is None:
        # No promoted model ⇒ return BEFORE any model call. There is no path on which an
        # unpromoted model's output reaches a caller.
        return MealPrediction(
            baseline_state=baseline_state, served=None, model_version=None
        )

    proba = model.predict_proba(features)[0]
    guarded = guard_prediction(
        proba=proba,
        states=tuple(model.states),
        predicted_bg=predicted_bg,
        baseline_state=baseline_state,
        in_distribution=in_distribution,
        n_nearby_train=n_nearby_train,
    )
    # INV-9: `serve_prediction` persists and confirms the row BEFORE returning, and it is
    # the only way this function produces a servable value — so a prediction cannot escape
    # unlogged. A refusal is persisted like any other prediction: auditable, renderable,
    # never a blank.
    served = serve_prediction(
        session,
        guarded,
        model_version=promoted.version,
        gate_state=gate_state,
        input_features=input_features,
        meal_id=meal_id,
    )
    return MealPrediction(
        baseline_state=baseline_state,
        served=served,
        model_version=promoted.version,
    )
