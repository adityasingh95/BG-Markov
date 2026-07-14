"""Record validity — the six exclusion rules of 04 §5 / 03 §2.

Pure functions. `exclusion_reasons` returns **every** applicable reason (not
just the first), in a fixed canonical order. `is_valid` is true iff that list is
empty. Nothing here reads a clock or a database.
"""

from __future__ import annotations

# Window and thresholds (04 §5, 03 §1).
VALID_ELAPSED_MIN: int = 105
VALID_ELAPSED_MAX: int = 135
MIN_INTERMEAL_MIN: int = 180  # previous meal < 3 h prior contaminates IOB/COB
MIN_MACRO_CONFIDENCE: int = 50
HYPO_POST_BG_MAX: int = 80  # post_bg < 80 is State 1 or 2 (a measured low)

# Canonical order in which reasons are reported.
_REASON_ORDER = (
    "missing_outcome",
    "outside_window",
    "rescued",
    "uncontrolled_intake",
    "iob_cob_contamination",
    "low_confidence",
)


def exclusion_reasons(
    *,
    post_bg: int | None,
    elapsed_min: int | None,
    hypo_treatment: bool,
    snack_during_window: bool,
    minutes_since_prev_meal: int | None,
    macro_confidence: int,
) -> list[str]:
    """Every applicable exclusion reason, in canonical order."""
    reasons: set[str] = set()

    if post_bg is None:
        reasons.add("missing_outcome")
    if elapsed_min is not None and not (VALID_ELAPSED_MIN <= elapsed_min <= VALID_ELAPSED_MAX):
        reasons.add("outside_window")
    if hypo_treatment:
        reasons.add("rescued")
    if snack_during_window:
        reasons.add("uncontrolled_intake")
    if minutes_since_prev_meal is not None and minutes_since_prev_meal < MIN_INTERMEAL_MIN:
        reasons.add("iob_cob_contamination")
    if macro_confidence < MIN_MACRO_CONFIDENCE:
        reasons.add("low_confidence")

    return [r for r in _REASON_ORDER if r in reasons]


def is_valid(reasons: list[str]) -> bool:
    """A record is valid iff it has no exclusion reasons."""
    return not reasons


def is_hypo_outcome(post_bg: int | None) -> bool:
    """A measured low (State 1 or 2): post_bg present and below 80."""
    return post_bg is not None and post_bg < HYPO_POST_BG_MAX
