"""FastAPI app: serves the shared UI shell (S-102).

No clinical behaviour and no model output here — this module wires the base
Jinja2 layout, the vendored Pico.css and the accessible input primitives that
every later logging/readout story is built on. Binds to 127.0.0.1 only (see
06 §7); no auth in v1.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import MealCreate, MealCreated
from data.recording import record_meal
from data.tables import BolusLog, BolusType

_TEST_DELAY_MIN = 120  # 05b §3.1 — "test your BG" prompt is reported mealtime + 120

_BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app = FastAPI(title="BG-Markov", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

# Seeded favourite meals — the adherence mechanism (05b §3). Tapping one
# populates all macros so a repeat meal is a few taps. Persisting favourite meal
# combos as a table is a later refinement (see decision log); the value S-301
# delivers is the tap-to-populate flow.
FAVOURITES: list[dict[str, object]] = [
    {"name": "Dal + 2 roti + sabzi", "meal_type": "lunch",
     "carbs_g": 40.0, "protein_g": 15.0, "fat_g": 13.0, "fiber_g": 11.0},
    {"name": "Rice + rajma", "meal_type": "lunch",
     "carbs_g": 75.0, "protein_g": 13.0, "fat_g": 3.5, "fiber_g": 9.0},
    {"name": "2 idli + sambar", "meal_type": "breakfast",
     "carbs_g": 44.0, "protein_g": 7.0, "fat_g": 4.6, "fiber_g": 6.0},
]


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """The meal-log form (S-301). Shows no model output — nothing patient-visible
    before Gate 1 (INV-2). The accessible-primitives gallery lives at /components.
    """
    return templates.TemplateResponse(request, "index.html", {"favourites": FAVOURITES})


@app.get("/components", response_class=HTMLResponse)
def components(request: Request) -> HTMLResponse:
    """Reference gallery of the accessible primitives (incl. the risk-cue
    pattern). Not patient-facing; keeps model-output examples off the form."""
    return templates.TemplateResponse(request, "components.html")


@app.post("/api/meals", response_model=MealCreated)
def create_meal(payload: MealCreate, session: Session = Depends(get_session)) -> MealCreated:
    """Log a meal (05 §1).

    Clinical timestamps are the client's reported values; the server stamps
    ``logged_at`` (via the S-202 reported-time path) and never substitutes
    ``now()``. ``bolus_offset_min`` being required is enforced by ``MealCreate``
    (422 if absent). Returns ``test_at`` = reported ``datetime`` + 120 min.
    """
    # The bolus injection time is the reported mealtime shifted by the reported
    # offset (negative = pre-bolus). No system clock enters a clinical timestamp.
    bolus_datetime = payload.datetime + dt.timedelta(minutes=payload.bolus_offset_min)

    meal = record_meal(
        reported_datetime=payload.datetime,
        meal_type=payload.meal_type,
        pre_bg=payload.pre_bg,
        pre_bg_time=payload.pre_bg_time,
        meal_bolus_units=payload.meal_bolus_units,
        bolus_datetime=bolus_datetime,
        carbs_g=payload.carbs_g,
        logged_by=payload.logged_by,
    )
    meal.protein_g = payload.protein_g
    meal.fat_g = payload.fat_g
    meal.fiber_g = payload.fiber_g
    meal.macro_confidence = payload.macro_confidence
    meal.correction_bolus_units = payload.correction_bolus_units
    meal.notes = payload.notes
    session.add(meal)
    session.flush()  # assign meal_id

    for units, kind in (
        (payload.meal_bolus_units, BolusType.meal),
        (payload.correction_bolus_units, BolusType.correction),
    ):
        if units > 0:
            session.add(
                BolusLog(
                    datetime=bolus_datetime,
                    logged_at=meal.logged_at,
                    units=units,
                    bolus_type=kind,
                    meal_id=meal.meal_id,
                    logged_by=payload.logged_by,
                )
            )
    session.commit()

    test_at = payload.datetime + dt.timedelta(minutes=_TEST_DELAY_MIN)
    alarm = test_at.strftime("%I:%M %p").lstrip("0")
    return MealCreated(
        meal_id=meal.meal_id,
        test_at=test_at,
        message=f"Logged. Set a phone alarm for {alarm} to test.",
    )
