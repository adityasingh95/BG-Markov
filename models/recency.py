"""Recency weighting for the monthly refit (S-1009, REQ-060, DL-047).

`07 §Retraining`: *"Monthly refit, trailing 6 months, older data down-weighted."* Her
insulin sensitivity drifts — insulin resistance is present at TDD 60 U — so a meal from
February is weaker evidence about July than a meal from last week.

**Half-life 90 days** (DL-047, operator-approved): a meal from three months ago counts half
as much as one from this week; the oldest in a six-month window about a quarter.

★ **The weight decays and never reaches zero.** An exponential cannot, and nothing here
floors it. That is load-bearing rather than incidental: the obvious tidy-up — dropping rows
whose weight falls below some threshold — silently deletes the oldest lows, and *a rescued
low from five months ago is still a low*. Recency reduces how much it counts. It does not
decide it never happened.

This module computes one factor. It is **multiplied into** the S-601 hypo × macro-confidence
weights, never substituted for them (see `models.refit.composite_weights`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

# DL-047, operator-approved. A clinical-ish constant: changing it changes how much of her
# own history counts, so it is named, pinned by a test, and not tuned in passing.
RECENCY_HALFLIFE_DAYS: int = 90


def recency_weights(
    dates: Sequence[dt.datetime],
    *,
    as_of: dt.datetime,
    half_life_days: int = RECENCY_HALFLIFE_DAYS,
) -> npt.NDArray[np.float64]:
    """Exponential-decay weights in ``(0, 1]``, one per date: ``0.5 ** (age_days / H)``.

    ``as_of`` is **injected**, never read from the wall clock (ADR-8). The project has one
    sanctioned clock reader, and a refit whose weights depend on when it happened to run is
    a refit nobody can reproduce.

    Ages are **clamped at zero**, so a row dated ahead of ``as_of`` — clock skew, a restored
    backup, a mistyped year — weighs 1.0 rather than becoming the most influential row in
    the fit. Every ambiguity resolves toward *no special treatment*.
    """
    if half_life_days <= 0:
        raise ValueError(f"half_life_days must be positive; got {half_life_days!r}")
    ages = np.array(
        [max((as_of - when).total_seconds() / 86400.0, 0.0) for when in dates],
        dtype=float,
    )
    return np.asarray(0.5 ** (ages / float(half_life_days)), dtype=float)
