"""Reported-timestamp derivations — the two most predictive features.

Both functions take **reported** datetimes and never read a clock. Conflating
reported time with log time here would corrupt the model silently (ADR-8).
"""

from __future__ import annotations

import datetime as dt


def _minutes_between(earlier: dt.datetime, later: dt.datetime) -> int:
    """Signed whole minutes from ``earlier`` to ``later``, rounded to nearest."""
    return round((later - earlier).total_seconds() / 60.0)


def bolus_offset_min(meal_datetime: dt.datetime, bolus_datetime: dt.datetime) -> int:
    """Signed minutes between the bolus and the first bite.

    Negative = pre-bolus (bolus **before** the meal); positive = bolus after.
    """
    return _minutes_between(meal_datetime, bolus_datetime)


def elapsed_min(meal_datetime: dt.datetime, post_bg_time: dt.datetime) -> int:
    """Reported minutes between the meal and the post-meal reading.

    Computed from the **reported** reading time, never from when it was entered.
    """
    return _minutes_between(meal_datetime, post_bg_time)
