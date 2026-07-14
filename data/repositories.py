"""Data-layer accessors, including the INV-7 choke point.

`get_training_set` is the single place a training set is assembled, and it calls
`inv7_rescued_excluded_and_retained` before returning — so a set that violates
INV-7 (a rescued meal leaked into training, or a rescued meal missing from the
hypo events) cannot be returned; it raises. This is the invariant *wired into*
the feature, not merely checked somewhere.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import safety
from core.validity import exclusion_reasons, is_hypo_outcome, is_valid
from data.tables import MealEvent


def _meals_ordered(session: Session) -> list[MealEvent]:
    return list(session.scalars(select(MealEvent).order_by(MealEvent.datetime)))


def _minutes_since(prev: dt.datetime | None, current: dt.datetime) -> int | None:
    if prev is None:
        return None
    return round((current - prev).total_seconds() / 60.0)


def reasons_for(meal: MealEvent, prev_meal_datetime: dt.datetime | None) -> list[str]:
    """Exclusion reasons for one meal, given the previous meal's reported time."""
    return exclusion_reasons(
        post_bg=meal.post_bg,
        elapsed_min=meal.elapsed_min,
        hypo_treatment=meal.hypo_treatment,
        snack_during_window=meal.snack_during_window,
        minutes_since_prev_meal=_minutes_since(prev_meal_datetime, meal.datetime),
        macro_confidence=meal.macro_confidence,
    )


def annotate_validity(meal: MealEvent, prev_meal_datetime: dt.datetime | None) -> MealEvent:
    """Persist `is_valid` + `exclusion_reasons` on a meal (write time, 04 §5).
    `elapsed_min` is left as stored, even when invalid."""
    reasons = reasons_for(meal, prev_meal_datetime)
    meal.is_valid = is_valid(reasons)
    meal.exclusion_reasons = ",".join(reasons) if reasons else None
    return meal


def get_rescued_meals(session: Session) -> list[MealEvent]:
    return [m for m in _meals_ordered(session) if m.hypo_treatment]


def get_hypo_events(session: Session) -> list[MealEvent]:
    """Rescued meals (retained even if post_bg looks normal) plus measured lows
    (INV-7 / REQ-023)."""
    return [
        m
        for m in _meals_ordered(session)
        if m.hypo_treatment or is_hypo_outcome(m.post_bg)
    ]


def get_training_set(session: Session) -> list[MealEvent]:
    """Valid meals only. INV-7 is enforced here: the returned set cannot contain
    a rescued meal, and every rescued meal must be retained as a hypo event."""
    meals = _meals_ordered(session)
    training: list[MealEvent] = []
    prev: dt.datetime | None = None
    for meal in meals:
        if is_valid(reasons_for(meal, prev)):
            training.append(meal)
        prev = meal.datetime

    safety.inv7_rescued_excluded_and_retained(
        training_meal_ids=[m.meal_id for m in training],
        hypo_event_ids=[m.meal_id for m in get_hypo_events(session)],
        rescued_meal_ids=[m.meal_id for m in get_rescued_meals(session)],
    )
    return training
