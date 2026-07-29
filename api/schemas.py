"""Request/response models for the API (05 §1).

Every clinical timestamp is a **reported** value supplied by the client; the
server never substitutes ``now()``. ``bolus_offset_min`` is required — omitting
it is a 422 (REQ-003), never a silent default.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict

from data.tables import LoggedBy, MealType


class MealCreate(BaseModel):
    idempotency_key: str
    datetime: dt.datetime  # REPORTED — when she ate
    meal_type: MealType
    pre_bg: int
    pre_bg_time: dt.datetime  # REPORTED
    carbs_g: float
    protein_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    macro_confidence: int = 95
    meal_bolus_units: float
    correction_bolus_units: float = 0.0
    bolus_offset_min: int  # REQUIRED — REQ-003, no default
    logged_by: LoggedBy = LoggedBy.patient
    notes: str | None = None


class MealCreated(BaseModel):
    meal_id: int
    test_at: dt.datetime
    message: str


class PostBgUpdate(BaseModel):
    post_bg: int
    post_bg_time: dt.datetime  # REPORTED — required, never assumed
    hypo_treatment: bool = False
    hypo_treatment_g: float | None = None
    snack_during_window: bool = False


class PostBgResult(BaseModel):
    meal_id: int
    elapsed_min: int | None
    is_valid: bool
    exclusion_reasons: list[str]


class CorrectionCreate(BaseModel):
    datetime: dt.datetime  # REPORTED — when she took the correction
    bg_before: int
    units: float
    food_in_window: bool  # "will you be eating in the next 4 hours?"
    logged_by: LoggedBy = LoggedBy.patient


class CorrectionCreated(BaseModel):
    event_id: int
    prompt_followup: bool  # only when no food is expected in the window
    followup_at: dt.datetime | None
    message: str


class CorrectionFollowup(BaseModel):
    bg_after: int
    bg_after_time: dt.datetime  # REPORTED — the +4 h reading time
    food_in_window: bool  # confirmed at follow-up


class CorrectionFollowupResult(BaseModel):
    event_id: int
    bg_after: int
    food_in_window: bool


class AdherenceResponse(BaseModel):
    n_meals: int
    valid_meals: int
    meals_to_gate1: int
    in_window_rate: float | None
    exclusions_by_reason: dict[str, int]
    days_since_last_log: int | None
    median_lag_min: float | None


class PromotionRequest(BaseModel):
    """`POST /api/operator/promote` / `/revoke` (S-1001b, `05 §6`).

    ``confirmed`` must be **explicitly true**. Reaching the URL is not a decision; saying
    yes is, and the difference matters when the action is putting someone who cannot feel
    a low in front of a model.

    Extra fields are **ignored, not rejected**. A client that sends
    ``{"preconditions_met": true}`` gets the same answer as one that does not: the server
    re-derives readiness from live data and refuses if it is not there. Rejecting the
    payload would only prove the field was unwelcome; ignoring it proves the claim has **no
    effect**, which is the property that matters.
    """

    # `model_version` collides with pydantic's protected `model_` namespace; the field name
    # comes from `05 §6` and the DB column, so the namespace is released rather than the
    # contract renamed.
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    confirmed: bool


class PromotionResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    is_promoted: bool
