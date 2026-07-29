"""FastAPI app: serves the shared UI shell (S-102).

No clinical behaviour and no model output here — this module wires the base
Jinja2 layout, the vendored Pico.css and the accessible input primitives that
every later logging/readout story is built on. Binds to 127.0.0.1 only (see
06 §7); no auth in v1.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.bolus import router as bolus_router
from api.deps import get_session
from api.presenters import BaselineComparison, gate1_conditions, shadow_rows
from api.schemas import (
    AdherenceResponse,
    BasalCreate,
    BasalRecorded,
    CorrectionCreate,
    CorrectionCreated,
    CorrectionFollowup,
    CorrectionFollowupResult,
    MealCreate,
    MealCreated,
    PostBgResult,
    PostBgUpdate,
    ProfileVersionCreate,
    ProfileVersionCreated,
    PromotionRequest,
    PromotionResult,
)
from core.clock import SystemClock
from data.adherence import GATE1_VALID_MEALS, adherence_metrics
from data.basal import record_basal
from data.profile import append_profile_version, profile_history
from data.promotion import promote_model, revoke_promotion
from data.recording import (
    record_correction_event,
    record_correction_followup,
    record_hypo_rescue,
    record_meal,
    record_post_bg,
)
from data.repositories import (
    active_profile,
    annotate_validity,
    get_promoted_artifact,
    iob_at_start_at,
    shadow_days,
)
from data.tables import BolusLog, BolusType, CorrectionEvent, LoggedBy, MealEvent
from models.metrics import CalibrationVerdict
from models.shadow import ShadowReport
from prescribe.gates import Gate1Status, gate1_status
from prescribe.readout import PatientReadout

_TEST_DELAY_MIN = 120  # 05b §3.1 — "test your BG" prompt is reported mealtime + 120
_CORRECTION_FOLLOWUP_MIN = 240  # F-3.2 — correction +4 h follow-up BG

_BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app = FastAPI(title="BG-Markov", docs_url=None, redoc_url=None)
app.include_router(bolus_router)
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


@app.get("/meals/{meal_id}/post-bg", response_class=HTMLResponse)
def post_bg_form(
    meal_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """The <15s post-meal reading form (S-303). The reading time is reported and
    editable — asked, never assumed (REQ-011)."""
    meal = session.get(MealEvent, meal_id)
    if meal is None:
        raise HTTPException(status_code=404, detail="meal not found")
    expected = meal.datetime + dt.timedelta(minutes=_TEST_DELAY_MIN)
    return templates.TemplateResponse(
        request,
        "post_bg.html",
        {"meal_id": meal_id, "expected_reading_iso": expected.strftime("%Y-%m-%dT%H:%M")},
    )


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


@app.patch("/api/meals/{meal_id}/post-bg", response_model=PostBgResult)
def add_post_bg(
    meal_id: int, payload: PostBgUpdate, session: Session = Depends(get_session)
) -> PostBgResult:
    """Attach the post-meal reading (05 §1).

    ``post_bg_time`` is reported (required); ``elapsed_min`` is computed from the
    reported times (S-202), validity from `04 §5` (S-203). The record is stored
    **regardless** of validity — adherence cannot be diagnosed from discarded
    data (`03 §2`).
    """
    meal = session.get(MealEvent, meal_id)
    if meal is None:
        raise HTTPException(status_code=404, detail="meal not found")

    meal.hypo_treatment = payload.hypo_treatment
    meal.hypo_treatment_g = payload.hypo_treatment_g
    meal.snack_during_window = payload.snack_during_window
    record_post_bg(meal, post_bg=payload.post_bg, post_bg_time=payload.post_bg_time)

    # A rescue is a low. Append it to the independent ledger so INV-7 can
    # reconcile against a record that survives even a meal-row deletion (S-305).
    if payload.hypo_treatment:
        session.add(
            record_hypo_rescue(meal_id=meal.meal_id, grams=payload.hypo_treatment_g)
        )

    prev_meal_datetime = session.scalars(
        select(MealEvent.datetime)
        .where(MealEvent.datetime < meal.datetime)
        .order_by(MealEvent.datetime.desc())
    ).first()
    annotate_validity(meal, prev_meal_datetime)
    session.commit()

    reasons = meal.exclusion_reasons.split(",") if meal.exclusion_reasons else []
    return PostBgResult(
        meal_id=meal.meal_id,
        elapsed_min=meal.elapsed_min,
        is_valid=meal.is_valid,
        exclusion_reasons=reasons,
    )


@app.get("/corrections", response_class=HTMLResponse)
def corrections_form(request: Request) -> HTMLResponse:
    """Log a standalone correction — the clean ISF signal (S-306). No patient
    model output (INV-2 holds; nothing here predicts anything)."""
    return templates.TemplateResponse(request, "corrections.html")


@app.post("/api/correction-events", response_model=CorrectionCreated)
def create_correction_event(
    payload: CorrectionCreate, session: Session = Depends(get_session)
) -> CorrectionCreated:
    """Log a correction bolus taken with no meal (05 §3, REQ-013).

    The reported ``datetime`` is the injection time; the server never substitutes
    ``now()``. The injection is written to ``bolus_log`` (REQ-006) so S-401's IOB
    can see it. When no food is expected in the window, prompt a +4 h follow-up so
    the drop can be measured — the alarm time is the **reported** datetime + 4 h.
    """
    event = record_correction_event(
        reported_datetime=payload.datetime,
        bg_before=payload.bg_before,
        units=payload.units,
        food_in_window=payload.food_in_window,
    )
    # iob_at_start = IOB from PRIOR insulin at the correction moment (S-306b /
    # DL-020). Computed from bolus_log BEFORE the correction bolus is inserted, so
    # the intervention itself is never counted. `at` is the reported time bound to
    # a local — the value derives from the log, not from `payload` (keeps the
    # derived-IOB discipline; `detect_manual_iob` stays clean).
    at = payload.datetime
    event.iob_at_start = iob_at_start_at(session, at)
    session.add(event)
    session.add(
        BolusLog(
            datetime=payload.datetime,  # REPORTED
            logged_at=event.logged_at,
            units=payload.units,
            bolus_type=BolusType.correction,
            meal_id=None,
            logged_by=payload.logged_by,
        )
    )
    session.commit()

    if payload.food_in_window:
        return CorrectionCreated(
            event_id=event.event_id,
            prompt_followup=False,
            followup_at=None,
            message="Logged. Eating soon, so this is not a clean ISF reading.",
        )
    followup_at = payload.datetime + dt.timedelta(minutes=_CORRECTION_FOLLOWUP_MIN)
    alarm = followup_at.strftime("%I:%M %p").lstrip("0")
    return CorrectionCreated(
        event_id=event.event_id,
        prompt_followup=True,
        followup_at=followup_at,
        message=f"Not eating in the next 4 hours? Log a follow-up BG at {alarm}.",
    )


@app.patch(
    "/api/correction-events/{event_id}/followup", response_model=CorrectionFollowupResult
)
def add_correction_followup(
    event_id: int, payload: CorrectionFollowup, session: Session = Depends(get_session)
) -> CorrectionFollowupResult:
    """Attach the +4 h reading (05 §3). ``bg_after_time`` is reported;
    ``food_in_window`` is confirmed here (it decides ISF cleanliness, 07 §6)."""
    event = session.get(CorrectionEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="correction event not found")

    record_correction_followup(
        event,
        bg_after=payload.bg_after,
        bg_after_time=payload.bg_after_time,
        food_in_window=payload.food_in_window,
    )
    session.commit()
    return CorrectionFollowupResult(
        event_id=event.event_id,
        bg_after=payload.bg_after,  # just written; typed int (column is nullable)
        food_in_window=event.food_in_window,
    )


@app.get("/api/adherence", response_model=AdherenceResponse)
def adherence(session: Session = Depends(get_session)) -> AdherenceResponse:
    """Operator adherence metrics (05 §, REQ-053). Operator-only — no model
    output, so INV-2 is not in play. ``now`` is the system clock (days-since-log)."""
    m = adherence_metrics(session, now=SystemClock().now())
    return AdherenceResponse(
        n_meals=m.n_meals,
        valid_meals=m.valid_meals,
        meals_to_gate1=m.meals_to_gate1,
        in_window_rate=m.in_window_rate,
        exclusions_by_reason=m.exclusions_by_reason,
        days_since_last_log=m.days_since_last_log,
        median_lag_min=m.median_lag_min,
    )


@app.get("/operator", response_class=HTMLResponse)
def operator_dashboard(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """The operator adherence dashboard (05b §7.1, S-307). Operator-only; not in
    the patient nav. Shows adherence numbers only — no model output here."""
    m = adherence_metrics(session, now=SystemClock().now())
    return templates.TemplateResponse(
        request,
        "operator.html",
        {"m": m, "gate1_target": GATE1_VALID_MEALS},
    )


def load_shadow_evidence(
    session: Session,
) -> tuple[ShadowReport | None, BaselineComparison, CalibrationVerdict | None]:
    """What Gate-1 evidence currently exists (S-1001a).

    The DB boundary for the report card. It answers *"what evidence is there?"* — never
    *"may she see it?"*, which is Gate 1's job on an entirely different surface (INV-2,
    S-1002).

    **Today it returns nothing, and that is correct.** A shadow report needs predictions
    with their outcomes backfilled (`prediction_log.actual_state`) and a scored model; no
    model has been promoted and no meal has been logged. Rather than fabricate a report to
    make the page look populated, the page renders an explicit empty state. Scoring a live
    model from `prediction_log` arrives with the refit story (S-1009).
    """
    if get_promoted_artifact(session) is None:
        return None, BaselineComparison(), None
    return None, BaselineComparison(), None


@app.get("/operator/shadow", response_class=HTMLResponse)
def operator_shadow(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """The operator's Gate-1 evidence screen (05b §7.2, S-1001a, REQ-055).

    Operator-only; not in the patient nav. **No dose appears here** and no plain-accuracy
    figure exists anywhere on it. Gate 1 is read live (ADR-7) and all five of its
    conditions are shown, met or not — a checklist that hides the unmet ones looks
    complete when it is not.
    """
    report, baseline, calibration = load_shadow_evidence(session)
    status = _live_gate1(session)
    promoted = get_promoted_artifact(session)
    return templates.TemplateResponse(
        request,
        "operator_shadow.html",
        {
            "rows": shadow_rows(report=report, baseline=baseline, calibration=calibration),
            "report": report,
            "gate1": status,
            "conditions": gate1_conditions(status, has_model=report is not None),
            "states": (1, 2, 3, 4, 5),
            "promoted_version": promoted.version if promoted else None,
        },
    )


def _live_gate1(session: Session) -> Gate1Status:
    """Evaluate Gate 1 from live data (ADR-7). One place, so the page and the endpoint can
    never disagree about what is true right now."""
    report, baseline, calibration = load_shadow_evidence(session)
    metrics = adherence_metrics(session, now=SystemClock().now())
    return gate1_status(
        valid_meals=metrics.valid_meals,
        model_hypo_recall=report.hypo_recall.recall if report else 0.0,
        baseline_hypo_recall=baseline.hypo_recall or 0.0,
        is_promoted=get_promoted_artifact(session) is not None,
        shadow_days=shadow_days(session, now=SystemClock().now()),
        calibration_ok=bool(calibration and calibration.is_acceptable),
    )


@app.post("/api/operator/promote", response_model=PromotionResult)
def operator_promote(
    payload: PromotionRequest, session: Session = Depends(get_session)
) -> PromotionResult:
    """**[SAFETY]** Open Gate 1 (S-1001b, REQ-058, `05 §6`). The only door it has.

    **The gate is re-evaluated here, from live data.** The UI disables the button when the
    conditions are unmet; that is a courtesy, not a control. Anything reaching this URL — a
    stale tab, a half-finished script, a future bug — meets the same bar, because the check
    lives at the point of effect.

    ★ **The precondition is ``automatic_conditions_met``, NOT ``is_open``.** ``is_promoted``
    is itself one of Gate 1's five conditions, so ``is_open`` is false *by definition* at
    the moment of promotion; gating on it would refuse every promotion forever, including
    the correct one, and a gate that can never open reads as caution rather than as a bug.

    Refuses with **409** naming *every* unmet condition — a refusal that reveals one blocker
    at a time teaches the operator to treat the gate as an obstacle course, when the honest
    reading is a description of what is not yet true.
    """
    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "CONFIRMATION_REQUIRED",
                "message": (
                    "Promotion needs an explicit yes. This puts her in front of the model."
                ),
            },
        )

    status = _live_gate1(session)
    if not status.automatic_conditions_met:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "PRECONDITIONS_NOT_MET",
                "failed": [c for c in status.failed_conditions if c != "promotion"],
                "message": "Good numbers are not permission, and these are not good yet.",
            },
        )

    try:
        promote_model(session, payload.model_version, confirmed_by=LoggedBy.operator)
    except ValueError as exc:  # unknown version — refuse, create nothing
        raise HTTPException(
            status_code=404, detail={"error": "UNKNOWN_MODEL_VERSION", "message": str(exc)}
        ) from exc
    return PromotionResult(model_version=payload.model_version, is_promoted=True)


@app.post("/api/operator/revoke", response_model=PromotionResult)
def operator_revoke(
    payload: PromotionRequest, session: Session = Depends(get_session)
) -> PromotionResult:
    """**[SAFETY]** Shut Gate 1 (S-1001b, `05 §6`).

    ★ **No preconditions. Ever.** A gate you cannot shut is not a gate. The failure this
    system is built around is a model that looks good, gets trusted, and is quietly wrong
    about a low — so the response to that suspicion must never be blocked by a precondition
    check, least of all the check that the model still looks fine.

    Takes effect on the next call (gates are live, ADR-7). Audited like promotion.
    """
    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail={"error": "CONFIRMATION_REQUIRED", "message": "Revocation needs a yes."},
        )
    try:
        revoke_promotion(session, payload.model_version, confirmed_by=LoggedBy.operator)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"error": "UNKNOWN_MODEL_VERSION", "message": str(exc)}
        ) from exc
    return PromotionResult(model_version=payload.model_version, is_promoted=False)


def load_patient_readout(session: Session, meal: MealEvent) -> PatientReadout | None:
    """The readout for a logged meal, or ``None`` when there is nothing to say (S-1002).

    **Today it returns ``None``, and that is correct.** Gate 1 is closed, so there is no
    patient-visible model output (INV-2, `03 §3` — *"Logging only. No model. No output."*).
    The live path — features → promoted model → guardrails → persist (INV-9) → serve —
    exists in `prescribe/serving.py` (S-1008) and is wired in once a model is promoted.

    It returns ``None`` rather than raising, because the *route* must not be in the business
    of catching a safety exception and deciding what to render instead.
    """
    return None


@app.get("/meals/{meal_id}/readout", response_class=HTMLResponse)
def patient_readout(
    meal_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """What she sees about a meal (05b §5, REQ-040, INV-2, S-1002).

    ★ **Two branches, no third.** With Gate 1 closed this renders an honest "nothing yet"
    state and **never constructs a readout at all** — ``build_patient_readout`` is not
    called, so there is no object to accidentally render. The alternative, catching
    ``GateNotPassed`` and rendering the best available thing, would put a rendering
    decision downstream of a safety exception; the next refactor catches it more broadly
    and something leaks.

    On the open path the gate is checked **twice** — here, and as the first line of
    ``build_patient_readout`` (S-804). That is deliberate: the builder's check is the one a
    future second caller cannot forget.

    **No dose ever appears on this page.** `PatientReadout` has no such field, and a test
    asserts no dose-like word appears in the template source either.
    """
    meal = session.get(MealEvent, meal_id)
    if meal is None:
        raise HTTPException(status_code=404, detail="meal not found")

    gate1 = _live_gate1(session)
    readout = load_patient_readout(session, meal) if gate1.is_open else None
    return templates.TemplateResponse(request, "readout.html", {"readout": readout})


@app.get("/basal", response_class=HTMLResponse)
def basal_form(request: Request) -> HTMLResponse:
    """The daily-Tresiba form (S-1013, REQ-007). Two fields: how much, and **when she
    took it** — the reported time, never assumed (ADR-8)."""
    return templates.TemplateResponse(request, "basal.html")


@app.post("/api/basal", response_model=BasalRecorded)
def create_basal(
    payload: BasalCreate, session: Session = Depends(get_session)
) -> BasalRecorded:
    """Record or correct the daily basal dose (S-1013, REQ-007).

    Re-posting a date is a **correction**, audited old → new — not a second dose.
    ``time_taken`` is required by the schema, so the server never has to invent one.
    """
    row = record_basal(
        session,
        date=payload.date,
        units=payload.units,
        time_taken=payload.time_taken,
        logged_by=payload.logged_by,
        clock=SystemClock(),
    )
    session.commit()
    return BasalRecorded(date=row.date, units=row.units)


@app.get("/operator/profile", response_class=HTMLResponse)
def operator_profile(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """The clinical constants and their history (S-1010, REQ-054/REQ-061).

    The history is **shown, not merely kept**: versioning is the whole point of this screen,
    and a previous value on the page is what makes "never overwrite" visible rather than a
    claim in a docstring.
    """
    return templates.TemplateResponse(
        request,
        "profile.html",
        {"current": active_profile(session), "history": profile_history(session)},
    )


@app.post("/api/operator/profile", response_model=ProfileVersionCreated)
def create_profile_version(
    payload: ProfileVersionCreate, session: Session = Depends(get_session)
) -> ProfileVersionCreated:
    """Append a new profile version (S-1010, REQ-061, `05 §6`).

    **Appends, never updates.** Returns any flags rather than refusing on them — a
    validation result nobody can see is not a warning (DL-048).
    """
    result = append_profile_version(
        session,
        effective_from=payload.effective_from,
        icr=payload.icr,
        isf=payload.isf,
        target_bg=payload.target_bg,
        changed_by=LoggedBy.operator,
    )
    session.commit()
    return ProfileVersionCreated(
        effective_from=payload.effective_from, icr=payload.icr, isf=payload.isf,
        target_bg=payload.target_bg, flags=[f.value for f in result.flags],
    )
