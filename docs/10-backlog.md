# 10 — Backlog

*Purpose: epics, stories, acceptance criteria, per-story TDD strategy.*
*Read before: starting any work. This is the build order.*

**Conventions**
- **AC** — acceptance criteria. Dev is done when these pass.
- **TDD** — the failing test SDET writes **first**. A floor, not a ceiling.
- **[SAFETY]** — requires a written invariant argument in the PR. A green build is **not** sufficient.
- `REQ-nnn` traces to `01-prd.md` §5. `INV-n` to `CLAUDE.md`.

---

# ★ BUILD ORDER

```
EPIC 1 (Foundation) → EPIC 2 (Data) → EPIC 3 (Logging + Durability)
                                              │
                                      ★ SHIP — LOGGING LIVE
                                        Gate 1 clock starts
                                              │
                              ┌───────────────┴─── ~3 months of data ───┐
                              ▼                                          ▼
        EPIC 4 (Features) → EPIC 5 (Baseline) → EPIC 6 (Model)
                                              → EPIC 7 (Validation)
                                              → EPIC 8 (Guardrails/Output)
                                                        │
                                                        ▼
                                              EPIC 9 (Prescriptive — Gate 2)
                                                        │
                                                        ▼
                          EPIC 10 (Integration, UI & End-to-End Validation)
```

### Three hard rules

1. **Ship EPIC 3 first.** The model was the whole design conversation but it is **not the bottleneck** — three months of her logging is. **Every week spent on the ordinal model before logging is live is a week added to the END of the project.**
2. **S-304 (restore drill) runs in month one, before there is real data to lose.** The story is not done until the drill has been **executed**.
3. **EPIC 9 does not start until S-703 (gate enforcement) is merged and green.** The bolus calculator is five lines and it is the most dangerous code in the system. **The gates must exist before the thing they gate.**

---

## EPIC 1 — Foundation

### S-101 — Project skeleton
**AC:** `pytest`, `ruff`, `mypy --strict` clean. Coverage gate at 90% on core. Deps pinned (fastapi, statsmodels, pandas, pydantic, hypothesis, alembic).
**TDD:** CI fails on a deliberate lint error; fails on a deliberate type error.

### S-102 — Accessible base layout — REQ (05b §2)
**AC:** ≥18px base, ≥48px targets, `inputmode="numeric"` on every BG/dose field, no colour-only signalling, no dropdowns for dish selection.
**TDD:** `axe` passes. Usable at 200% zoom. Every numeric field asserts `inputmode`.

### S-103 [SAFETY] — Config loader
**AC:** Frozen pydantic model; mutation raises. `icr: null` permitted at load but sets `prescriptive_enabled = False`. Unknown keys raise. `isf <= 0` raises. `max_bolus_u > 25` raises.
**TDD:** Property — any config with `icr is None` ⇒ `prescriptive_enabled == False`. Config cannot raise `max_bolus_u` above the hard-coded ceiling.

### S-104 [SAFETY] — Safety invariants module
**AC:** INV-1..9, each **one named function** in `core/safety.py`. Raises `SafetyViolation` — **never `assert`**. **Zero internal project imports** (ADR-6).
**TDD:** Positive + negative per invariant. **AST test: no `assert` in `core/safety.py`.** Grep test: no other module re-implements an invariant.

### S-105 [SAFETY] — ★ Forbidden-pattern test suite
**AC:** All patterns in `09-test-plan.md` §6 have a failing-on-violation test.
**TDD:** **The `datetime.now()` AST test is the most important.** Deliberately introduce each pattern; assert each test fires.
**Adversarial:** These will look like dead weight. They are the guardrails that catch the 2am refactor. **Do not delete them.**

---

## EPIC 2 — Data Layer

### S-201 — Schema + migrations — REQ-002, 005, 006, 007, 054
**AC:** All tables per `04-data-model.md`. `bolus_offset_min` accepts negatives. `net_carbs_g` computed, floored at 0. `logged_at` present and distinct from `datetime`. `patient_profile` versioned, never updated in place.
**TDD:** `bolus_offset_min = -15` round-trips. `carbs=30, fiber=40` ⇒ `net_carbs=0`, not −10. A profile change creates a **new row**.

### S-202 [SAFETY] — ★ Reported timestamps (ADR-8) — REQ-004, 005
**The cheapest high-value story in the pack. Impossible to retrofit.**
**AC:** `datetime` = reported. `logged_at` = system clock. `bolus_offset_min` and `elapsed_min` computed from **reported** times only.
**TDD:**
- Log at 09:40 reporting an 08:00 mealtime ⇒ `datetime=08:00`, `logged_at=09:40`. **Assert they differ.**
- Post-BG entered at 11:30 for a 10:00 reading ⇒ `elapsed_min` from **10:00**.
- **AST test: `datetime.now()` never populates a clinical timestamp.**
**Adversarial:** This is the exact mistake a coding agent makes on autopilot. It corrupts the model's two most important features **with no error and no way to detect it afterwards.**

### S-203 [SAFETY] — ★ Validity engine + INV-7 — REQ-022, 023
**AC:** All six exclusion rules with correct reasons. **All applicable reasons recorded, not just the first.** `elapsed_min` stored even when invalid. `get_training_set()` and `get_hypo_events()` both exist.
**TDD:**
- 105 ⇒ valid; 104 ⇒ `outside_window`. 135 ⇒ valid; 136 ⇒ invalid.
- **★ REGRESSION GUARD: 100 meals, 20 rescued ⇒ training set excludes all 20; `get_hypo_events()` returns exactly 20.**
**Adversarial:** The natural refactor — *"invalid rows get dropped"* — **silently deletes every low she ever had.** The model would then be trained on a world where she never goes low. **This test exists to catch that. It will look redundant. Do not delete it.**

### S-204 — Dish table — REQ-009
**AC:** IFCT 2017 ingest. Macros per household portion. Free text ⇒ `macro_confidence = 60`, queued for review.
**TDD:** `2 × roti` = exactly double `1 × roti`. Free text defaults to 60, not 95.

---

## EPIC 3 — Logging & Durability ★ THE CRITICAL PATH

### S-301 — Meal log form — REQ-001, 002
**AC: A repeat meal is ≤4 taps + 2 numbers.** Optional fields collapsed, never blocking. `localStorage` draft-save.
**TDD:** **An automated flow test that counts taps and asserts ≤4.** This is a *tested* requirement, not an aspiration. Kill the form mid-entry ⇒ draft survives.

### S-302 [SAFETY] — Bolus timing — REQ-003
**AC:** Signed offset. **Cannot be skipped or silently defaulted.**
**TDD:** Submission without a timing choice is rejected. "15 min before" ⇒ `-15`.

### S-303 — Post-meal reading + test-time prompt — REQ-010, 011, 014
**AC:** <15s. `post_bg_time` reported. Prompt shows **reported mealtime + 120**.
**TDD:** Log at 09:40 for an 08:00 meal ⇒ prompt says **10:00 AM**, not 11:40. Retrospective entry **asks**, never assumes.

### S-304 [SAFETY] — ★ Backup + restore drill — REQ-050, 051, 052
**AC:** `app.db` **never** in a synced folder. Hourly `sqlite3 .backup` → synced folder. Nightly CSV. `cli restore-drill`.
**TDD:** Backup during an active write yields a valid DB. Restored snapshot is byte-identical.
**★ THE STORY IS NOT DONE UNTIL THE DRILL HAS BEEN RUN FOR REAL. Month one. Before there is data to lose. BA logs the date.**

### S-305 [SAFETY] — Hypo rescue capture — REQ-012, INV-7
**TDD:** Rescued meal absent from training, present in `get_hypo_events()`.

### S-306 — Correction-event capture — REQ-013
**The highest-value data in the system** — the only causally clean read on ISF.
**AC:** Prompted when a correction bolus has no meal. +4h follow-up. `iob_at_start` computed.
**TDD:** `food_in_window = true` ⇒ excluded from ISF derivation.

### S-307 — Operator adherence dashboard — REQ-053
**AC:** Valid rate, exclusions by reason, **`median(logged_at − datetime)`**, days-since-last-log, meals-to-Gate-1.
**TDD:** The lag metric is computed from the two distinct columns, not fabricated.

# ★ SHIP HERE — logging live. The Gate 1 clock starts.
### Everything below runs **in parallel** with ~3 months of data collection.

---

## EPIC 4 — Derived Features

### S-401 [SAFETY] — IOB engine (Fiasp) — REQ-020
**AC:** Exponential, tp=55, td=240. **Always derived; no manual-entry path exists.**
**TDD:**
- **Property: monotonically decreasing on (0, td).** The core correctness property.
- Property: `∈ [0,1]` for all t. `f(0)=1`, `f(240)=0`, `f(-5)=1` (clock skew).
- **Golden: 6 hard-coded (t, fraction) pairs to 4 dp.** Locks the curve.
- Two 5U boluses at one instant = one 10U bolus.
- AST: no module assigns IOB from user input.

### S-402 — Effective basal (Tresiba) — REQ-021
**TDD:** Step change 24→30 U: at +1 day strictly between; at +5 days within 0.5 of 30. **Asserts the multi-day carryover is actually modelled.** Lockout days 1–3 flagged, day 4 not.

### S-403 — Exercise encoding — REQ-024
**TDD:** **The non-monotonicity test** — `light/60min` and `intense/60min` feature vectors differ in more than scalar magnitude, i.e. the encoding *permits* opposite-signed effects.
**Adversarial:** Prevents regression to a numeric 0/1/2 column, which **mathematically forbids** the physiology.

### S-404 — Feature pipeline
**AC:** `pre_bg` **continuous**. `macro_confidence/100` as `sample_weight`. Scaler fit on train folds only.
**TDD:** AST — `pre_bg` never reaches the state-binner on the input path. Scaler stats differ between train-fold and full-set fits (proves the split is respected).

---

## EPIC 5 — Baseline & Parameters

### S-501 — ★ Baseline model — REQ-030
**Build this BEFORE any ML. It takes an afternoon.**
**AC:** Pure function. Binned via the shared state function. Scored on the full metric suite. **Its score is the bar to beat.**
**TDD:** Zero carbs/bolus/IOB ⇒ `post = pre`. **Directionality:** doubling carbs raises the prediction; doubling bolus lowers it. Golden: 5 hand-computed cases.

### S-502 [SAFETY] — ISF from correction events — REQ-033
**AC:** Only `iob_at_start < 0.5` **and** `food_in_window = false`. **≥5 events required.** Never silently swaps. Derived ISF ≤ 0 raises.
**TDD:** 4 events ⇒ default retained, derived value *reported*. 5 ⇒ applied, `isf_source = derived`.

### S-503 [SAFETY] — ★ ICR/ISF constrained OLS — REQ-032, INV-8
**AC:** Sign-constrained `β_carb ≥ 0`, `β_ins ≥ 0`. If the **unconstrained** fit gives `β_ins < 0`, **log a prominent warning naming confounding-by-indication**, then constrain. Cross-check against correction events; **on disagreement, prefer the correction events.**
**TDD:** **★ Construct a dataset where bolus positively correlates with post-meal BG (the realistic case). Assert `β_ins ≥ 0` and the warning fired.** The single most important test in the model epics.

---

## EPIC 6 — The Model

### S-601 — Ordinal model — REQ-031
**AC:** **One** model. `pre_bg` continuous. L2. Hypo states up-weighted × confidence weights.
**TDD:** Grep — `multi_class` appears nowhere. Grep — no `for state in range(1,6): fit(...)`. Probabilities sum to 1.0. **Ordinal sanity: as `pre_bg` rises, `P(state ≥ 4)` is non-decreasing.**

### S-602 — Brant test + partial PO
**TDD:** PO-satisfying synthetic data passes; threshold-varying data fails and escalation fires.

### S-603 — Bayesian ordinal (n ≥ 200)
**AC:** Priors encode **INV-8 as a sign constraint**. Credible intervals, not point estimates.
**TDD:** Posterior for `β_insulin` has support only on the correct side of zero. Intervals widen as n shrinks.

---

## EPIC 7 — Validation

### S-701 [SAFETY] — ★ Temporal CV — REQ-034
**TDD:** `max(train.datetime) < min(test.datetime)` **every fold.** **No `date` in both train and test in any fold** (basal is constant within a day ⇒ day-level leakage). Grep — `shuffle=True` appears nowhere.
**Adversarial:** **If the model performs suspiciously well, this is why. Investigate before celebrating.**

### S-702 — Metric suite — REQ-035
**AC:** Hypo recall @ fixed FAR (**primary**), Brier, reliability diagram, MAE, Clarke grid, off-by-one. **Plain accuracy is NOT reported.**
**TDD:** Golden — published Clarke pairs land in documented zones. Grep — `accuracy_score` absent from the reporting module.

### S-703 [SAFETY] — ★ Gate enforcement — REQ-040, 041, INV-1, INV-2
**EPIC 9 is blocked until this is merged and green.**
**AC:** Gates evaluated from **live data on every call. Never cached** (ADR-7).
**TDD:**
- `icr = None` ⇒ `recommend_bolus()` raises `GateNotPassed`. **No fixture, mock, flag, or env var bypasses it.**
- n=149 ⇒ patient output raises. n=150 with metrics passing ⇒ renders.
- **n=200 but hypo recall below baseline ⇒ STILL BLOCKED.** Volume alone never opens Gate 1.

---

## EPIC 8 — Guardrails & Output

### S-801 [SAFETY] — Output guardrails — REQ-044, 046
**TDD:** Each of the five conditions has a triggering test. Diffuse posterior at max p=0.39 ⇒ "uncertain"; at 0.41 ⇒ a state. **Baseline says 3, model says 5 ⇒ both returned, `conflict=true`, no winner picked.** Predicted 601 ⇒ raises; 600 ⇒ does not.

### S-802 [SAFETY] — Prediction log — REQ-045, INV-9
**TDD:** **Mock the persistence layer to fail ⇒ assert NO prediction is returned.** Write-then-display ordering is **enforced, not incidental.**

### S-803 [SAFETY] — Kill switch — REQ-047
**TDD:** Bad run ⇒ trips, output suppressed, baseline shown. **A subsequent good prediction does NOT silently re-enable it.**

### S-804 [SAFETY] — Patient risk readout — REQ-040, INV-2
**AC:** **Hypo risk is the headline.** Plain language. Refusal is a rendered state. Never advice.
**TDD:** n=149 ⇒ surface raises. No bypass.

### S-805 — Shadow-mode dashboard
Calibration, hypo recall, Clarke grid, predictions vs actuals, `β_insulin < 0` warnings.

---

## EPIC 9 — Prescriptive (Gate 2)

> **BLOCKED until S-703 is merged and green.**
> **BLOCKED until the endocrinologist confirms ICR (OQ-1) and ISF (OQ-2).**
> Five lines of code. The most dangerous code in the system.

### S-901 [SAFETY] — Bolus calculator — REQ-041..043
**AC:** The clinical formula. **No ML in this path.** INV-1/3/4 enforced. Full arithmetic displayed. Framed as a suggestion for review.
**TDD:**
- **INV-4:** BG 79 ⇒ refuses. BG 80 ⇒ computes.
- **INV-3:** `carbs_g = 900` (typo for 90) ⇒ **capped at 15 U AND flagged implausible.** Assert **both** the cap and the flag.
- **INV-3:** Negative computed dose ⇒ returns 0.0.
- **INV-1:** `icr = None` ⇒ raises. **Assert no fixture, mock, or config bypasses.**
- Golden: 5 hand-computed doses to 2 dp.
- Property: non-decreasing in carbs; non-increasing in IOB.

---

## EPIC 10 — Integration, UI & End-to-End Validation

> Post-ship hardening, added after EPICs 1–9 completed (approved by the operator,
> 2026-07-17, DL-033). EPICs 5–9 delivered the model/prescriptive surfaces as **tested
> Python returning data structures** (`ShadowReport`, `PatientReadout`, `BolusRecommendation`);
> the HTML render layer was **deferred by design** (S-804/S-805 presentation notes) because
> there is nothing patient-visible to render before Gate 1. This epic builds those render
> layers, a seeded synthetic-data generator, and one end-to-end test that drives the whole
> cycle.
>
> **Building a UI does not open a gate.** The patient readout and bolus screens render the
> *already-gated* logic: the readout route calls `require_gate1` first (INV-2) and the bolus
> route `require_gate2` first (INV-1). Before those gates, the screens render the refusal /
> baseline state — never a blank, never a dose. Runtime gating is unchanged.
>
> The operator dashboard (S-1001), the synthetic-data generator (S-1004), and the E2E test
> (S-1005) are **not gated** and are buildable now. S-1002/S-1003 render gated states now;
> their patient-visible model/dose output still waits on Gate 1 / clinical go-live.

### S-1001 — Operator shadow dashboard UI — REQ-055
**AC:** A rendered operator page for `build_shadow_report`: hypo recall @ FAR (**headline
metric**), Brier, a reliability/calibration diagram, Clarke grid, predictions-vs-actuals
matrix, off-by-one/severe rates, and the **`β_insulin < 0` confounding alarm** on the same
screen. Live Gate 1 / Gate 2 status shown. Operator-only, in the operator nav, **not** the
patient nav. **No plain-accuracy figure anywhere.** No dose on this screen.
**TDD:** Grep — `accuracy` absent from the template. The `β_insulin < 0` case renders a
visible alarm, not a silent pass. `axe` passes; usable at 200% zoom. Renders with an empty
report (pre-data) without error.

### S-1002 [SAFETY] — Patient readout UI — REQ-040, INV-2
**Discharges the S-804 deferred presentation note.**
**AC:** A Jinja template + route rendering `PatientReadout`. **The route calls
`require_gate1` first, no bypass** — before Gate 1 it renders the refusal / baseline state
as a **rendered answer, never a blank, never an error page**. Hypo risk is the headline, in
**text** (never colour-only). **There is no dose/bolus/units field on this screen, ever.**
**TDD:** Gate-1-closed ⇒ the route renders the refusal/baseline state (asserted), never a
prediction; no query param, header, or env var flips it. `axe` passes. A grep/DOM test
asserts no dose-like field is present on the readout template.

### S-1003 [SAFETY] — Bolus calculator UI — REQ-041, REQ-042, REQ-043, INV-1, INV-3, INV-4
**The most dangerous screen in the system. Clinical-deployment gated.**
**AC:** A form + route over `recommend_bolus`. **The route calls `require_gate2` first, no
bypass** (INV-1) — `icr = None` renders a "disabled until Gate 2" state, not a form that
computes. Refuses below BG 80 (INV-4). An over-cap dose renders the **flagged implausible**
state (INV-3), never a silent 15 U. Shows the **full arithmetic**; frames the number as *a
suggestion for review*, not an instruction; **does not autofill the dose into any action or
log**. No ML in the path (the UI calls only `recommend_bolus`).
**TDD:** icr=None ⇒ disabled state rendered, no dose (asserted); no bypass param/env. BG 79
⇒ "treat the low first" state; BG 80 ⇒ computes. carbs=900 ⇒ the flagged-implausible state
renders (cap **and** flag both visible). Golden: the 5 hand-computed doses render to 2 dp.
Grep — the UI module imports nothing from `models/`.

### S-1004 — Synthetic-data generator — REQ-056
**AC:** A **seeded** generator producing a full synthetic logging cycle — meals, boluses,
corrections, exercise, post-meal readings, hypo rescues — honouring **reported-timestamp
discipline** (`datetime` reported, `logged_at` separate; ADR-8) and producing a realistic
hypo minority. Lives under `tests/` / `scripts/` fixtures. **Never importable into a
production model-fit or dosing path, and never presented as real patient data** (an AST/grep
guard asserts `core/`,`models/`,`prescribe/`,`api/` do not import it).
**TDD:** A fixed seed reproduces byte-identical output. No generated clinical `datetime`
comes from the system clock. The forbidden-import guard fires if a production module imports
it.

### S-1005 [SAFETY] — End-to-end cycle test — REQ-057
**The "prove it all works through the full cycle" story.**
**AC:** One test (or suite) drives synthetic data (S-1004) through the **whole chain**:
logging/validity + INV-7 → features → model fit → temporal CV → metric suite → gates →
patient readout → shadow dashboard → bolus calculator. Asserts the safety invariants hold
**across** the chain, not just in unit isolation, and that the gates refuse correctly
end-to-end.
**TDD (the chain-level assertions):**
- **INV-7 across the chain:** a rescued low is absent from the training set the model is fit
  on, yet present in `get_hypo_events()` and in the hypo-recall denominator.
- **INV-2:** with < 150 valid meals, the patient readout path refuses; the operator dashboard
  still renders.
- **INV-1:** the bolus path refuses with an unconfirmed ICR; confirmed ⇒ computes.
- **INV-9:** every served prediction in the run is persisted **before** it is returned.
- **No temporal leakage:** every CV fold satisfies `max(train.datetime) < min(test.datetime)`
  and shares no `date` across train/test.
**Adversarial:** this is the test that catches an invariant that holds in isolation but is
bypassed by the wiring between stages. It is the integration counterpart to the unit safety
suite — **do not let it degrade into a smoke test.**

---

## Traceability

BA maintains **REQ-nnn → story → test → status** in `docs/traceability.md`.
**Any REQ without a covering test is a visible gap.**
