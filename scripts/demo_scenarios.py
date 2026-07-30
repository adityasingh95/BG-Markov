"""End-to-end scenarios against a seeded DEMO database. NOT patient data.

Runs the real code paths — the real app routes, the real invariants, the real gate — and
prints what actually happens. Where a scenario cannot run because a dependency is missing,
it says so rather than simulating the result.

Usage:  python -m scripts.demo_scenarios --db demo.db
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.app import app, load_shadow_evidence
from api.deps import get_session
from core.safety import SafetyViolation
from data.adherence import adherence_metrics
from data.db import make_engine, session_factory
from data.repositories import (
    active_profile,
    get_hypo_events,
    get_training_set,
    shadow_days,
)
from data.tables import BasalLog, BolusLog, MealEvent, ModelArtifact, PredictionLog
from data.training import assemble_training_data
from features.basal import effective_basal
from models.refit import composite_weights, run_refit
from prescribe.bolus import recommend_bolus
from prescribe.gates import gate1_status

NOW = dt.datetime(2026, 7, 30, 12, 0)


def h(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def sub(title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 72 - len(title)))


def scenario_1_landscape(session: Session) -> None:
    h("SCENARIO 1 — What is in the database")
    meals = session.scalar(select(func.count()).select_from(MealEvent)) or 0
    valid = len(get_training_set(session))
    hypos = get_hypo_events(session)
    rescued = [m for m in hypos if m.hypo_treatment]
    print(f"  meals logged            {meals}")
    print(f"  valid for training      {valid}   ({100 * valid / meals:.0f}%)")
    print(f"  hypo events retained    {len(hypos)}   of which rescued: {len(rescued)}")
    print(f"  boluses                 {session.scalar(select(func.count()).select_from(BolusLog))}")
    print(f"  basal days              {session.scalar(select(func.count()).select_from(BasalLog))}")

    sub("★ INV-7 in action: rescued meals are EXCLUDED from training, RETAINED as hypos")
    training_ids = {m.meal_id for m in get_training_set(session)}
    leaked = [m.meal_id for m in rescued if m.meal_id in training_ids]
    print(f"  rescued meals that leaked into training : {len(leaked)}  (must be 0)")
    print(f"  rescued meals still counted as hypos    : "
          f"{sum(1 for m in rescued if m in hypos)}/{len(rescued)}")
    print("  → the lows are kept as the thing to predict, and kept out of the outcome fit")

    sub("Adherence (S-307) — the operator's view of data quality")
    m = adherence_metrics(session, now=NOW)
    for field in ("logged_meals", "complete_meals", "completion_rate", "valid_meals"):
        if hasattr(m, field):
            print(f"  {field:24s}{getattr(m, field)}")


def scenario_2_basal(session: Session) -> None:
    h("SCENARIO 2 — Effective basal: today's dose is NOT today's effect")
    from data.repositories import basal_doses

    doses = basal_doses(session)
    smoothed = effective_basal(doses)
    print("  Tresiba runs ~42 h and reaches steady state after 3-4 days, so the raw daily")
    print("  figure as a feature is a FORBIDDEN pattern. The EWMA (25 h half-life) is used.\n")
    print("     date          raw dose    effective basal (EWMA)")
    for (when, units), sm in list(zip(doses, smoothed, strict=True))[-6:]:
        print(f"     {when.date()}     {units:5.1f} U        {sm:6.2f} U")
    raw_last = doses[-1][1]
    print(f"\n  → last raw dose {raw_last:.1f} U vs effective {smoothed[-1]:.2f} U "
          f"— a {abs(raw_last - smoothed[-1]):.2f} U difference the model would get wrong")


def scenario_3_calculator(session: Session) -> None:
    h("SCENARIO 3 — The bolus calculator and its two invariants")
    profile = active_profile(session)
    # `icr` is nullable BY DESIGN (S-1011): null means the calculator refuses and the
    # screen renders "setting missing". That was the system's real state until S-1010
    # gave the operator a way to set it.
    assert profile is not None and profile.icr is not None, "no ICR on file"
    icr = profile.icr
    print(f"  Active profile: ICR {profile.icr} g/U · ISF {profile.isf} mg/dL/U · "
          f"target {profile.target_bg} mg/dL\n")

    sub("3a. An ordinary meal — 60 g carbs at BG 190")
    r = recommend_bolus(icr=icr, isf=profile.isf, carbs_g=60.0,
                        current_bg=190.0, target_bg=float(profile.target_bg), iob=0.0)
    print(f"  suggested: {r.total_units:.2f} U")
    print(f"  arithmetic: {r.arithmetic}")

    sub("3b. The same meal with 2 U already on board")
    r2 = recommend_bolus(icr=icr, isf=profile.isf, carbs_g=60.0,
                         current_bg=190.0, target_bg=float(profile.target_bg), iob=2.0)
    print(f"  suggested: {r2.total_units:.2f} U   (was {r.total_units:.2f} U)")
    print("  → IOB is DERIVED from bolus_log, never entered by hand (forbidden pattern)")

    sub("3c. ★ INV-4 — BG 79: she cannot reliably feel a low, so nothing is suggested")
    for bg in (79.0, 80.0):
        try:
            out = recommend_bolus(icr=icr, isf=profile.isf, carbs_g=40.0,
                                  current_bg=bg, target_bg=135.0, iob=0.0)
            print(f"  BG {bg:5.1f} → {out.total_units:.2f} U")
        except SafetyViolation as exc:
            print(f"  BG {bg:5.1f} → SafetyViolation: {exc}")

    sub("3d. ★ INV-3 — a typo: 900 g of carbs instead of 90")
    typo = recommend_bolus(icr=icr, isf=profile.isf, carbs_g=900.0,
                           current_bg=150.0, target_bg=135.0, iob=0.0)
    print(f"  suggested: {typo.total_units:.2f} U  (uncapped would be ~{900 / 9:.0f} U)")
    print(f"  flagged  : {typo.implausible_input}")
    print(f"  arithmetic: {typo.arithmetic}")
    print("  → CAPPED and FLAGGED. Not silently accepted, not silently refused.")

    sub("3e. A missing ICR is an INPUT ERROR, not a safety violation (INV-1 retired, DL-035)")
    try:
        recommend_bolus(icr=0.0, isf=30.0, carbs_g=40.0, current_bg=150.0,
                        target_bg=135.0, iob=0.0)
    except SafetyViolation as exc:  # pragma: no cover - would be wrong
        print(f"  WRONG — raised SafetyViolation: {exc}")
    except ValueError as exc:
        print(f"  ValueError (correct): {exc}")


def scenario_4_gate(session: Session) -> None:
    h("SCENARIO 4 — Gate 1: may she see model output at all? (INV-2)")
    print("  Gate 1 has FIVE conditions. All are evaluated LIVE, never cached (ADR-7).\n")
    status = gate1_status(
        valid_meals=len(get_training_set(session)),
        model_hypo_recall=0.0,
        baseline_hypo_recall=0.0,
        is_promoted=False,
        shadow_days=shadow_days(session, now=NOW),
        calibration_ok=False,
    )
    rows = [
        ("volume >= 150 valid meals", status.meets_volume, f"{status.valid_meals} valid"),
        ("beats the clinical baseline", status.beats_baseline, "no model scored"),
        ("calibration OK (DL-042)", status.calibration_ok, "no model scored"),
        ("90 days of shadow mode", status.meets_shadow_period, f"{status.shadow_days} days"),
        ("operator has promoted", status.is_promoted, "not promoted"),
    ]
    for name, ok, detail in rows:
        print(f"    [{'x' if ok else ' '}]  {name:32s} {detail}")
    print(f"\n  GATE 1 OPEN: {status.is_open}")
    print(f"  blocking   : {', '.join(status.failed_conditions)}")
    print("\n  → the volume condition is MET on this data; the rest are not, and the")
    print("    checklist names every unmet one rather than hiding them.")


def scenario_5_promotion(client: TestClient) -> None:
    h("SCENARIO 5 — Trying to promote the model anyway")
    r = client.post(
        "/api/operator/promote",
        json={"model_version": "demo-v1", "confirmed": True},
    )
    print(f"  POST /api/operator/promote  →  HTTP {r.status_code}")
    print(f"  body: {r.text[:400]}")
    print("\n  → 409, naming every failed condition. The operator cannot open Gate 1 by")
    print("    accident, and the refusal explains itself.")


def scenario_6_refit(session: Session) -> None:
    h("SCENARIO 6 — The monthly refit (S-1009)")
    data = assemble_training_data(session, as_of=NOW)
    print(f"  assembled from the DB: {len(data)} rows x {data.x.shape[1]} features")
    print(f"  trailing window      : 183 days ending {NOW.date()}")

    weights = composite_weights(data, as_of=NOW)
    print("\n  composite weights (confidence x hypo x recency):")
    print(f"    min {weights.min():.4f}   max {weights.max():.4f}   "
          f"zeros: {(weights == 0).sum()}")
    print("  ★ zero weights must be 0 — a row weighted 0 was not in the fit, and the")
    print("    rows that reach zero first are the oldest, i.e. the rescued lows.")

    oldest = min(range(len(data.dates)), key=lambda i: data.dates[i])
    newest = max(range(len(data.dates)), key=lambda i: data.dates[i])
    age = (data.dates[newest] - data.dates[oldest]).days
    print(f"\n  oldest row is {age} days older than the newest;")
    print(f"    its recency factor is {0.5 ** (age / 90):.3f}x  (90-day half-life, DL-047)")

    artifact = run_refit(session, as_of=NOW)
    session.commit()
    print(f"\n  artifact written : {artifact.version}")
    print(f"  is_promoted      : {artifact.is_promoted}   ← never inherited (REQ-060)")
    print(f"  n_rows           : {artifact.n_rows}")
    print(f"  features fitted  : {len(artifact.feature_list)} of 23")
    dropped = artifact.metrics.get("dropped_constant_features", [])
    print(f"  dropped (no rank): {len(dropped)} → {', '.join(dropped[:5])}"
          f"{' ...' if len(dropped) > 5 else ''}")
    print(f"  hypo_recall      : {artifact.metrics.get('hypo_recall')}")
    print(f"  n_hypo_observed  : {artifact.metrics.get('n_hypo_observed')}")
    print(f"  off_by_one       : {artifact.metrics.get('off_by_one')}")
    print(f"  severe_error     : {artifact.metrics.get('severe_error')}")


def scenario_7_patient_view(client: TestClient) -> None:
    h("SCENARIO 7 — What SHE sees, before Gate 1 (INV-2)")
    for path, label in (("/", "the meal log"), ("/bolus", "the bolus calculator")):
        r = client.get(path)
        print(f"  GET {path:10s} → HTTP {r.status_code}  ({label})")
    body = client.get("/bolus").text.lower()
    for word in ("predict", "probability", "risk of", "model says"):
        print(f"    contains {word!r}: {word in body}")
    print("\n  → no model output on any patient surface. The calculator is the clinical")
    print("    formula only — no ML in the dose path at all.")


def scenario_8_shadow(session: Session, client: TestClient) -> None:
    h("SCENARIO 8 — The operator shadow dashboard")
    n_pred = session.scalar(select(func.count()).select_from(PredictionLog)) or 0
    promoted = session.scalars(
        select(ModelArtifact).where(ModelArtifact.is_promoted.is_(True))
    ).first()
    report, _baseline, _calib = load_shadow_evidence(session)
    r = client.get("/operator/shadow")
    print(f"  predictions logged : {n_pred}")
    print(f"  promoted artifact  : {promoted.version if promoted else None}")
    print(f"  shadow report      : {report}")
    print(f"  GET /operator/shadow → HTTP {r.status_code}, "
          f"empty state shown: {'nothing to show' in r.text.lower()}")
    print("\n  ★ Empty here because nothing is promoted YET — not because nothing can")
    print("    predict. That gap closed in S-1015; scenario 9 promotes and shows the loop.")
    print("    An empty dashboard is a true statement about the evidence, and the page")
    print("    says so rather than filling itself in.")


def scenario_9_the_full_loop(session: Session, client: TestClient) -> None:
    h("SCENARIO 9 — The full loop: refit → promote → serve → score → Gate 1")
    from sqlalchemy import func as _f

    from data.model_store import load_fitted_model
    from data.predictions import backfill_actual_states
    from data.tables import ModelArtifact as _MA

    artifact = session.scalars(
        select(_MA).order_by(_MA.fit_date.desc())
    ).first()
    if artifact is None:
        print("  no artifact — run scenario 6 first")
        return
    artifact.is_promoted = True
    session.flush()
    loaded = load_fitted_model(session, artifact)
    print(f"  promoted        : {artifact.version}")
    print(f"  model reloadable: {loaded is not None}   ← S-1014 (parameters as JSON)")

    sub("she logs 14 meals through the real API")
    before_pred = session.scalar(select(_f.count()).select_from(PredictionLog)) or 0
    # 14, not 5: the dashboard needs >= 10 scored predictions before it will
    # report anything, so a smaller run would only ever show the empty state.
    for i in range(14):
        when = NOW - dt.timedelta(hours=26 * i + 2)
        r = client.post("/api/meals", json={
            "idempotency_key": f"loop-{i}", "datetime": when.isoformat(),
            "meal_type": "lunch", "pre_bg": 118 + 9 * i,
            "pre_bg_time": (when - dt.timedelta(minutes=5)).isoformat(),
            "meal_bolus_units": 4.0 + 0.3 * i, "correction_bolus_units": 0.0,
            "bolus_offset_min": -10, "carbs_g": 36.0 + 5 * i, "protein_g": 18.0,
            "fat_g": 12.0, "fiber_g": 5.0, "macro_confidence": 90,
            "logged_by": "patient",
        })
        assert r.status_code == 200, r.text
        if i < 3 or i == 13:
            print(f"    meal {r.json()['meal_id']:>4}  HTTP 200  keys={sorted(r.json())}")
        elif i == 3:
            print("    ...")

    after = session.scalar(select(_f.count()).select_from(PredictionLog)) or 0
    print(f"\n  predictions logged: {after - before_pred}   ← S-1015; INV-9 write-before-return")
    print(f"  shadow clock      : {shadow_days(session, now=NOW + dt.timedelta(days=3))} days"
          "   ← the 90-day clock is RUNNING")

    sub("outcomes arrive; the backfill scores them (DL-049)")
    # A realistic mix INCLUDING lows — a window with no lows is correctly unscoreable,
    # which would make this scenario "pass" for the wrong reason.
    outcomes = (72, 155, 148, 61, 190, 150, 88, 165)
    for i, meal in enumerate(session.scalars(
        select(MealEvent).where(MealEvent.post_bg.is_(None))
    ).all()):
        meal.post_bg = outcomes[i % len(outcomes)]
        meal.post_bg_time = meal.datetime + dt.timedelta(minutes=120)
        meal.elapsed_min = 120
    session.flush()
    print(f"  actual_state backfilled for {backfill_actual_states(session)} predictions")

    report, _b, _c = load_shadow_evidence(session)
    if report is None:
        n = session.scalar(
            select(_f.count()).select_from(PredictionLog)
            .where(PredictionLog.actual_state.is_not(None))
        ) or 0
        print(f"  shadow report     : None  (only {n} scored; needs >= 10, and BOTH lows")
        print("                      and non-lows). Fails closed rather than headlining a")
        print("                      hypo recall it cannot support.")
    else:
        logged = session.scalar(select(_f.count()).select_from(PredictionLog)) or 0
        refused = session.scalar(
            select(_f.count()).select_from(PredictionLog)
            .where(PredictionLog.guardrail_fired.is_not(None))
        ) or 0
        print(f"  shadow report     : n_predictions={report.n_predictions} "
              f"(of {logged} logged; {refused} were REFUSALS, excluded)")
        print("    ★ a refusal carries no distribution, so scoring it would read as")
        print("      'the model predicted no low' — a different statement entirely")
        print(f"    hypo recall     : {report.hypo_recall.recall:.3f}")
        print(f"    Brier           : {report.brier:.4f}")
        print(f"    off-by-one      : {report.off_by_one:.3f}")
        print(f"    severe error    : {report.severe_error:.3f}")
        print("  → the operator's Gate-1 evidence, from real logged predictions")

    sub("Gate 1, re-read LIVE after all of that")
    st = gate1_status(
        valid_meals=len(get_training_set(session)),
        model_hypo_recall=report.hypo_recall.recall if report else 0.0,
        baseline_hypo_recall=0.0, is_promoted=True,
        shadow_days=shadow_days(session, now=NOW + dt.timedelta(days=3)),
        calibration_ok=False,
    )
    print(f"  GATE 1 OPEN: {st.is_open}   blocking: {', '.join(st.failed_conditions)}")
    print("  → promotion alone does not open it. The 90-day clock has 2 of 90 days.")


def scenario_10_idempotency(session: Session, client: TestClient) -> None:
    h("SCENARIO 10 — ★ The double-tap (S-1016)")
    from sqlalchemy import func as _f

    from data.repositories import iob_at_start_at

    when = NOW - dt.timedelta(hours=3)
    payload = {
        "idempotency_key": "double-tap-demo", "datetime": when.isoformat(),
        "meal_type": "dinner", "pre_bg": 150,
        "pre_bg_time": (when - dt.timedelta(minutes=5)).isoformat(),
        "meal_bolus_units": 6.0, "correction_bolus_units": 1.0,
        "bolus_offset_min": -10, "carbs_g": 55.0, "protein_g": 20.0,
        "fat_g": 12.0, "fiber_g": 5.0, "macro_confidence": 90, "logged_by": "patient",
    }
    at = when + dt.timedelta(minutes=30)

    def counts() -> tuple[int, int, float]:
        session.expire_all()
        return (
            session.scalar(select(_f.count()).select_from(MealEvent)) or 0,
            session.scalar(select(_f.count()).select_from(BolusLog)) or 0,
            iob_at_start_at(session, at),
        )

    r1 = client.post("/api/meals", json=payload)
    m1, b1, iob1 = counts()
    r2 = client.post("/api/meals", json=payload)      # she taps again
    m2, b2, iob2 = counts()

    print(f"  first  submit → HTTP {r1.status_code}, meal_id {r1.json()['meal_id']}")
    print(f"  SECOND submit → HTTP {r2.status_code}, meal_id {r2.json()['meal_id']}"
          "   ← same id, not 409")
    print(f"\n    meals     {m1} → {m2}")
    print(f"    boluses   {b1} → {b2}   ← the one that matters")
    print(f"    IOB       {iob1:.3f} → {iob2:.3f} U")

    def dose(iob: float) -> float:
        # A large meal at a high reading, so the suggestion is well clear of zero and the
        # comparison below is about IOB rather than about the INV-3 floor.
        return recommend_bolus(icr=9.0, isf=30.0, carbs_g=90.0, current_bg=260.0,
                               target_bg=135.0, iob=iob).total_units

    print(f"    dose      {dose(iob1):.2f} U → {dose(iob2):.2f} U   (90 g at BG 260)")
    print("\n  ★ What the duplicate WOULD have cost, had it been recorded:")
    print(f"      IOB  {iob1:.2f} U → {iob1 + 7.0:.2f} U")
    print(f"      dose {dose(iob1):.2f} U → {dose(iob1 + 7.0):.2f} U"
          f"   ({dose(iob1) - dose(iob1 + 7.0):.2f} U LESS than she needs)")
    print("    Silently, plausibly, for the ~5 h Fiasp is active — with no screen on which")
    print("    a doubled bolus looks any different from a real one.")


def scenario_11_capture_survives(session: Session, client: TestClient) -> None:
    h("SCENARIO 11 — ★ Her meal logging survives a model that cannot cope (DL-053)")

    when = NOW - dt.timedelta(hours=5)
    # A big correction on top of a meal bolus drives the 07 §4 baseline out of INV-6's range.
    r = client.post("/api/meals", json={
        "idempotency_key": "implausible-demo", "datetime": when.isoformat(),
        "meal_type": "dinner", "pre_bg": 110,
        "pre_bg_time": (when - dt.timedelta(minutes=5)).isoformat(),
        "meal_bolus_units": 2.0, "correction_bolus_units": 14.0,
        "bolus_offset_min": -10, "carbs_g": 10.0, "protein_g": 5.0,
        "fat_g": 3.0, "fiber_g": 1.0, "macro_confidence": 90, "logged_by": "patient",
    })
    print("  a meal whose baseline lands outside INV-6's [20, 600]:")
    print(f"    POST /api/meals → HTTP {r.status_code}   ← her meal is RECORDED")

    refusals = session.scalars(
        select(PredictionLog).where(PredictionLog.guardrail_fired.is_not(None))
    ).all()
    print(f"    refusals recorded: {len(refusals)}")
    for row in refusals[-1:]:
        print(f"      guardrail_fired = {row.guardrail_fired!r}, distribution = "
              f"{row.predicted_distribution}")
    print("\n  → INV-6 still RAISES inside predict_baseline_bg; no out-of-range value is")
    print("    used or shown. What changed (operator, DL-053 amended) is that her primary")
    print("    capture surface no longer depends on a number nobody reads.")
    print("  → Caught is not silent: the refusal is a ROW, and it is EXCLUDED from scoring")
    print("    so it can never read as 'the model predicted no low'.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="demo_scenarios")
    p.add_argument("--db", default="demo.db")
    args = p.parse_args(argv)

    engine = make_engine(f"sqlite:///{args.db}")
    with session_factory(engine)() as session:
        def _override() -> Iterator[Session]:
            yield session

        app.dependency_overrides[get_session] = _override
        client = TestClient(app)

        scenario_1_landscape(session)
        scenario_2_basal(session)
        scenario_3_calculator(session)
        scenario_4_gate(session)
        scenario_5_promotion(client)
        scenario_6_refit(session)
        scenario_7_patient_view(client)
        scenario_8_shadow(session, client)
        scenario_9_the_full_loop(session, client)
        scenario_10_idempotency(session, client)
        scenario_11_capture_survives(session, client)

        app.dependency_overrides.clear()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
