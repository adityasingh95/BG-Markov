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
from data.tables import BolusLog, CorrectionEvent, HypoRescueLog, MealEvent
from features.iob import iob_at


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


def get_recorded_rescue_meal_ids(session: Session) -> set[int]:
    """The rescued set INV-7 reconciles against: the **union** of meals currently
    flagged `hypo_treatment` and meals recorded in the independent `hypo_rescue_log`
    ledger (S-305 / DL-019).

    Sourcing from the ledger — not the flag alone — is what lets INV-7 catch the
    two ways a low can silently disappear: a meal row that is deleted (gone from
    the flag set, still in the ledger) or a `hypo_treatment` flag that is cleared
    (same). The ledger entry is a fact that outlives both.
    """
    flagged = {m.meal_id for m in get_rescued_meals(session)}
    ledgered = set(session.scalars(select(HypoRescueLog.meal_id)))
    return flagged | ledgered


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
        rescued_meal_ids=get_recorded_rescue_meal_ids(session),
    )
    return training


def get_clean_correction_events(session: Session) -> list[CorrectionEvent]:
    """The unconfounded ISF signal (07 §6): standalone corrections with no food
    AND a KNOWN, low insulin-on-board.

    Filter: ``food_in_window == False AND iob_at_start is not None AND
    iob_at_start < 0.5``. A NULL ``iob_at_start`` is **deferred, not clean** — the
    IOB engine (S-401) has not yet backfilled it, so we do not know the confounder
    and the event must be excluded. This is the accessor the future ``derive-isf``
    (S-501) reads; it never mutates or applies ISF.
    """
    return list(
        session.scalars(
            select(CorrectionEvent)
            .where(
                CorrectionEvent.food_in_window.is_(False),
                CorrectionEvent.iob_at_start.is_not(None),
                CorrectionEvent.iob_at_start < 0.5,
            )
            .order_by(CorrectionEvent.datetime)
        )
    )


def boluses_before(session: Session, at: dt.datetime) -> list[tuple[dt.datetime, float]]:
    """Injections logged **strictly before** ``at`` — the pre-existing insulin at
    that moment. Strictly-before excludes a bolus logged at the same instant (e.g.
    the correction being captured), which is the intervention, not prior IOB."""
    rows = session.execute(
        select(BolusLog.datetime, BolusLog.units).where(BolusLog.datetime < at)
    ).all()
    return [(when, units) for when, units in rows]


def iob_at_start_at(session: Session, at: dt.datetime) -> float:
    """Insulin-on-board from PRIOR injections at ``at`` (S-306b / DL-020).

    The single bridge from the pure S-401 IOB engine to ``bolus_log``. Used to fill
    ``correction_event.iob_at_start`` — the confounder that decides whether a
    correction is a clean ISF signal (07 §6). Derived, never entered.
    """
    return iob_at(at, boluses_before(session, at))


def backfill_correction_iob(session: Session) -> int:
    """Fill ``iob_at_start`` for correction events left NULL before the IOB engine
    existed (DL-020). Returns the number filled; idempotent."""
    pending = list(
        session.scalars(
            select(CorrectionEvent).where(CorrectionEvent.iob_at_start.is_(None))
        )
    )
    for event in pending:
        event.iob_at_start = iob_at_start_at(session, event.datetime)
    session.commit()
    return len(pending)
