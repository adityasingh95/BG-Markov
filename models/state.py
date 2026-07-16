"""The shared BG→state binner (S-501, 03 §).

One function, one boundary set — the baseline, the ordinal model, and the risk
readout all bin the same way. **Ordering is load-bearing:** predicting State 4 when
the truth is State 1 is catastrophic, so the states are monotone in BG and the
boundaries are exact.

Binning happens on the **output** (a predicted or observed BG), never on ``pre_bg``
as a model input — the forbidden-pattern guard enforces that (binning ``pre_bg`` as
an input would discard exactly the low-BG resolution needed to predict a low).
"""

from __future__ import annotations

# 03 §: State 1 <54 · 2 54–79 · 3 80–180 · 4 181–250 · 5 >250.
STATE_BOUNDARIES: tuple[int, int, int, int] = (54, 80, 181, 251)


def bg_to_state(bg: float) -> int:
    """Map a blood-glucose value (mg/dL) to its clinical state 1–5."""
    for state, boundary in enumerate(STATE_BOUNDARIES, start=1):
        if bg < boundary:
            return state
    return 5
