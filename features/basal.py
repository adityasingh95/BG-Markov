"""Effective basal — Tresiba / degludec EWMA (S-402, REQ-021).

Today's dose is not today's effect: degludec has ~42 h duration and reaches steady
state only after 3–4 days (07 §3). The effective background insulin is an
exponentially-weighted moving average of the daily dose with a **25 h half-life**,
computed over real timestamps so the decay is in time, not row count. A dose change
is uninterpretable for 3 days — `in_titration_lockout` flags that window so
basal-related guidance can be suppressed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from datetime import timedelta

import pandas as pd

BASAL_HALFLIFE = "25h"  # degludec EWMA half-life (07 §3)
TITRATION_LOCKOUT_DAYS = 3  # a dose change is uninterpretable for this many days


def effective_basal(doses: list[tuple[dt.datetime, float]]) -> list[float]:
    """EWMA-smoothed effective basal aligned to each daily dose.

    ``doses`` is ``[(datetime, units), …]`` ascending (typically from ``basal_log``,
    one per day). The half-life is applied over the real timestamps, so a dose
    change ramps over days rather than stepping.
    """
    if not doses:
        return []
    times = pd.DatetimeIndex([when for when, _ in doses])
    values = pd.Series([float(units) for _, units in doses], index=times)
    smoothed = values.ewm(halflife=BASAL_HALFLIFE, times=times).mean()
    return [float(v) for v in smoothed.to_list()]


def _change_times(doses: Iterable[tuple[dt.datetime, float]]) -> list[dt.datetime]:
    """Timestamps at which the dose differs from the immediately preceding one."""
    changes: list[dt.datetime] = []
    prev: float | None = None
    for when, units in doses:
        if prev is not None and float(units) != prev:
            changes.append(when)
        prev = float(units)
    return changes


def in_titration_lockout(doses: list[tuple[dt.datetime, float]], at: dt.datetime) -> bool:
    """True if ``at`` is within ``[C, C + 3 days]`` of any dose change ``C``.

    Errs toward suppression: the change day through +3 days inclusive are locked
    (+4 days is clear), so a basal coefficient learnt mid-ramp is never trusted.
    """
    window = timedelta(days=TITRATION_LOCKOUT_DAYS)
    return any(change <= at <= change + window for change in _change_times(doses))
