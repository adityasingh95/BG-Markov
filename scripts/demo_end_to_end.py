"""BG-Markov end-to-end demo on SYNTHETIC data (not real patient data).

Drives the REAL code paths — feature pipeline, the ordinal model, the S-702 metric
suite, Gate 1, the patient readout, and the bolus calculator — so you can see what the
system is like without touching a real record. Nothing here changes a clinical constant or
opens a gate that hasn't been earned; Gate 1 decides honestly on the data.
(Gate 2 / INV-1 was retired by S-1011 — a missing ICR is now a plain input error.)

    python scripts/demo_end_to_end.py

Nothing here is a test; it is a readable walk-through of the behaviour the tests lock in.
It builds its dataset in memory from a fixed seed and touches no database.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Make the project importable when run as `python scripts/demo_end_to_end.py` from
# any directory (a script's sys.path[0] is its own dir, not the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.tables import ExIntensity, MealType
from features.pipeline import FEATURE_NAMES, feature_vector, make_scaler, sample_weight
from models.baseline import predict_baseline_state
from models.ordinal import fit_ordinal, hypo_confidence_weights
from models.shadow import build_shadow_report
from models.state import bg_to_state
from prescribe.bolus import recommend_bolus
from prescribe.gates import SHADOW_MIN_DAYS, gate1_status, require_gate1

# --- clinician-confirmed profile (DL-032), read as parameters, never hardcoded ----
ICR = 9.0      # g carb / unit
ISF = 30.0     # mg/dL / unit
TARGET = 135.0  # mg/dL

R = random.Random(20260717)  # fixed seed — reproducible, no Date.now()/random-at-import


# --- a light duck-typed meal the feature pipeline can read ------------------------
@dataclass
class Meal:
    pre_bg: float
    carbs_g: float
    protein_g: float
    fat_g: float
    fiber_g: float
    meal_bolus_units: float
    correction_bolus_units: float
    bolus_offset_min: float
    meal_type: MealType
    ex_intensity: ExIntensity
    ex_duration_min: int
    ex_offset_min: int
    pre_ex_intensity: ExIntensity
    pre_ex_duration_min: int
    macro_confidence: float
    # derived quantities the caller would compute from the IOB / basal engines
    iob_at_meal: float
    effective_basal: float
    minutes_since_last_bolus: float


def _synth_day(day: int) -> list[tuple[Meal, float]]:
    """One day of 2-3 meals; returns (meal, true_post_bg). A physiologically plausible
    post-BG so the model has real signal, with exercise sometimes driving a low."""
    out: list[tuple[Meal, float]] = []
    for mtype in (MealType.breakfast, MealType.lunch, MealType.dinner):
        if mtype == MealType.lunch and R.random() < 0.15:
            continue  # she skips lunch sometimes
        pre_bg = R.uniform(90, 200)
        carbs = R.uniform(20, 90)
        fiber = R.uniform(0, 8)
        # she boluses close to formula for carbs, and slightly UNDER-corrects (runs a
        # little high, as many people do) — with human noise.
        meal_bolus = max(0.0, carbs / ICR * R.uniform(0.90, 1.05))
        corr = max(0.0, (pre_bg - TARGET) / ISF * R.uniform(0.70, 1.0))
        iob = max(0.0, R.gauss(0.6, 0.6))
        # exercise: post-meal walks; intense evening spin sometimes — the main low driver
        ex_int, ex_dur = ExIntensity.none, 0
        roll = R.random()
        if roll < 0.25:
            ex_int, ex_dur = ExIntensity.light, R.randint(20, 45)
        elif roll < 0.35:
            ex_int, ex_dur = ExIntensity.intense, R.randint(30, 60)

        # true post BG (07 §4 shape): carbs raise, bolus+correction+some IOB lower,
        # exercise lowers, plus residual biological noise.
        post = (
            pre_bg
            + (carbs / ICR) * ISF
            - (meal_bolus + corr) * ISF
            - 0.5 * iob * ISF
        )
        if ex_int == ExIntensity.light:
            post -= 0.5 * ex_dur          # a walk lowers BG
        elif ex_int == ExIntensity.intense:
            post -= 1.2 * ex_dur          # intense exercise, sharper drop
        post += R.gauss(0, 18)            # residual biological noise
        post = float(min(max(post, 25.0), 480.0))

        out.append(
            (
                Meal(
                    pre_bg=pre_bg, carbs_g=carbs, protein_g=R.uniform(5, 30),
                    fat_g=R.uniform(2, 25), fiber_g=fiber, meal_bolus_units=meal_bolus,
                    correction_bolus_units=corr, bolus_offset_min=R.uniform(-10, 20),
                    meal_type=mtype, ex_intensity=ex_int, ex_duration_min=ex_dur,
                    ex_offset_min=R.randint(0, 30) if ex_dur else 0,
                    pre_ex_intensity=ExIntensity.none, pre_ex_duration_min=0,
                    macro_confidence=R.uniform(60, 100),
                    iob_at_meal=iob, effective_basal=R.uniform(18, 24),
                    minutes_since_last_bolus=R.uniform(120, 480),
                ),
                post,
            )
        )
    return out


def _hr(title: str) -> None:
    print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)


def main() -> None:
    # ---------------------------------------------------------------- 1. DATA IN
    _hr("1.  SYNTHETIC DATA IN  (90 days ≈ what shadow mode would collect)")
    rows = [row for day in range(90) for row in _synth_day(day)]
    meals = [m for m, _ in rows]
    post_bgs = np.array([p for _, p in rows])
    true_states = np.array([bg_to_state(p) for p in post_bgs])
    n = len(meals)
    hypo = np.isin(true_states, (1, 2))
    print(f"  {n} meals over 90 days.  Hypo events (state 1-2): "
          f"{int(hypo.sum())} ({100*hypo.mean():.0f}%).")
    dist = {s: int((true_states == s).sum()) for s in (1, 2, 3, 4, 5)}
    print(f"  State distribution 1..5: {dist}")

    # temporal split: first 70% train, last 30% test (forward-chaining, no leakage)
    cut = int(0.7 * n)
    idx_tr, idx_te = range(cut), range(cut, n)

    # ------------------------------------------------------------ 2. FEATURES + FIT
    _hr("2.  FEATURE PIPELINE + ORDINAL MODEL  (the real S-404/S-601 code)")
    X = np.array([[feature_vector(
        m, iob_at_meal=m.iob_at_meal, effective_basal=m.effective_basal,
        minutes_since_last_bolus=m.minutes_since_last_bolus)[k]
        for k in FEATURE_NAMES] for m in meals], dtype=float)
    scaler = make_scaler().fit(X[list(idx_tr)])   # scaler fit on TRAIN ONLY
    Xs = scaler.transform(X)
    conf = np.array([sample_weight(m) for m in meals])
    w = hypo_confidence_weights(true_states[list(idx_tr)], conf[list(idx_tr)])
    fit = fit_ordinal(Xs[list(idx_tr)], true_states[list(idx_tr)], confidence_weights=w)
    print(f"  Fitted one proportional-odds ordinal logit on {cut} train meals "
          f"({len(FEATURE_NAMES)} features, hypo up-weighted ×4).")
    print(f"  Observed ordered states in train: {fit.states}")

    # hypo score on the held-out test meals = P(state ≤ 2)
    hypo_score = 1.0 - fit.prob_at_least(Xs[list(idx_te)], 3)
    proba = fit.predict_proba(Xs[list(idx_te)])
    pred_states = np.array([fit.states[i] for i in proba.argmax(axis=1)])
    te_true = true_states[list(idx_te)]
    te_hypo = hypo[list(idx_te)]
    te_post = post_bgs[list(idx_te)]

    # predicted BG for the metric suite: state midpoint is enough for the demo
    _MID = {1: 45.0, 2: 67.0, 3: 130.0, 4: 215.0, 5: 300.0}
    pred_bg = np.array([_MID[s] for s in pred_states])

    # baseline (the clinical formula) hypo recall, for the gate comparison. INV-6 fires
    # when the formula projects a BG off the bottom of the scale — that IS a predicted
    # low, so we catch it (never crash) and count it as a flagged hypo (state 1).
    def _base_state(m: Meal) -> int:
        try:
            return predict_baseline_state(
                pre_bg=m.pre_bg, carbs_g=m.carbs_g, meal_bolus_units=m.meal_bolus_units,
                correction_bolus_units=m.correction_bolus_units,
                iob_at_meal=m.iob_at_meal, icr=ICR, isf=ISF)
        except Exception:  # SafetyViolation (INV-6) — projected off-scale ⇒ a low
            return 1

    base_states = np.array([_base_state(meals[i]) for i in idx_te])
    base_hypo_recall = float(
        (np.isin(base_states, (1, 2)) & te_hypo).sum() / max(te_hypo.sum(), 1))

    # -------------------------------------------------------- 3. SHADOW REPORT (operator)
    _hr("3.  OPERATOR SHADOW REPORT  (the real S-702 metric suite + INV-8 alarm)")
    report = build_shadow_report(
        hypo_score=hypo_score, is_hypo=te_hypo, predicted_bg=pred_bg,
        reference_bg=te_post, pred_states=pred_states, actual_states=te_true,
        unconstrained_beta_insulin=0.42,  # ≥0 ⇒ no confounding alarm (INV-8)
    )
    hr = report.hypo_recall
    print(f"  Hypo recall @ FAR≤10%     : {hr.recall:.0%}  (false-alarm {hr.far:.0%})")
    print(f"  Baseline hypo recall      : {base_hypo_recall:.0%}   ← the bar to beat")
    print(f"  Brier score               : {report.brier:.3f}   (lower is better)")
    print(f"  MAE                       : {report.mae_mgdl:.0f} mg/dL")
    print(f"  Clarke grid               : {report.clarke}")
    print(f"  Off-by-one / severe error : {report.off_by_one:.0%} / {report.severe_error:.0%}")
    print(f"  β_insulin confounding flag: {report.beta_insulin_confounding}  "
          f"(unconstrained β={report.unconstrained_beta_insulin:+.2f})")

    # ------------------------------------------------------- 4. GATE 1 (patient visibility)
    _hr("4.  GATE 1 — is she allowed to SEE the model yet?  (INV-2)")
    model_recall = hr.recall
    # shadow_days is DERIVED in production (data.repositories.shadow_days, from
    # prediction_log timestamps) — hard-coded here only because this demo has no DB.
    scenarios = (("today (few valid meals)", 40, 12), ("after collection", n, 90))
    for label, meals_seen, days_shadowed in scenarios:
        g = gate1_status(valid_meals=meals_seen, model_hypo_recall=model_recall,
                         baseline_hypo_recall=base_hypo_recall,
                         is_promoted=False,  # S-1006: nobody has promoted it
                         shadow_days=days_shadowed)  # S-1007: derived, never stored
        why = []
        if not g.meets_volume:
            why.append(f"needs ≥150 valid meals (has {meals_seen})")
        if not g.beats_baseline:
            why.append(f"model recall {model_recall:.0%} must strictly beat "
                       f"baseline {base_hypo_recall:.0%}")
        if not g.meets_shadow_period:
            why.append(f"day {g.shadow_days} of {SHADOW_MIN_DAYS} shadow mode "
                       f"({SHADOW_MIN_DAYS - g.shadow_days} to go, REQ-048)")
        if not g.is_promoted:
            why.append("the operator has not promoted it (S-1006 — a human must decide)")
        state = "OPEN" if g.is_open else "CLOSED"
        print(f"  {label:26s}: Gate 1 {state}"
              + ("" if g.is_open else "  — " + "; ".join(why)))
    print("  NOTE: even when every automatic condition holds, the FINAL open is an "
          "operator's manual call — never automatic.")

    # ------------------------------------------------------ 5. WHAT SHE SEES (readout)
    _hr("5.  PATIENT READOUT  (INV-2: gated; no dose ever shown to her)")
    # Gate 1 is closed in reality, so build_patient_readout would refuse. Show that,
    # then show what the readout WOULD look like once earned (a promoted gate).
    closed = gate1_status(valid_meals=40, model_hypo_recall=model_recall,
                          baseline_hypo_recall=base_hypo_recall, is_promoted=False,
                          shadow_days=12)
    try:
        require_gate1(closed)
    except Exception as e:  # GateNotPassed (INV-2, Gate 1)
        print(f"  Today  → {type(e).__name__}: patient sees only the BASELINE estimate, "
              "never the model. This is the system refusing, by design.")
    print("  Once earned, the readout is hypo-risk-FIRST text (never a colour, never a "
          "number-to-inject):")
    print('     headline: "Higher chance of a LOW after this meal — check before you drive"')
    print("     (no dose, no bolus field exists on the patient readout at all)")

    # ----------------------------------------------------------- 6. BOLUS CALCULATOR
    _hr("6.  BOLUS CALCULATOR  (INV-3/4 — the sharpest end, no ML in the path)")
    print(f"  Profile: ICR {ICR:g} g/U · ISF {ISF:g} mg/dL/U · target {TARGET:g} mg/dL\n")

    def show(desc: str, **kw: float) -> None:
        try:
            r = recommend_bolus(isf=ISF, target_bg=TARGET, **kw)  # type: ignore[arg-type]
            flag = "  ⚠ IMPLAUSIBLE INPUT — RE-CHECK" if r.implausible_input else ""
            print(f"  {desc}\n      → {r.total_units:.2f} U{flag}\n      {r.arithmetic}")
        except Exception as e:
            print(f"  {desc}\n      → REFUSED: {type(e).__name__} — {e}")
        print()

    show("Normal dinner: 60 g carbs, BG 180, IOB 0",
         icr=ICR, carbs_g=60.0, current_bg=180.0, iob=0.0)
    show("Correction only: 0 g carbs, BG 240, IOB 1",
         icr=ICR, carbs_g=0.0, current_bg=240.0, iob=1.0)
    show("Below target, no carbs: BG 100 (correction would be negative)",
         icr=ICR, carbs_g=0.0, current_bg=100.0, iob=0.0)
    show("★ TYPO: 900 g carbs (meant 90), BG 180 — must NOT hand back a lethal dose",
         icr=ICR, carbs_g=900.0, current_bg=180.0, iob=0.0)
    show("★ She is already LOW: BG 72 — treat the low first (INV-4)",
         icr=ICR, carbs_g=60.0, current_bg=72.0, iob=0.0)
    show("★ No ICR set on the profile (icr=None) — an input error, not a gate (S-1011)",
         icr=None, carbs_g=60.0, current_bg=180.0, iob=0.0)

    _hr("DONE — every number above came from the real modules, on synthetic data.")


if __name__ == "__main__":
    main()
