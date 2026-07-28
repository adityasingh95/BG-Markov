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
                                              EPIC 9 (Prescriptive)
                                                        │
                                                        ▼
                          EPIC 10 (Integration, UI & End-to-End Validation)
```

### Three hard rules

1. **Ship EPIC 3 first.** The model was the whole design conversation but it is **not the bottleneck** — three months of her logging is. **Every week spent on the ordinal model before logging is live is a week added to the END of the project.**
2. **S-304 (restore drill) runs in month one, before there is real data to lose.** The story is not done until the drill has been **executed**.
3. **EPIC 9 did not start until S-703 (gate enforcement) was merged and green.** The bolus calculator is five lines and it is the most dangerous code in the system. *(Gate 2 was later retired by S-1011/DL-035; **Gate 1 still gates patient-visible output**, and INV-3/INV-4 still bound the dose.)*

---

## EPIC 1 — Foundation

### S-101 — Project skeleton
**AC:** `pytest`, `ruff`, `mypy --strict` clean. Coverage gate at 90% on core. Deps pinned (fastapi, statsmodels, pandas, pydantic, hypothesis, alembic).
**TDD:** CI fails on a deliberate lint error; fails on a deliberate type error.

### S-102 — Accessible base layout — REQ (05b §2)
**AC:** ≥18px base, ≥48px targets, `inputmode="numeric"` on every BG/dose field, no colour-only signalling, no dropdowns for dish selection.
**TDD:** `axe` passes. Usable at 200% zoom. Every numeric field asserts `inputmode`.

### S-103 [SAFETY] — Config loader
**AC:** Frozen pydantic model; mutation raises. `icr: null` permitted at load but sets `icr_present = False` *(named `prescriptive_enabled` until S-1011 retired Gate 2)*. Unknown keys raise. `isf <= 0` raises. `max_bolus_u > 25` raises.
**TDD:** Property — any config with `icr is None` ⇒ `icr_present == False`. Config cannot raise `max_bolus_u` above the hard-coded ceiling.

### S-104 [SAFETY] — Safety invariants module
**AC:** INV-1..9, each **one named function** in `core/safety.py` *(INV-1 retired by S-1011; INV-2..9 keep their numbers)*. Raises `SafetyViolation` — **never `assert`**. **Zero internal project imports** (ADR-6).
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

### S-703 [SAFETY] — ★ Gate enforcement — REQ-040, INV-2  *(REQ-041/INV-1 retired by S-1011)*
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

## EPIC 9 — Prescriptive

> *(Historical: was BLOCKED until S-703 was green and the endocrinologist confirmed ICR/ISF.
> Both cleared; the ICR **gate** was then retired by S-1011/DL-035 — the confirmed values
> stand, only the gate is gone.)*
> Five lines of code. **Still the most dangerous code in the system**, now bounded by INV-3
> and INV-4 rather than by a gate.

### S-901 [SAFETY] — Bolus calculator — REQ-041..043
**AC:** The clinical formula. **No ML in this path.** INV-3/4 enforced (INV-1 retired by S-1011; a bad ICR is a `ValueError`). Full arithmetic displayed. Framed as a suggestion for review.
**TDD:**
- **INV-4:** BG 79 ⇒ refuses. BG 80 ⇒ computes.
- **INV-3:** `carbs_g = 900` (typo for 90) ⇒ **capped at 15 U AND flagged implausible.** Assert **both** the cap and the flag.
- **INV-3:** Negative computed dose ⇒ returns 0.0.
- **~~INV-1~~ (retired, S-1011):** `icr = None` / `<= 0` ⇒ **`ValueError`**, asserted to be neither a `SafetyViolation` nor a `GateNotPassed`.
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
> route formerly `require_gate2` (INV-1, **now retired** — S-1011). Before Gate 1, the screens render the refusal /
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

### S-1003 [SAFETY] — Bolus calculator UI — REQ-042, REQ-043, INV-3, INV-4
**The most dangerous screen in the system. Clinical-deployment gated.**
**AC:** A form + route over `recommend_bolus`. **Ungated** (Gate 2/INV-1 retired, S-1011): a
missing or `<= 0` ICR renders a plain *"profile incomplete — set the ICR"* state, not a gate
refusal and not a computing form. Refuses below BG 80 (INV-4). An over-cap dose renders the
**flagged implausible** state (INV-3), never a silent 15 U. **IOB is displayed read-only with
its provenance and is never an input field** (REQ-020 — a typed IOB is a forbidden pattern,
`detect_manual_iob`). Shows the **full arithmetic**; frames the number as *a suggestion for
review*; **does not autofill the dose into any action or log**. No ML in the path.
**TDD:** icr None/`<= 0` ⇒ the profile-incomplete state, no dose (asserted). BG 79 ⇒ "treat
the low first"; BG 80 ⇒ computes. carbs=900 ⇒ flagged-implausible (cap **and** flag visible).
Golden: the 5 hand-computed doses render to 2 dp. **No IOB input element exists in the
template.** Grep — the UI module imports nothing from `models/`.

### S-1004 [SAFETY] — Synthetic-data generator — REQ-056 — **DONE 2026-07-18**
**Reclassified `[SAFETY]` on review (2026-07-18, DL-034): "fake data can never reach a
production fit or be mistaken for hers" is a safety property, so the guard belongs in
`tests/forbidden/` (S-105 lineage) with a written argument, not as a plain AC.**
**AC:** A **seeded** generator producing a full synthetic logging cycle — meals, boluses,
corrections, exercise, post-meal readings, hypo rescues — honouring **reported-timestamp
discipline** (`datetime` reported, `logged_at` separate; ADR-8) and producing a realistic
hypo minority. Lives under `tests/` / `scripts/` fixtures. **Never importable into a
production model-fit or dosing path, and never presented as real patient data** — the
forbidden-import guard runs in `tests/forbidden/` and asserts `core/`,`models/`,`prescribe/`,
`api/` do not import it.
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
- **ICR input check (S-1011):** the bolus path raises `ValueError` on a missing/`<= 0` ICR — asserted to be neither a `SafetyViolation` nor a `GateNotPassed`; a usable ICR ⇒ computes.
- **INV-9:** every served prediction in the run is persisted **before** it is returned.
- **No temporal leakage:** every CV fold satisfies `max(train.datetime) < min(test.datetime)`
  and shares no `date` across train/test.
**Adversarial:** this is the test that catches an invariant that holds in isolation but is
bypassed by the wiring between stages. It is the integration counterpart to the unit safety
suite — **do not let it degrade into a smoke test.**

---

> **★ Review addendum — 2026-07-18 (DL-034).** Holding the first-cut EPIC 10 (S-1001–S-1005)
> against the full end-to-end usage sequence exposed that the UI/test layer was scoped but the
> sequence's **operational spine was assumed, not storied.** Two of the gaps are
> **spec-conformance**, not new decisions: `07 §Retraining` already mandates *"Monthly refit …
> Promotion is manual, on hypo recall"* and REQ-048 already requires *"Shadow mode ≥ 90 days
> before patient-visible output."* Yet `gate1_status()` opens automatically on
> `volume ∧ beats_baseline`, and `ModelArtifact.is_promoted` (schema, *"manual only"*) is read
> nowhere. The stories below close the code-vs-spec gap. **They tighten Gate 1; they do not
> relax it. No threshold here is chosen by the team — 90 days, monthly, and "manual on hypo
> recall" all trace to the spec.**

### S-1012 [SAFETY] — Gate-1 calibration condition — REQ-058, INV-2 — **BLOCKED on OQ-9**
**The fifth Gate-1 condition. Found 2026-07-18 (DL-041) while building S-1001: `03 §3` and
`04 §9` both list `calibration acceptable (held-out)` among the Gate-1 conditions, and
`gate1_status()` implements the other four but not this one. The S-1007 note claiming code
and spec now agreed was wrong; DL-041 corrects it.**
**Why it is blocked, not just unbuilt:** *"acceptable"* has **no defined threshold anywhere in
the spec**. Picking one is a clinical acceptance decision, not a team decision (CLAUDE.md —
escalate). `models/metrics.py::reliability_curve` already produces the evidence; what is
missing is the rule. **Do not invent a number to unblock the story.**
**AC (once OQ-9 is answered):** `gate1_status(..., calibration_ok: bool)` — required, not
defaulted, same reasoning as `is_promoted` (S-1006) and `shadow_days` (S-1007). A named,
REQ-traced constant for the threshold. `Gate1Status` reports it so S-1001 can show it in the
checklist. Fails closed: not computable ⇒ not acceptable.
**TDD:** every other condition ✓ + calibration ✗ ⇒ CLOSED; the argument is required
(`TypeError` on omission); a model with a wildly miscalibrated reliability curve does not open
the gate; no env var or config flag substitutes.
**Until it lands:** S-1001 renders the condition as **"not yet enforced — awaiting OQ-9"**
rather than omitting it. A missing condition in a conjunction can only make the gate *more*
permissive than the spec, so this is the honest rendering: the gap is visible on the very
screen where Gate 1 gets opened.

### Build order (EPIC 10)
`S-1004` (synthetic data) → `S-1008` (live prediction wiring) → `S-1006`/`S-1007` (Gate-1
promotion + shadow-clock preconditions) → `S-1001` (operator dashboard, incl. the promotion
control) → `S-1002` (patient readout — needs live wiring **and** the gate) → `S-1003` (bolus
UI) → `S-1005` (E2E, needs all of the above). `S-1009` (refit) and `S-1010` (profile update)
are independent and can land any time.

### S-1006 [SAFETY] — Gate-1 manual promotion — REQ-058, INV-2 — **DONE 2026-07-18**
**Closes the review gap G1. Brings code into conformance with `07 §Retraining` ("Promotion
is manual, on hypo recall").**
**AC:** `gate1_status()` gains a **required** `is_promoted` input and opens **only** when
`volume ∧ beats_baseline ∧ is_promoted`. `is_promoted` is read from the live
`ModelArtifact.is_promoted` (the schema flag that today nothing consumes); it is set **only**
by an explicit, audited operator action (never by code on a metric threshold, never an env
var/flag). Fails closed: absent/unknown ⇒ not promoted.
**TDD:** volume ✓ + beats-baseline ✓ + **not promoted ⇒ Gate 1 CLOSED** (the missing case
today). Promoted but volume/recall not met ⇒ still closed. Promotion is a recorded action
(audit-logged); no env var/param opens it. The `is_promoted` column is now referenced by
`gate1_status` (grep proves it is wired, not dead).
**Adversarial:** the tempting "auto-promote once metrics pass" is exactly what the spec
forbids — a human must put her in front of the model on purpose.

### S-1007 [SAFETY] — Gate-1 shadow-period precondition — REQ-048, INV-2 — **DONE 2026-07-18**
**Closed G2. REQ-048 ("≥ 90 days shadow before patient-visible output") was enforced
nowhere — a REQ with no covering test is a visible gap. This gave it its first
enforcement and its first test. Record: DL-040.**
**AC:** Gate 1 additionally requires **≥ 90 days of shadow-mode operation** (measured from the
first logged shadow prediction to now) before it can open. The 90-day constant traces to
REQ-048, not to the team. Surfaced as a countdown on the operator dashboard.
**TDD:** 89 days shadow, everything else ✓ ⇒ Gate 1 CLOSED; 90 days ⇒ eligible (still needs
promotion, S-1006). The shadow clock is computed from logged prediction timestamps, not a
stored boolean.
**Delivered:** `SHADOW_MIN_DAYS = 90` (commented with REQ-048) + `gate1_status(...,
shadow_days)` **required, not defaulted**; `Gate1Status.shadow_days` / `.meets_shadow_period`
for the S-1001 countdown; `data/repositories.py::shadow_days(session, *, now)` derived from the
earliest `prediction_log.created_at`, `now` injected, clamped at 0. `prescribe/gates.py` stays
DB-free. 17 tests incl. ★ the 89/90 boundary, ★ **time is not evidence** (500 days never
substitutes for volume / baseline / promotion), ★ no table may carry a `shadow*` column, ★ the
readout still raises at day 89 with everything else earned. Guards seen to fire before revert.
**This closed the last code-vs-spec divergence in `03 §3`.**

### S-1008 — Live prediction wiring (per-meal orchestration) — REQ-059 — **DONE 2026-07-18**
**Closes G3. The runtime loop is unit-built but nothing runs it on a real logged meal;
S-1002/S-1003 have nothing to render without it, and S-1005 only tests it on synthetic data.**
**AC:** On a logged meal, orchestrate the real path: derive features → `predict_proba` →
`guard_prediction` → **`record_prediction` (INV-9: persisted before returned)** → serve to the
readout. Uses the currently-promoted `ModelArtifact`; if none is promoted, the patient path
returns the baseline (Gate 1 governs visibility). No new model logic — pure wiring over the
shipped modules.
**TDD:** a served prediction is persisted before return (mock persistence failure ⇒ nothing
served, INV-9). With no promoted model, the patient path yields the baseline, never a raw
model output. Guardrail refusals propagate as rendered states.

### S-1009 — Monthly refit cadence — REQ-060
**Closes G4. `07 §Retraining`: "Monthly refit, trailing 6 months, older data down-weighted."
Currently no schedule exists.**
**AC:** A monthly refit over a trailing 6-month window with older data down-weighted, writing
a **new** `ModelArtifact` (never overwriting) that stays **unpromoted** until the operator
promotes it (S-1006). A refit never auto-promotes.
**TDD:** a refit produces a new artifact row with `is_promoted = False`. The trailing window
and down-weighting are applied (not a full-history equal-weight fit).

### S-1010 — Patient-profile update surface — REQ-061
**Closes G5. Clinical constants are versioned (REQ-054) but there is no operator action to
append a new version — the "keep ICR/ISF updatable later" ask has no surface.**
**AC:** An operator-only action appends a **new** `patient_profile` version (e.g. a revised
ICR/ISF/target); the prior version is retained (append-only, never mutated). Gate 2 and the
bolus calculator read the latest version live. No clinical value is hardcoded.
**TDD:** appending a version creates a new row and leaves the old intact; `recommend_bolus`
reflects the new value on the next call (live, not cached).

### S-1011 [SAFETY] — Retire Gate 2 / INV-1 (ICR de-gated) — REQ-041 — **DONE 2026-07-18**
> **Operator go given 2026-07-18; executed the same day (DL-035).** Removed a named safety
> invariant. Written safety argument in `docs/stories/S-1011.md`. Rollback baseline: `7a7c3bf`
> (`v1.0.0-epic9`). Verified: 442 tests, ruff + `mypy --strict` clean, 99.73% coverage.

**Intent.** The clinician-confirmed-ICR gate (**Gate 2 / INV-1**) is removed as a *gate*.
ICR / ISF / target become ordinary versioned `patient_profile` parameters the bolus calculator
uses directly — no confirmation ceremony, no hard-disable. The **ICR value is unchanged**
(still 9 g/U, DL-032); only its *gate status* goes.

**Kept deliberately (not part of the removal):**
- **A plain input check** — `recommend_bolus` raises **`ValueError`** (an ordinary error, **not**
  `SafetyViolation`/`GateNotPassed`) when `icr` is missing or `≤ 0`, so the arithmetic never
  divides by null/garbage. This is correctness, not the confirmation gate.
- **INV-3** (never negative; cap-and-flag a typo) and **INV-4** (no bolus below BG 80) — the
  bolus calculator keeps both.
- **Gate 1 / INV-2** (patient-visible output) — a *different* mechanism, untouched.
- **`GateNotPassed`** stays in `core/safety.py` — Gate 1 still uses it.
- **INV numbering** — mark **INV-1 "retired"**; do **not** renumber INV-2…9 (renumbering nine
  invariants across the repo is how a bug gets introduced).

**AC (the removal, across all implementations):**
- `prescribe/bolus.py` — drop `require_gate2`/`gate2_status`; `icr: float | None` → `icr: float`;
  add the `ValueError` presence/positivity check. INV-3/INV-4 paths unchanged.
- `prescribe/gates.py` — remove `Gate2Status`, `gate2_status`, `require_gate2`; keep Gate 1.
- `core/safety.py` — remove `inv1_prescriptive_requires_gate2`; keep `GateNotPassed`; header
  marks INV-1 retired.
- `core/config.py` — retire/repurpose `prescriptive_enabled` (prescriptive no longer gated on a
  confirmed ICR).
- **Docs** — CLAUDE.md invariant table (INV-1 → retired) + "three under most pressure" note;
  `01-prd.md` REQ-041; `07-clinical-model-spec.md` §11; this backlog (S-703, S-901, S-1003);
  `traceability.md`; stories S-104/S-703/S-901; glossary + affected specs.
- **Prototype** — remove the Gate 2 status line and the bolus screen's "disabled until Gate 2"
  state (an absent ICR becomes a plain "profile incomplete", not a gate).

**TDD (SDET first — tests updated to the new contract before Dev edits code):**
- `test_gates.py` — remove the Gate 2 suite; Gate 1 suite unchanged.
- `test_bolus.py` — remove the INV-1 `GateNotPassed`/no-bypass cases; **add**: `icr=None` and
  `icr≤0` ⇒ `ValueError` (not `SafetyViolation`). Keep the INV-3 typo cap+flag, INV-4 BG-80
  refusal, the 5 golden doses, and the carbs/IOB monotonicity properties.
- `test_safety_invariants.py` / `test_safety_module_hygiene.py` — remove the INV-1 positive/
  negative and any INV-1 hygiene assertion; the "no `assert`, one-function-per-invariant, zero
  project imports" hygiene still holds for the remaining invariants.
- config tests — update/remove `prescriptive_enabled`.

**Written safety argument (required in the PR) [SAFETY].** Must argue: the ICR is a required
input the formula cannot run without, so a present/positive `ValueError` check preserves
arithmetic safety; the dose is still causal arithmetic with **no ML in the path**; **INV-3**
and **INV-4** still bound and floor it; **Gate 1** still governs whether any model output
reaches her; and the ICR remains in the **versioned, append-only, auditable** profile. State
plainly what is given up: there is no longer a confirmation checkpoint before the calculator
will compute on the configured ICR.

---

## ★ REVISIT LATER — parked, not forgotten

*Deliberately deferred items with a trigger condition. **Do not act on these before the trigger.**
BA reviews this list whenever a trigger fires.*

### ★ R-1 — The Markov question — **trigger: ≥ 150 real valid meals**
**Raised by:** operator, 2026-07-18 · **Record:** DL-038 · **Open question:** OQ-8 ·
**Source:** *"Blood sugar prediction using markov chain"* (operator-supplied)

This project **began as a Markov-chain design** and was deliberately built as a single pooled
ordinal regression instead. DL-038 records all six deviations and the reason for each. The
dominant reason was **small-n**: the source design fits one model per pre-meal state and returns
*"insufficient historical data"* below ~10–15 rows per state — which, at 150 meals, would have
gone silent for **exactly the hypo states the system exists to predict**.

**That argument is currently an estimate, not a measurement.** Once real data exists it can be
tested. Revisit then:

1. **Is a transition-matrix view now informative *as an operator diagnostic*?** Adding
   `P(post-state | pre-state)` as a *descriptive* panel on the shadow dashboard is cheap and may
   be clinically readable. It would **supplement, never replace**, the pooled model.
2. **Does binning `pre_bg` measurably lose anything?** Currently forbidden on first-principles
   grounds. With real data, quantify it rather than assume it.
3. **Does the name still fit?** "BG-Markov" is the source document's framing (glossary §5).

**Constraints on any future revisit — these do not lapse:**
- **Per-pre-state sub-models stay forbidden** unless the data shows every state, *including 1
  and 2*, has enough rows to fit. That is the whole point of the original objection.
- **Plain accuracy stays unreported**, and **random splits stay forbidden** (day-level leakage).
- **No ML in the dose path**, ever — the source's closing suggestion to expand the model into
  dose recommendations is permanently declined.
- Anything touching the state boundaries is a **clinical constant** → endocrinologist, not the
  team (see OQ-5, State 2's upper bound at 79, still unconfirmed).

---

## Traceability

BA maintains **REQ-nnn → story → test → status** in `docs/traceability.md`.
**Any REQ without a covering test is a visible gap.**
