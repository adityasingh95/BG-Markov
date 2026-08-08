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

**Boundaries:** `[54, 80, 181, 251]`. **Declared** (`00a §4`, was OQ-5). State 2's upper edge stays at 80 rather than the standard 70 — it buys a warning band for a subject modelled as unable to feel a low.

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

## 3. Gate State Machine

> **Research mode (`00a §3.1`).** The clinical gates are retired: there is no
> patient to protect and no endocrinologist to wait for. What remains is a
> **readiness ladder** — a statement of what has to be true before a given claim
> is worth making. It gates *interpretation*, not access.
>
> Gates are still evaluated **from live data on every call.** Never cached, never
> configured, never stubbed (ADR-7 — unchanged). A cached gate state produces a
> result label that no longer matches the data behind it.

```
   ┌─────────────────────────────────────────────────────┐
   │ CLOSED                                              │
   │ Not enough data to fit. No model.                   │
   └───────────────────────┬─────────────────────────────┘
                           │ n_valid_meals ≥ 50
   ┌───────────────────────▼─────────────────────────────┐
   │ GATE 0 — MODEL TRAINS                               │
   │ Metrics computed. Results labelled PRELIMINARY.     │
   │ Underpowered — report intervals, not points. (RQ-2) │
   └───────────────────────┬─────────────────────────────┘
                           │ n_valid_meals ≥ 150
                           │ AND hypo_recall > baseline
                           │ AND calibration acceptable (held-out)
                           │ AND held-out temporal evaluation done
                           │     (REQ-057 — replaces the 90-day clock)
   ┌───────────────────────▼─────────────────────────────┐
   │ GATE 1 — H-1 IS ANSWERABLE                          │
   │ The model beat the baseline on a held-out fold.     │
   │ Guardrails active. Results still labelled.          │
   └───────────────────────┬─────────────────────────────┘
                           │ icr declared (00a §4)
                           │ AND (isf declared
                           │      OR n_clean_correction_events ≥ 5)
   ┌───────────────────────▼─────────────────────────────┐
   │ GATE 2 — PRESCRIPTIVE MODULE BUILDABLE              │
   │ Output is a number in a study, NOT a dose.          │
   │ NO ML in this path (ADR-10 — unchanged).            │
   └─────────────────────────────────────────────────────┘
```

**Gate 2 opens on declared parameters, so it is open from the start.** That does
not make the prescriptive module a dose calculator — it makes it an
implementation of a formula whose behaviour is under test. INV-3 and INV-4 are
what is being tested, and they are **kept in full**.

### Gate rules

| Rule | |
|---|---|
| **Volume alone is never sufficient for Gate 1.** | 200 meals with hypo recall *below* the clinical baseline → **still closed.** Unchanged: the gate is a claim about the model, and row count is not evidence for it. |
| **Gates may close as well as open.** | Resolves the contradiction between the old "gates only ever advance" and ADR-7. Gates are recomputed live; if a refit drops hypo recall below baseline, Gate 1 closes. **A closing gate suppresses ML output but leaves the clinical baseline visible** — the screen never goes blank. Mirrors the kill switch (§4). |
| **Never advances past its condition.** | No gate opens on anything other than its stated condition being true of live data. |
| **No bypass exists.** | Not by fixture, not by mock, not by config flag, not by env var. SDET writes a test proving this for each gate. **Unchanged — a stubbed gate produces a mislabelled result.** |

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
