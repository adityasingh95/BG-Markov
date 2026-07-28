"""The prescriptive bolus calculator — the sharpest end of the system (S-901, INV-1/3/4).

This is the only place that recommends putting insulin into a person who cannot feel a
low, so it is deliberately dumb: the standard clinical formula (07 §11), causal by
construction, **no model output anywhere in the path**. It refuses when she is already low
(INV-4); it caps at ``MAX_BOLUS_U`` and **flags** an implausible input rather than silently
dosing a typo (INV-3); it is never negative (INV-3); and it shows its full working and
frames itself as a suggestion for review, never an instruction.

ICR / ISF / target come from the versioned ``patient_profile`` as parameters — there is no
clinical constant literal here, so they are updatable by a new profile version (DL-032).

**Gate 2 / INV-1 retired (S-1011, DL-035).** The prescriptive module is no longer gated on
a clinician-confirmed ICR. The ICR is a required *input*: because the formula divides by
it, a missing or non-positive value raises a plain ``ValueError`` — an ordinary input
error, deliberately **not** a ``SafetyViolation``. What still bounds this function is
INV-3 and INV-4; what still governs whether she sees any model output is Gate 1 / INV-2,
which is untouched. See ``docs/stories/S-1011.md`` for the written safety argument.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.safety import (
    MAX_BOLUS_U,
    inv3_bolus_within_bounds,
    inv4_bolus_allowed_at_bg,
)

_FRAMING = "A suggestion for review — check the arithmetic. Not an instruction."


@dataclass(frozen=True)
class BolusRecommendation:
    """A bolus suggestion with its full working shown. ``capped``/``implausible_input``
    flag an over-cap event (INV-3) so a typo is surfaced, never silently dosed."""

    total_units: float
    carb_dose: float
    correction_dose: float
    iob_subtracted: float
    capped: bool
    implausible_input: bool
    arithmetic: str
    framing: str


def recommend_bolus(
    *,
    icr: float,
    isf: float,
    carbs_g: float,
    current_bg: float,
    target_bg: float,
    iob: float,
) -> BolusRecommendation:
    """Recommend a bolus using the clinical formula (07 §11) — **no ML**.

    Raises ``ValueError`` if ``icr`` is missing or non-positive (the formula divides by
    it) — an ordinary input error, **not** a ``SafetyViolation``; Gate 2 / INV-1 is retired
    (S-1011). Refuses below BG 80 (INV-4). Caps at ``MAX_BOLUS_U`` and flags an implausible
    input rather than silently clipping a typo (INV-3); never negative.
    """
    # The ICR is a divisor: reject a missing/nonsensical one BEFORE any arithmetic, so the
    # dose can never be inf, nan, or negative-by-division. Ordinary input validation.
    if icr is None or icr <= 0.0:  # `is None` guards runtime callers, not just typing
        raise ValueError(
            f"icr must be a positive number of grams per unit; got {icr!r}. "
            "Set it on the patient profile before using the calculator."
        )

    # INV-4: refuse to dose someone who is already low — treat the low first.
    inv4_bolus_allowed_at_bg(current_bg)

    # The standard clinical formula — causal arithmetic, no model output.
    carb_dose = carbs_g / icr
    correction_dose = (current_bg - target_bg) / isf
    raw = carb_dose + correction_dose - iob
    dose = max(0.0, raw)  # INV-3: never negative

    # INV-3: an over-cap dose is an IMPLAUSIBLE INPUT (e.g. a carbs typo), flagged — not a
    # silent clip that hands back a confident lethal-looking 15 U.
    implausible = dose > MAX_BOLUS_U
    capped = implausible
    if implausible:
        dose = MAX_BOLUS_U
    inv3_bolus_within_bounds(dose)  # final belt-and-braces: 0 <= dose <= MAX_BOLUS_U

    arithmetic = (
        f"carb dose = {carbs_g:g} g / {icr:g} = {carb_dose:.2f} U; "
        f"correction = ({current_bg:g} - {target_bg:g}) / {isf:g} = {correction_dose:.2f} U; "
        f"minus IOB {iob:g} U → {raw:.2f} U → {dose:.2f} U"
        + (" (CAPPED — input looks implausible, please re-check)" if capped else "")
    )
    return BolusRecommendation(
        total_units=dose,
        carb_dose=carb_dose,
        correction_dose=correction_dose,
        iob_subtracted=iob,
        capped=capped,
        implausible_input=implausible,
        arithmetic=arithmetic,
        framing=_FRAMING,
    )
