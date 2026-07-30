"""Request/response models for the API (05 §1).

Every clinical timestamp is a **reported** value supplied by the client; the
server never substitutes ``now()``. ``bolus_offset_min`` is required — omitting
it is a 422 (REQ-003), never a silent default.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.timestamps import require_naive
from data.tables import LoggedBy, MealType


def _naive(field: str) -> classmethod:  # type: ignore[type-arg]
    """A validator that refuses a timezone offset on a **reported** clinical time (S-1018).

    ★ One factory, applied by name, so a new reported-time field is one line and the rule
    cannot be re-implemented slightly differently in a second schema. The rule itself lives
    in `core.timestamps.require_naive` — this only points at it.

    Deliberately **not** applied to ``logged_at`` (never client-supplied), to
    ``BasalCreate.time_taken`` (a ``time``, which carries no date and no offset here) or to
    any ``date`` field.
    """
    def _check(_cls: object, value: dt.datetime) -> dt.datetime:
        return require_naive(value, field=field)

    return field_validator(field)(classmethod(_check))


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

    _naive_datetime = _naive("datetime")
    _naive_pre_bg_time = _naive("pre_bg_time")


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

    _naive_post_bg_time = _naive("post_bg_time")


class PostBgResult(BaseModel):
    meal_id: int
    elapsed_min: int | None
    is_valid: bool
    exclusion_reasons: list[str]


class CorrectionCreate(BaseModel):
    #: S-1019. Optional so an existing client (and every pre-S-1019 test) still works, but
    #: when present it is enforced. Required-and-unread was the S-1016 mistake; the mirror
    #: image — required-and-enforced with no client sending it — would simply lock her out.
    idempotency_key: str | None = None
    datetime: dt.datetime  # REPORTED — when she took the correction
    bg_before: int
    units: float
    food_in_window: bool  # "will you be eating in the next 4 hours?"
    logged_by: LoggedBy = LoggedBy.patient

    _naive_datetime = _naive("datetime")


class CorrectionCreated(BaseModel):
    event_id: int
    prompt_followup: bool  # only when no food is expected in the window
    followup_at: dt.datetime | None
    message: str


class CorrectionFollowup(BaseModel):
    bg_after: int
    bg_after_time: dt.datetime  # REPORTED — the +4 h reading time
    food_in_window: bool  # confirmed at follow-up

    _naive_bg_after_time = _naive("bg_after_time")


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


class BasalCreate(BaseModel):
    """`POST /api/basal` (S-1013, REQ-007).

    ``time_taken`` is **required** and **reported** — when she injected. A server-side
    default would be `datetime.now()` wearing a different hat, and it is the one field
    whose fabrication silently distorts every later `effective_basal` (ADR-8).
    """

    date: dt.date
    units: float = Field(gt=0)
    time_taken: dt.time
    logged_by: LoggedBy = LoggedBy.patient


class BasalRecorded(BaseModel):
    date: dt.date
    units: float


class ProfileVersionCreate(BaseModel):
    """`POST /api/operator/profile` (S-1010, REQ-061, `05 §6`).

    ``gt=0`` on both divisors mirrors `data.profile` (DL-048): the calculator divides by
    them, so a non-positive value is refused at the door. Values that are merely *unusual*
    pass validation and come back **flagged** — blocking them would push a genuine clinical
    change into a hand-edit of the database, audited nowhere.
    """

    effective_from: dt.date
    icr: float = Field(gt=0)
    isf: float = Field(gt=0)
    target_bg: int = Field(gt=0)


class ProfileVersionCreated(BaseModel):
    effective_from: dt.date
    icr: float
    isf: float
    target_bg: int
    flags: list[str]
