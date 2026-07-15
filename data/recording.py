"""Write-path record construction with the ADR-8 timestamp discipline.

`datetime` is what she reported; `logged_at` is the system clock (from an
injected `Clock`); `bolus_offset_min` and `elapsed_min` are derived from
reported times only. The system clock populates `logged_at` and nothing else —
enforced by the S-105 forbidden-pattern guard (which flags any now()-call bound
to a clinical timestamp, scanning this module) and by a targeted write-path test.
"""

from __future__ import annotations

import datetime as dt

from core.clock import Clock, SystemClock
from core.timestamps import bolus_offset_min, elapsed_min
from data.tables import (
    CorrectionEvent,
    HypoRescueLog,
    LoggedBy,
    MealEvent,
    MealType,
)


def record_meal(
    *,
    reported_datetime: dt.datetime,
    meal_type: MealType,
    pre_bg: int,
    pre_bg_time: dt.datetime,
    meal_bolus_units: float,
    bolus_datetime: dt.datetime,
    carbs_g: float,
    logged_by: LoggedBy,
    clock: Clock | None = None,
) -> MealEvent:
    """Build a MealEvent from reported inputs.

    `reported_datetime` / `pre_bg_time` / `bolus_datetime` are all **reported**.
    `logged_at` is the system clock (ADR-8). `bolus_offset_min` is derived from
    the reported meal and bolus times.
    """
    clock = clock or SystemClock()
    logged_at = clock.now()  # system clock — the ONLY use of now() here (ADR-8)
    return MealEvent(
        datetime=reported_datetime,
        logged_at=logged_at,
        logged_by=logged_by,
        meal_type=meal_type,
        pre_bg=pre_bg,
        pre_bg_time=pre_bg_time,
        meal_bolus_units=meal_bolus_units,
        bolus_offset_min=bolus_offset_min(reported_datetime, bolus_datetime),
        carbs_g=carbs_g,
    )


def record_post_bg(
    meal: MealEvent, *, post_bg: int, post_bg_time: dt.datetime
) -> MealEvent:
    """Attach a post-meal reading. `post_bg_time` is **reported**; `elapsed_min`
    is computed from it and the reported meal time — never from entry time."""
    meal.post_bg = post_bg
    meal.post_bg_time = post_bg_time
    meal.elapsed_min = elapsed_min(meal.datetime, post_bg_time)
    return meal


def record_hypo_rescue(
    *, meal_id: int, grams: float | None, clock: Clock | None = None
) -> HypoRescueLog:
    """Append an independent rescue record to `hypo_rescue_log` (INV-7 / DL-019).

    `logged_at` is the system clock — this is the record's write time, not a
    clinical timestamp (ADR-8). The row is deliberately not FK-bound to the meal,
    so it survives a meal-row deletion and INV-7 can reconcile against it.
    """
    clock = clock or SystemClock()
    return HypoRescueLog(meal_id=meal_id, grams=grams, logged_at=clock.now())


def record_correction_event(
    *,
    reported_datetime: dt.datetime,
    bg_before: int,
    units: float,
    food_in_window: bool,
    clock: Clock | None = None,
) -> CorrectionEvent:
    """Build a standalone correction event from reported inputs (S-306, REQ-013).

    `reported_datetime` is **reported**; `logged_at` is the system clock (ADR-8).
    `iob_at_start` is left NULL — deferred to S-401's `iob_at()` (never
    hand-entered). `bg_after` / `bg_after_time` arrive at the +4 h follow-up.
    """
    clock = clock or SystemClock()
    return CorrectionEvent(
        datetime=reported_datetime,
        logged_at=clock.now(),  # system clock — the only now() here (ADR-8)
        bg_before=bg_before,
        units=units,
        food_in_window=food_in_window,
    )


def record_correction_followup(
    event: CorrectionEvent, *, bg_after: int, bg_after_time: dt.datetime, food_in_window: bool
) -> CorrectionEvent:
    """Attach the +4 h reading. `bg_after_time` is **reported**; `food_in_window`
    is confirmed at follow-up (it decides ISF cleanliness, 07 §6)."""
    event.bg_after = bg_after
    event.bg_after_time = bg_after_time
    event.food_in_window = food_in_window
    return event
