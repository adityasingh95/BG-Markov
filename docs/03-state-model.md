# 03 — State Model

*Purpose: glycaemic states, meal-record lifecycle, gate state machine.*
*Read before: `04-data-model.md`, `07-clinical-model-spec.md`.*

---

## 1. Glycaemic States

The model's output space. Ordered — this matters, and it is why the model is **ordinal**, not multinomial.

| State | Range (mg/dL) | Label | Clinical meaning |
|---|---|---|---|
| **1** | < 54 | Severe hypoglycaemia | Emergency. |
| **2** | 54 – 79 | Hypoglycaemia | **Upper bound raised from the standard 70 — confirmed, OQ-5/DL-043.** She cannot feel a low; this buys a warning band. |
| **3** | 80 – 180 | Target | Aligned to her 120–150 correction target. |
| **4** | 181 – 250 | Hyperglycaemia | |
| **5** | > 250 | Severe hyperglycaemia | |

**Boundaries:** `[54, 80, 181, 251]`. **Confirmed 2026-07-18 by the operator (OQ-5, DL-043) —
the line stays at 80.**

> **Why 80 and not the standard 70.** She cannot feel a low. A 75 that is still falling is a 55
> twenty minutes later and nobody in the room knows. The raised edge buys ~10 mg/dL of warning
> time, and it matches `core.safety.BOLUS_BG_FLOOR = 80` (INV-4) so *below 80* means one thing
> everywhere in the system rather than two similar things at two numbers.
> **Accepted costs, recorded not glossed:** more false alarms in the 70–79 band (and a system
> that cries wolf gets ignored, which is worse than useless), and hypo-recall figures that are
> **not directly comparable** to published literature anchored at 70.
> **Changing this later re-labels all history** — every stored meal is categorised through this
> line, so a change silently redefines "a low" across the training set and makes last month's
> recall figures mean something different. That is precisely why it was settled before there is
> data, rather than left open.

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
   └─────────────────────────────────────────────────────┘

   ~~GATE 2 — PRESCRIPTIVE~~  REMOVED (S-1011, DL-035, 2026-07-18)
   The bolus calculator is no longer gated on a confirmed ICR. It runs
   whenever a usable ICR exists on the profile, bounded by INV-3 / INV-4,
   with NO ML in the path. Gate 1 above is unaffected.
```

### Gate rules

| Rule | |
|---|---|
| **Volume alone is never sufficient for Gate 1.** | 200 meals with hypo recall *below* the clinical baseline → **still blocked.** The model must earn it. |
| **★ Metrics alone are never sufficient either.** | Every automatic condition can hold and Gate 1 **stays closed** until the operator promotes the model *deliberately* (`model_artifact.is_promoted`, set only by an explicit audited action). Conforms `07 §Retraining` — *"Promotion is manual, on hypo recall."* Code never sets it on a threshold. |
| **The shadow clock is a precondition, not a formality.** | `shadow_mode_days ≥ 90` (REQ-048) is computed from logged prediction timestamps, never a stored boolean. **Enforced since 2026-07-18 (S-1007):** `data.repositories.shadow_days(session, *, now)` derives whole days from the earliest `prediction_log.created_at`; `gate1_status` requires it. Clamped at 0, so clock skew reads as *not yet*. **Time is never evidence** — a long shadow substitutes for none of the other three conditions. |
| **~~Gate 2~~ — REMOVED.** | Retired 2026-07-18 (S-1011, DL-035) at the operator's direction. The ICR is an ordinary versioned profile value; `recommend_bolus` raises a plain `ValueError` on a missing/`<= 0` ICR. **INV-3, INV-4 and Gate 1 are unaffected.** Do not re-introduce a dose gate under another name. |
| **Gates only ever advance.** | A gate can be manually revoked by the operator. It never advances automatically past its condition. |
| **No bypass exists.** | Not by fixture, not by mock, not by config flag, not by env var. SDET writes a test proving this for each gate. |

> **Code-vs-spec status (updated 2026-07-18, corrected same day — DL-041).**
> ✅ Manual promotion is enforced (S-1006): `gate1_status()` requires `is_promoted`, and
> `model_artifact.is_promoted` is read by both `gate1_status` (*may she see it?*) and
> `get_promoted_artifact` (*which model serves?*); writes go only through
> `data/promotion.py` and are audited.
> ✅ The **≥ 90-day shadow clock is enforced** (S-1007, DL-040): `gate1_status()` requires
> `shadow_days`, derived live from `prediction_log` and never stored.
> ⏳ **`calibration acceptable (held-out)` is NOT enforced.** This diagram lists **five**
> conditions; `gate1_status()` implements **four**. The S-1007 closing note claimed the two
> now agreed — **that was wrong, and this corrects it.** The blocker is not code: *"acceptable"*
> has **no defined threshold anywhere in the spec**, and choosing one is a clinical decision,
> not a team decision (CLAUDE.md — escalate). Tracked as **OQ-9** and story **S-1012**; the
> operator dashboard (S-1001) renders this condition as *not yet enforced* rather than
> omitting it, so the gap is visible on the screen where Gate 1 is opened.
> **Gate 1 is not weakened by this** — it is the conjunction, so a missing condition can only
> ever make the gate *more* permissive than the spec, and the remaining four hold it shut today.
> Recorded rather than left silent.

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
