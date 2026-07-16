"""Operator adherence metrics (S-307, REQ-053).

Adherence is the bottleneck: Gate 1 needs 150 valid meals (03 §). This module
computes the operator dashboard's numbers, read-only, from the meal log. The
load-bearing one is ``median_lag_min`` — ``median(logged_at − datetime)`` — the
recall-bias early-warning, computed from the **two distinct columns** (the ADR-8
payoff). Nothing here is patient-visible; it reports no model output.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.tables import MealEvent

# Gate 1's volume precondition (03 §). Necessary, never sufficient — hypo recall
# must still beat the clinical baseline; that gate decision is a later story.
GATE1_VALID_MEALS: int = 150


@dataclass(frozen=True)
class AdherenceMetrics:
    n_meals: int
    valid_meals: int
    meals_to_gate1: int
    in_window_rate: float | None  # over meals WITH an outcome; None if none yet
    exclusions_by_reason: dict[str, int]
    days_since_last_log: int | None
    median_lag_min: float | None  # median(logged_at − datetime), minutes


def adherence_metrics(session: Session, *, now: dt.datetime) -> AdherenceMetrics:
    """Compute the dashboard metrics. ``now`` is injected (the one operational
    clock read — days-since-last-log; never a clinical timestamp)."""
    meals = list(session.scalars(select(MealEvent)))
    n = len(meals)

    valid = sum(1 for m in meals if m.is_valid)

    reasons: Counter[str] = Counter()
    for m in meals:
        if m.exclusion_reasons:
            reasons.update(m.exclusion_reasons.split(","))

    with_outcome = [m for m in meals if m.post_bg is not None]
    in_window_rate: float | None = None
    if with_outcome:
        out_of_window = sum(
            1
            for m in with_outcome
            if m.exclusion_reasons and "outside_window" in m.exclusion_reasons.split(",")
        )
        in_window_rate = (len(with_outcome) - out_of_window) / len(with_outcome)

    days_since_last_log: int | None = None
    if meals:
        last_log = max(m.logged_at for m in meals)
        days_since_last_log = (now - last_log).days

    median_lag_min: float | None = None
    if meals:
        # THE metric: derived from the two distinct columns, not fabricated.
        lags = [(m.logged_at - m.datetime).total_seconds() / 60.0 for m in meals]
        median_lag_min = median(lags)

    return AdherenceMetrics(
        n_meals=n,
        valid_meals=valid,
        meals_to_gate1=max(0, GATE1_VALID_MEALS - valid),
        in_window_rate=in_window_rate,
        exclusions_by_reason=dict(reasons),
        days_since_last_log=days_since_last_log,
        median_lag_min=median_lag_min,
    )
