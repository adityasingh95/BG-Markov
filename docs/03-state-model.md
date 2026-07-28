# 03 — State Model

*Purpose: glycaemic states, meal-record lifecycle, gate state machine.*
*Read before: `04-data-model.md`, `07-clinical-model-spec.md`.*

---

## 1. Glycaemic States

The model's output space. Ordered — this matters, and it is why the model is **ordinal**, not multinomial.

| State | Range (mg/dL) | Label | Clinical meaning |
|---|---|---|---|
| **1** | < 54 | Severe hypoglycaemia | Emergency. |
| **2** | 54 – 79 | Hypoglycaemia | **Upper bound raised from the standard 70.** She cannot feel a low; this buys a warning band. |
| **3** | 80 – 180 | Target | Aligned to her 120–150 correction target. |
| **4** | 181 – 250 | Hyperglycaemia | |
| **5** | > 250 | Severe hyperglycaemia | |

**Boundaries:** `[54, 80, 181, 251]`. Confirm State 2's upper edge with the endocrinologist (OQ-5).

### Rules

- **States are an OUTPUT space only.** `pre_bg` enters the model as a **continuous** feature. Binning it as an input discards information and is a forbidden pattern.
- **Ordering is load-bearing.** Predicting State 4 when the truth is State 5 is a minor error. Predicting State 4 when the truth is State 1 is a catastrophic one. Multinomial logistic regression cannot tell these apart. Ordinal regression can.
- **The boundaries sit inside meter noise.** A fingerstick carries ±15% error, so near 180 the *label itself* is uncertain. This is a known, accepted limitation of the discrete design (`01-prd.md` §7).

---

## 2. Meal Record Lifecycle

```
                    ┌──────────┐
                    │  DRAFT   │  localStorage; not persisted
                    └────┬─────┘
                         │ submit
                    ┌────▼─────┐
                    │ LOGGED   │  pre_bg, macros, bolus captured
                    │          │  awaiting post-meal reading
                    └────┬─────┘
                         │ post_bg entered
                    ┌────▼─────┐
                    │ COMPLETE │  validity computed
                    └────┬─────┘
              ┌──────────┴──────────┐
              ▼                     ▼
        ┌──────────┐          ┌──────────┐
        │  VALID   │          │ EXCLUDED │
        └────┬─────┘          └────┬─────┘
             │                     │
             ▼                     ├──▶ rescued ──▶ ★ RETAINED AS HYPO EVENT
       training set                │                  (INV-7 — NOT deleted)
                                   └──▶ other reasons ──▶ excluded from training,
                                                          RETAINED for adherence
                                                          diagnostics
```

### Exclusion reasons

| Reason | Condition |
|---|---|
| `missing_outcome` | `post_bg` is null |
| `outside_window` | `elapsed_min` outside [105, 135] |
| `rescued` | `hypo_treatment = true` → **see INV-7 below** |
| `uncontrolled_intake` | `snack_during_window = true` |
| `iob_cob_contamination` | Previous meal < 3 h prior |
| `low_confidence` | `macro_confidence < 50` |

Multiple reasons may apply. **All are recorded**, not just the first.

### ★ INV-7 — the rescue exception **[SAFETY]**

A rescued meal is excluded from **outcome regression** but **retained as a hypo event** (State 2 or 1) for the risk model.

**Why this is a named invariant rather than a detail:** the natural refactor is *"invalid rows get dropped from the training set."* That single line would silently delete every low she actually experienced — the exact population the system exists to predict — and the model would then be trained on a world where she never goes low. It would look fine. It would be calibrated on nothing.

S-203 carries a regression guard specifically for this. **Do not delete it when it becomes inconvenient.**

### Nothing is ever hard-deleted

Invalid records are **kept**. `elapsed_min` is stored even when it falls outside the window. Adherence cannot be diagnosed from data that was thrown away.

---

## 3. Gate State Machine **[SAFETY]**

Gates are evaluated **from live data on every call.** Never cached, never configured, never stubbed. A cached "gate passed" is a silent safety failure (ADR-7).

```
   ┌─────────────────────────────────────────────────────┐
   │ CLOSED                                              │
   │ Logging only. No model. No output.                  │
   └───────────────────────┬─────────────────────────────┘
                           │ n_valid_meals ≥ 50
   ┌───────────────────────▼─────────────────────────────┐
   │ GATE 0 — MODEL TRAINS                               │
   │ Metrics computed. OPERATOR-VISIBLE ONLY.            │
   │ Patient sees nothing. (INV-2)                       │
   └───────────────────────┬─────────────────────────────┘
                           │ n_valid_meals ≥ 150
                           │ AND hypo_recall > baseline
                           │ AND calibration acceptable (held-out)
                           │ AND shadow_mode_days ≥ 90
                           │ AND is_promoted ← ★ OPERATOR, MANUAL
   ┌───────────────────────▼─────────────────────────────┐
   │ GATE 1 — PATIENT-VISIBLE RISK OUTPUT                │
   │ Still shadow-logged. Guardrails active.             │
   └───────────────────────┬─────────────────────────────┘
                           │ icr_confirmed
                           │ AND (isf_confirmed_by_endo
                           │      OR n_clean_correction_events ≥ 5)
   ┌───────────────────────▼─────────────────────────────┐
   │ GATE 2 — PRESCRIPTIVE MODULE ENABLED   ⚠ RETIRING   │
   │ Bolus calculator. NO ML in this path. (INV-1)       │
   │ Slated for removal under S-1011 (DL-035).           │
   └─────────────────────────────────────────────────────┘
```

### Gate rules

| Rule | |
|---|---|
| **Volume alone is never sufficient for Gate 1.** | 200 meals with hypo recall *below* the clinical baseline → **still blocked.** The model must earn it. |
| **★ Metrics alone are never sufficient either.** | Every automatic condition can hold and Gate 1 **stays closed** until the operator promotes the model *deliberately* (`model_artifact.is_promoted`, set only by an explicit audited action). Conforms `07 §Retraining` — *"Promotion is manual, on hypo recall."* Code never sets it on a threshold. |
| **The shadow clock is a precondition, not a formality.** | `shadow_mode_days ≥ 90` (REQ-048) is computed from logged prediction timestamps, never a stored boolean. |
| **Gate 2 is blocked on a human, not on code.** | It waits on the endocrinologist (OQ-1, OQ-2). No amount of engineering opens it. **⚠ Retiring** — the operator has decided to de-gate ICR (DL-035); S-1011 removes this gate and INV-1, replacing it with an ordinary present/`> 0` input check. Gate 1 is unaffected. |
| **Gates only ever advance.** | A gate can be manually revoked by the operator. It never advances automatically past its condition. |
| **No bypass exists.** | Not by fixture, not by mock, not by config flag, not by env var. SDET writes a test proving this for each gate. |

> **Code-vs-spec status (2026-07-18).** This state machine is the target. `gate1_status()`
> currently evaluates **only** volume ∧ hypo-recall — the shadow clock and manual promotion are
> **not yet enforced in code**, and `model_artifact.is_promoted` is read nowhere. S-1006 and
> S-1007 bring the code into conformance with this spec; until they land, the gate is weaker
> than this diagram. Recorded in DL-034 rather than left as a silent divergence.

---

## 4. Kill Switch **[SAFETY]**

```
   ┌────────────┐   rolling prospective performance
   │   ARMED    │   drops below the clinical baseline
   │ ML output  │────────────────────────┐
   │  showing   │                        │
   └─────▲──────┘                        ▼
         │                     ┌──────────────────────┐
         │  MANUAL             │      TRIPPED         │
         │  re-arm only        │  ML output suppressed│
         └─────────────────────│  Baseline shown      │
                               │  Operator alerted    │
                               └──────────────────────┘
```

**It never re-arms itself.** A single good prediction after a bad run does not restore trust, and the code must not pretend otherwise.

When tripped, the system **falls back to the clinical baseline** — which is always available, always causal, and never depends on the model.
