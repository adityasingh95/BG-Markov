"""Request/response models for the API (05 §1).

Every clinical timestamp is a **reported** value supplied by the client; the
server never substitutes ``now()``. ``bolus_offset_min`` is required — omitting
it is a 422 (REQ-003), never a silent default.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

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
