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
from data.tables import LoggedBy, MealEvent, MealType


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
