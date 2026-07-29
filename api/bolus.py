"""The bolus calculator screen — the sharpest end of the UI (S-1003, REQ-042/043).

**This module imports nothing from ``models``, and a test asserts it.** That is why the
calculator lives here rather than in ``api/app.py``, which imports ``models.metrics`` and
``models.shadow`` for the operator dashboard: *"no ML in the dose path"* has to be a fact
you can check by looking, not a promise in a docstring.

**It branches; it never catches.** ``recommend_bolus`` raises ``SafetyViolation`` below
BG 80 (INV-4) and ``ValueError`` on a missing/non-positive ICR (S-1011). Both refusing
states are decided *before* the calculator is called, so no partially-computed dose is ever
in scope to render. The invariants stay where they are, unreachable from here but standing
for every other caller — which is what makes them invariants rather than error handling.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from api.deps import get_session
from core.safety import BOLUS_BG_FLOOR
from data.repositories import active_profile, boluses_before, iob_at_start_at
from prescribe.bolus import BolusRecommendation, recommend_bolus

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


class CalculatorState(StrEnum):
    """The four states, and there is no fifth."""

    PROFILE_INCOMPLETE = "profile_incomplete"
    TREAT_THE_LOW_FIRST = "treat_the_low_first"
    SUGGESTION = "suggestion"


@dataclass(frozen=True)
class IobDisplay:
    """IOB **read-only, with its provenance** (REQ-020).

    Never an input. It is the one number on this screen where being plausibly wrong does
    direct harm: it is subtracted, so an underestimate raises the dose, and there is
    nothing to check it against the way carbs can be checked against the plate.
    """

    units: float
    n_recent_boluses: int
    source: str


@dataclass(frozen=True)
class CalculatorView:
    state: CalculatorState
    message: str
    iob: IobDisplay | None
    recommendation: BolusRecommendation | None


def build_calculator_view(
    session: Session, *, at: dt.datetime, carbs_g: float, current_bg: float
) -> CalculatorView:
    """Decide which of the three states this is, and compute only in the last one."""
    profile = active_profile(session)
    if profile is None or profile.icr is None or profile.icr <= 0.0:
        return CalculatorView(
            state=CalculatorState.PROFILE_INCOMPLETE,
            message=(
                "The ICR (grams of carbohydrate per unit) is not set on the profile, so "
                "there is nothing to calculate with. Set it on the profile first. "
                "This is a missing setting, not a safety hold."
            ),
            iob=None,
            recommendation=None,
        )

    # INV-4, decided here so `recommend_bolus` is never called in a state where it would
    # raise. The invariant remains as the backstop for every other caller.
    if current_bg < BOLUS_BG_FLOOR:
        return CalculatorView(
            state=CalculatorState.TREAT_THE_LOW_FIRST,
            message=(
                f"Your reading is {current_bg:g}. Treat the low first — nothing is "
                "calculated below "
                f"{BOLUS_BG_FLOOR:g}. Come back once you are back up."
            ),
            iob=None,
            recommendation=None,
        )

    iob_units = iob_at_start_at(session, at)
    iob = IobDisplay(
        units=iob_units,
        n_recent_boluses=len(boluses_before(session, at)),
        source="derived from your logged injections — never typed in",
    )
    return CalculatorView(
        state=CalculatorState.SUGGESTION,
        message="",
        iob=iob,
        recommendation=recommend_bolus(
            icr=profile.icr,
            isf=profile.isf,
            carbs_g=carbs_g,
            current_bg=current_bg,
            target_bg=float(profile.target_bg),
            iob=iob_units,
        ),
    )


@router.get("/bolus", response_class=HTMLResponse)
def bolus_calculator(
    request: Request,
    at: dt.datetime | None = None,
    carbs_g: float | None = None,
    current_bg: float | None = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """The calculator (05b §6, REQ-042/043, INV-3/INV-4).

    ``at`` is **reported** — when she is going to inject — and IOB is computed at that
    time. Defaulting it to the system clock would be the forbidden pattern in its most
    tempting form: nearly right at the table, and silently wrong every time the calculator
    is used afterwards, which is exactly when IOB matters most (ADR-8).

    Nothing here is logged and nothing is autofilled. The page is a rendered suggestion.
    """
    view = (
        build_calculator_view(session, at=at, carbs_g=carbs_g, current_bg=current_bg)
        if at is not None and carbs_g is not None and current_bg is not None
        else None
    )
    return templates.TemplateResponse(request, "bolus.html", {"view": view})
