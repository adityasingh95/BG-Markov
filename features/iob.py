"""Insulin-on-board — the Fiasp exponential activity curve (S-401, REQ-020).

IOB is **derived**, never entered: `iob_fraction(t)` is the share of a bolus still
active `t` minutes after injection, and `iob_at` sums that share over every prior
injection. There is no parameter, column, or request field that sets IOB directly
— the S-105 `detect_manual_iob` guard scans every package to keep it that way.

Model: the standard LoopKit / OpenAPS exponential insulin-activity curve,
parameterised by peak time `tp` and duration `td`. Fiasp (fast): tp=55, td=240.
The curve is bounded [0, 1] and strictly decreasing on (0, td) — insulin only
clears, never re-accumulates.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable

TP_MIN: float = 55.0  # time to peak activity (min) — Fiasp
TD_MIN: float = 240.0  # total duration of activity (min) — Fiasp

# Precomputed curve constants (functions of tp, td only).
_TAU = TP_MIN * (1.0 - TP_MIN / TD_MIN) / (1.0 - 2.0 * TP_MIN / TD_MIN)
_A = 2.0 * _TAU / TD_MIN
_S = 1.0 / (1.0 - _A + (1.0 + _A) * math.exp(-TD_MIN / _TAU))


def iob_fraction(t_min: float) -> float:
    """Fraction of a bolus still active `t_min` minutes after injection, in [0, 1].

    `t <= 0` (a bolus at or after `at`, e.g. clock skew) is full IOB (1.0);
    `t >= td` is fully cleared (0.0); strictly decreasing in between.
    """
    if t_min <= 0.0:
        return 1.0
    if t_min >= TD_MIN:
        return 0.0
    return 1.0 - _S * (1.0 - _A) * (
        (t_min * t_min / (_TAU * TD_MIN * (1.0 - _A)) - t_min / _TAU - 1.0)
        * math.exp(-t_min / _TAU)
        + 1.0
    )


def iob_at(at: dt.datetime, boluses: Iterable[tuple[dt.datetime, float]]) -> float:
    """Total insulin-on-board at `at`: sum over injections of
    `units · iob_fraction(minutes since injection)`.

    Linear in units, so it is additive — two 5 U boluses at one instant equal one
    10 U bolus. `boluses` is typically read from `bolus_log`; this function stays
    pure (no DB, no clock) so it is trivially testable and cannot acquire an input
    path for IOB itself.
    """
    total = 0.0
    for when, units in boluses:
        age_min = (at - when).total_seconds() / 60.0
        total += units * iob_fraction(age_min)
    return total
