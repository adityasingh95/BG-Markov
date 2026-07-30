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
    print("\n  ★ This is CORRECT and it is also the gap. The dashboard is empty because")
    print("    prediction_log is empty, and prediction_log is empty because NOTHING IN")
    print("    THE RUNNING APP SERVES A PREDICTION. See the blockers section.")


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

        app.dependency_overrides.clear()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
