"""Reported-timestamp derivations — the two most predictive features.

Both functions take **reported** datetimes and never read a clock. Conflating
reported time with log time here would corrupt the model silently (ADR-8).
"""

from __future__ import annotations

import datetime as dt


def require_naive(value: dt.datetime, *, field: str) -> dt.datetime:
    """Return ``value`` if it is a naive local wall-clock time; raise otherwise (S-1018).

    ★ **It refuses. It does not convert.**

    A reported clinical time is the number she read off a phone or a glucometer. It is a
    wall-clock time, not an instant, and this system has exactly one user in exactly one
    place — so a naive local datetime is the whole truth and an offset adds nothing but a
    way to be wrong.

    The three conversions all look reasonable and all lose:

    * ``value.replace(tzinfo=None)`` keeps the shifted numbers — 02:30 for an 08:00
      breakfast — and returns something that type-checks perfectly;
    * ``value.astimezone()`` converts to *the server's* timezone, which is not where she is,
      and is wrong by a different amount depending on where the container runs;
    * ``value.astimezone(dt.UTC)`` is the same mistake with a fixed sign.

    Every one of them is silent. So an offset is an input error and gets a 422 that names
    the field — the same reasoning as DL-035's ICR: this is a malformed request, not a
    breached invariant, and it raises ``ValueError`` rather than ``SafetyViolation``.
    Conflating the two would make the invariant vocabulary mean nothing.

    ADR-8's known failure is *fabricating* a clinical timestamp. This is the other one:
    **relabelling** the one she reported. It leaves no anomaly behind — 02:30 is a perfectly
    plausible row for someone who sleeps badly — so it has to be refused at the door or it
    is never detectable afterwards.
    """
    if value.tzinfo is not None:
        raise ValueError(
            f"{field} must be a naive local wall-clock time (e.g. 2026-07-30T08:00:00) — "
            f"got a timezone-aware value ({value.isoformat()}). A reported clinical time is "
            "the time she read, not an instant; see ADR-8."
        )
    return value


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
