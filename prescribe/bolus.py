"""The prescriptive bolus calculator — the sharpest end of the system (S-901, INV-1/3/4).

This is the only place that recommends putting insulin into a person who cannot feel a
low, so it is deliberately dumb: the standard clinical formula (07 §11), causal by
construction, **no model output anywhere in the path**. It is hard-gated on Gate 2 (a
clinician-confirmed ICR, INV-1); it refuses when she is already low (INV-4); it caps at
``MAX_BOLUS_U`` and **flags** an implausible input rather than silently dosing a typo
(INV-3); it is never negative (INV-3); and it shows its full working and frames itself as
a suggestion for review, never an instruction.

ICR / ISF / target come from the versioned ``patient_profile`` as parameters — there is no
clinical constant literal here, so they are updatable by a new profile version (DL-032).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from core.safety import (
    MAX_BOLUS_U,
    inv3_bolus_within_bounds,
    inv4_bolus_allowed_at_bg,
)
from prescribe.gates import gate2_status, require_gate2

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
    icr: float | None,
    isf: float,
    carbs_g: float,
    current_bg: float,
    target_bg: float,
    iob: float,
) -> BolusRecommendation:
    """Recommend a bolus using the clinical formula (07 §11) — **no ML**.

    Gate 2 (INV-1) is evaluated from the live ``icr`` first, with no bypass; ``icr = None``
    raises ``GateNotPassed``. Refuses below BG 80 (INV-4). Caps at ``MAX_BOLUS_U`` and flags
    an implausible input rather than silently clipping a typo (INV-3); never negative.
    """
    # INV-1: prescriptive module disabled until Gate 2 — live, first, no bypass. The gate
    # raises for a null/non-positive icr, so past this line icr is a confirmed positive.
    require_gate2(gate2_status(icr=icr))
    icr_confirmed = cast(float, icr)

    # INV-4: refuse to dose someone who is already low — treat the low first.
    inv4_bolus_allowed_at_bg(current_bg)

    # The standard clinical formula — causal arithmetic, no model output.
    carb_dose = carbs_g / icr_confirmed
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
        f"carb dose = {carbs_g:g} g / {icr_confirmed:g} = {carb_dose:.2f} U; "
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
