"""ISF derivation from clean correction events (S-502, 07 §6).

ISF is the most dangerous number in the system — it sits in the denominator of the
correction term, and an ISF that is too low over-doses. This derives it from the
only unconfounded data (standalone corrections with no food, negligible prior IOB),
behind three guards: a >=5-event gate, a never-silent-swap contract (both the
current and derived value are returned), and a hard stop on any non-positive result.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from statistics import mean

from core.safety import SafetyViolation

MIN_CLEAN_EVENTS = 5  # 07 §6 — fewer than this may not override the default


@dataclass(frozen=True)
class ISFResult:
    n_clean: int
    derived_isf: float | None  # the derived value (reported even when not applied)
    applied: bool              # True iff n_clean >= MIN_CLEAN_EVENTS
    isf: float                 # the ISF to use (current unless applied)
    isf_source: str            # "derived" iff applied, else the incoming source
    events_needed: int = MIN_CLEAN_EVENTS


def derive_isf(
    triples: Iterable[tuple[float, float, float]],
    *,
    current_isf: float,
    current_source: str,
) -> ISFResult:
    """Derive ISF from ``(bg_before, bg_after, units)`` triples of clean events.

    ``derived = mean((bg_before − bg_after)/units)``. Raises ``SafetyViolation`` if
    the derived value is non-positive (insulin appearing not to lower glucose).
    Applies only at ``>= MIN_CLEAN_EVENTS``; otherwise the current ISF/source are
    kept and the derived value is merely reported — never a silent swap.
    """
    events = list(triples)
    n = len(events)
    if n == 0:
        return ISFResult(0, None, False, current_isf, current_source)

    derived = mean((before - after) / units for before, after, units in events)
    if derived <= 0.0:
        raise SafetyViolation(
            f"S-502: derived ISF {derived} <= 0 — insulin cannot raise glucose; "
            "refusing to derive from this data"
        )

    if n >= MIN_CLEAN_EVENTS:
        return ISFResult(n, derived, True, derived, "derived")
    return ISFResult(n, derived, False, current_isf, current_source)
