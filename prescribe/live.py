"""The live prediction path for one meal (S-1015, REQ-045/REQ-059, INV-2/INV-9).

`serve_meal_prediction` has existed since S-1008 and **nothing called it**, so
`prediction_log` stayed empty, shadow evidence never accrued, the 90-day clock never
started, and Gate 1 could never open. This is the composition root that connects it.

★ **Prediction is not gated; display is.** Shadow mode *is* "the model predicts, everything
is logged, she sees nothing" — the only mechanism by which the evidence Gate 1 requires ever
accumulates. INV-2 is enforced on the readout (S-1002/S-804), not here. Gating prediction
here would stop the clock so Gate 1 could never legitimately open, and **the deadlock would
look like caution**.

★ **The features served are assembled by `data.training`, the same code that assembles the
features trained on.** A second, parallel feature path drifts, and drift shows up as a model
that scores well and predicts badly — the single most dangerous failure this system has.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from core.safety import SafetyViolation
from data.model_store import load_fitted_model
from data.predictions import record_prediction
from data.repositories import (
    active_profile,
    get_promoted_artifact,
    iob_from_prior_boluses,
)
from data.tables import MealEvent
from data.training import assemble_training_data, derive_meal_features
from models.baseline import predict_baseline_bg
from models.state import bg_to_state
from prescribe.gates import gate1_status
from prescribe.serving import MealPrediction, serve_meal_prediction

_BASELINE_OUT_OF_RANGE = "baseline_out_of_range"


def _n_training_rows(session: Session, now: dt.datetime) -> int:
    """How much training data stands behind this prediction — the sparse-region guardrail's
    input (07 §10 #2). Counted, not assumed."""
    return len(assemble_training_data(session, as_of=now))


@dataclass(frozen=True)
class LiveOutcome:
    """What the live path produced for one meal.

    ``served is None`` means no model output exists — no promotion, no stored model, or a
    feature mismatch. It never means "a model ran and we dropped the result".
    """

    baseline_bg: float | None
    baseline_state: int | None
    input_features: dict[str, float]
    served: Any = None
    #: Set when nothing could be predicted, for a stated reason. `None` means no refusal.
    refused: str | None = None

    @property
    def prediction(self) -> MealPrediction | None:  # pragma: no cover - convenience
        return None


def predict_for_meal(
    session: Session, meal: MealEvent, *, now: dt.datetime
) -> LiveOutcome | None:
    """Predict for one meal and persist the result. ``None`` when nothing can be predicted.

    **Fails closed at every step** — no profile, no ICR, no promoted artifact, no stored
    model, or a meal the assembler does not produce a row for, all yield ``None`` with no
    row written and no exception raised. The absence of a prediction is a normal state of
    the world, not an error.

    ``now`` is injected (ADR-8). It selects the trailing window the feature assembler uses;
    a live path whose features depend on when it happened to run is not reproducible from
    the log afterwards.
    """
    profile = active_profile(session)
    if profile is None or profile.icr is None or profile.icr <= 0:
        return None

    # ★ The SAME derivation the refit uses, not a parallel path — and deliberately NOT
    # `assemble_training_data`, which filters to meals that already have an outcome. The
    # meal being predicted has no `post_bg` yet; that is the entire point. Feature
    # derivation and training-set membership are different questions.
    features = {k: float(v) for k, v in derive_meal_features(session, meal).items()}

    artifact = get_promoted_artifact(session)

    try:
        baseline_bg = predict_baseline_bg(
            pre_bg=float(meal.pre_bg),
            carbs_g=float(meal.carbs_g),
            meal_bolus_units=float(meal.meal_bolus_units),
            correction_bolus_units=float(meal.correction_bolus_units),
            # ★ PRIOR insulin only — not `features['iob_at_meal']`, which counts this meal's
            # own pre-bolus because a pre-bolus is timestamped before the meal. `07 §4`
            # subtracts meal_bolus and iob as separate terms, so using the feature here
            # subtracts the same insulin twice (DL-054).
            iob_at_meal=iob_from_prior_boluses(
                session, at=meal.datetime, meal_id=meal.meal_id
            ),
            icr=float(profile.icr),
            isf=float(profile.isf),
        )
    except SafetyViolation as exc:
        # ★ DL-053 AMENDED, operator-approved 2026-07-30. INV-6 fired on the BASELINE — an
        # internal diagnostic she never sees — while she was logging a meal. Before the
        # amendment this returned HTTP 500 and HER MEAL WAS LOST, not merely unpredicted.
        #
        # INV-6 is NOT weakened: it still raises inside `predict_baseline_bg`, and no
        # out-of-range value is used, stored as a prediction, or shown anywhere. What changed
        # is what the LOGGING path does with the raise. Her primary capture surface must not
        # depend on the arithmetic of a number nobody reads.
        #
        # ★ Caught is not the same as SILENT. The refusal is persisted like any other
        # refusal (S-801/S-802) — auditable, never a blank — so "the model stopped
        # predicting" can never look identical to "no model is promoted".
        if artifact is not None:
            record_prediction(
                session,
                model_version=artifact.version,
                gate_state="shadow",
                input_features=features,
                predicted_distribution={},
                baseline_state=0,
                meal_id=meal.meal_id,
                guardrail_fired=_BASELINE_OUT_OF_RANGE,
            )
        return LiveOutcome(
            baseline_bg=None,
            baseline_state=None,
            input_features=features,
            refused=f"{_BASELINE_OUT_OF_RANGE}: {exc}",
        )
    baseline_state = bg_to_state(baseline_bg)

    model = load_fitted_model(session, artifact) if artifact is not None else None
    if model is None:
        # No promoted model, or one written before S-1014 with nothing stored. The baseline
        # stands on its own; there is nothing to log because nothing was predicted.
        return LiveOutcome(
            baseline_bg=baseline_bg, baseline_state=baseline_state, input_features=features
        )

    try:
        # `predict_proba_for` refuses a feature order that does not match the stored model
        # (S-1014) — a positional mismatch would otherwise be confident and wrong.
        x = np.array([[features[name] for name in model.feature_names]], dtype=float)
        model.predict_proba_for(x, feature_names=model.feature_names)
    except KeyError:
        # The promoted model names a feature this assembler no longer produces. Serving it
        # would mis-index the coefficient vector; refusing costs one prediction.
        return LiveOutcome(
            baseline_bg=baseline_bg, baseline_state=baseline_state, input_features=features
        )

    # `gate_state` records the gate AT THE MOMENT OF PREDICTION, so the row says what the
    # world looked like when it was written rather than what it looks like when it is read.
    gate = gate1_status(
        valid_meals=_n_training_rows(session, now),
        model_hypo_recall=float(artifact.metrics.get("hypo_recall") or 0.0)
        if artifact is not None else 0.0,
        baseline_hypo_recall=0.0,
        is_promoted=True,
        shadow_days=0,
        calibration_ok=False,
    )
    served = serve_meal_prediction(
        session,
        model=model,
        features=x,
        baseline_state=baseline_state,
        predicted_bg=baseline_bg,
        in_distribution=True,
        n_nearby_train=_n_training_rows(session, now),
        input_features=features,
        meal_id=meal.meal_id,
        gate_state="open" if gate.is_open else "shadow",
    )
    return LiveOutcome(
        baseline_bg=baseline_bg,
        baseline_state=baseline_state,
        input_features=features,
        served=served.served,
    )


def predict_for_meal_safely(
    session: Session, meal: MealEvent, *, now: dt.datetime
) -> LiveOutcome | None:
    """:func:`predict_for_meal`, with the DL-053 error policy applied. **One named place.**

    ★ **A `SafetyViolation` propagates; nothing else does.**

    Meal logging is her primary capture surface: if a model error takes that route down she
    cannot log, which is worse for her than having no prediction. But swallowing errors
    would make INV-9 unenforceable and would hide INV-6 exactly where it fires.

    Catching a *failure to predict* does not weaken INV-9. INV-9 constrains **write before
    return**, and here there is no return — a prediction that never happened cannot escape
    unlogged. What would weaken it is catching an exception raised *by the write*, and that
    path raises `SafetyViolation`, which is re-raised untouched.

    This lives here, not in `api/app.py`, on purpose. The S-1002 guard forbids the route
    from naming any safety exception at all, and that guard stays maximally strict: a broad
    `except` in a request handler is indistinguishable, to a reader and to an AST check, from
    the one-line version that disarms INV-9 and INV-6 together. Putting the policy in a named
    function makes it reviewable, testable, and greppable — one rule, one place, the same
    shape as `core/safety.py`.

        Her data capture never depends on the model working.
        Her safety invariants never depend on the model failing quietly.
    """
    try:
        return predict_for_meal(session, meal, now=now)
    except SafetyViolation:
        raise           # an invariant was breached — it must stay loud
    except Exception:   # noqa: BLE001 - deliberate and narrow; see DL-053
        session.rollback()
        return None
