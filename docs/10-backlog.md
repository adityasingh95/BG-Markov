# 10 — Backlog

*Purpose: epics, stories, acceptance criteria, per-story TDD strategy.*
*Read before: starting any work. This is the build order.*

**Conventions**
- **AC** — acceptance criteria. Dev is done when these pass.
- **TDD** — the failing test SDET writes **first**. A floor, not a ceiling.
- **[SAFETY]** — requires a written invariant argument in the PR. A green build is **not** sufficient.
- `REQ-nnn` traces to `01-prd.md` §5. `INV-n` to `CLAUDE.md`.

---

# ★ BUILD ORDER — REORDERED FOR RESEARCH MODE

**The original order shipped logging first because three months of a real
person's adherence stood between EPIC 1 and any result. There is no such clock
now, so the model is the bottleneck and the order inverts.** See `00a §5`.

```
EPIC 1 (Foundation) → EPIC 2 (Data) → EPIC 3a (Generator + Durability)
                                              │
                                      ★ DATA AVAILABLE
                                              │
        EPIC 4 (Features) → EPIC 5 (Baseline) → EPIC 6 (Model)
                                              → EPIC 7 (Validation)
                                              → EPIC 8 (Guardrails/Output)
                                              → EPIC 9 (Prescriptive)
                                              → EPIC 10 (Results)
                                              │
                                      EPIC 3b (Logging UI) — LAST, optional
```

### Four hard rules

1. **The generator is not part of the system under test.** It lives in its own
   package. No module under `core/`, `features/`, `models/` or `prescribe/` may
   import it or read its ground-truth parameters (REQ-055, tested in S-310).
   **A model that can see the answer key proves nothing.**
2. **S-501 (the clinical baseline) is still built before any ML.** It takes an
   afternoon and it is the bar the model must beat. If the ordinal model cannot
   beat it, **that is the finding** — carbs and insulin explain nearly
   everything, and the baseline stands alone.
3. **S-304 (restore drill) still runs early.** A lost run is a re-run you did not
   budget for. The story is not done until the drill has been **executed**.
4. **EPIC 7 (validation) is not optional and does not come last.** The leakage
   suite must be provably working *before* any headline number is quoted. A
   result produced ahead of S-701 is not a result.

### What moved and why

| Story | Was | Now | Why |
|---|---|---|---|
| **EPIC 3a** (new) | — | Right after EPIC 2 | The generator is the data source; nothing downstream runs without it. |
| S-301, S-302, S-303, S-307 | EPIC 3, critical path | **EPIC 3b, last, optional** | A logging UI for a subject who does not exist. Retained as spec; build only if real logging is ever wanted. |
| S-304 (backup/restore) | EPIC 3 | **EPIC 3a** | Still cheap, still early. |
| S-305, S-306 (hypo rescue, correction events) | EPIC 3 | **EPIC 3a** — generator emits these | They are *data shapes* the generator must produce, not UI. **INV-7 and H-3 both depend on them.** |
| EPIC 9 | Blocked on S-703 + endocrinologist | **Unblocked** | Gate 2 opens on declared parameters. INV-3/INV-4 are under test, not gating. |
| **EPIC 10** (new) | — | Last | Writes the answers to H-1..H-5 down. Without it the build produces artefacts, not conclusions. |

---

## EPIC 1 — Foundation

### S-101 — Project skeleton
**AC:** `pytest`, `ruff`, `mypy --strict` clean. Coverage gate at 90% on core. Deps pinned (fastapi, statsmodels, pandas, pydantic, hypothesis, alembic).
**TDD:** CI fails on a deliberate lint error; fails on a deliberate type error.

### S-102 — Accessible base layout — REQ (05b §2)
**AC:** ≥18px base, ≥48px targets, `inputmode="numeric"` on every BG/dose field, no colour-only signalling, no dropdowns for dish selection.
**TDD:** `axe` passes. Usable at 200% zoom. Every numeric field asserts `inputmode`.

### S-103 [SAFETY] — Config loader
**AC:** Frozen pydantic model; mutation raises. Unknown keys raise. `isf <= 0` raises. **`max_bolus_u > 15` raises** — the config ceiling equals `MAX_BOLUS_U` (INV-3). Declared parameters (`00a §4`) load with their provenance; `isf_source` accepts `declared`.
**TDD:** Config cannot raise `max_bolus_u` above the INV-3 ceiling — **assert 16 raises and 15 does not.** Mutation of a loaded config raises. A parameter without provenance raises.
**Note:** the original AC permitted `max_bolus_u` up to 25, above the 15 U invariant. Corrected — see decision log DL-005.

### S-104 [SAFETY] — Safety invariants module
**AC:** The **kept** invariants — INV-3, 4, 6, 7, 8, 9 — each **one named function** in `core/safety.py`. Raises `SafetyViolation` — **never `assert`**. **Zero internal project imports** (ADR-6). Retired invariants (INV-1, 2, 5) have **no function**; the module carries a comment naming each retirement and pointing at `00a §3.1`.
**TDD:** Positive + negative per kept invariant. **AST test: no `assert` in `core/safety.py`.** Grep test: no other module re-implements an invariant. **Test that the retired numbers are absent as functions** — so a later reader cannot mistake a silent deletion for a documented retirement.

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

## EPIC 3a — Data Generator & Durability ★ THE CRITICAL PATH

**The data source for the whole build.** Nothing downstream runs without it.

### S-308 — ★ Synthetic subject generator — REQ-055, `00a §5`
**The generator defines ground truth.** Everything measurable about H-2 and H-3
comes from knowing the answer in advance.

**AC:**
- Emits `meal_event`, `bolus_log`, `basal_log` and `correction_event` rows conforming to `04-data-model.md`.
- Configured with **true** `ICR`, `ISF`, `β_carb`, `β_ins`, noise levels and a hypo rate. These are the answer key.
- **Dosing is confounded by design** — bolus chosen as a function of carbs and `pre_bg`, per `07 §7`. This is H-2 and it must not be optional.
- Reproducible from a seed. The seed is recorded with every dataset.
- Emits **`logged_at` distinct from `datetime`**, with a realistic transcription lag distribution.

**TDD:**
- Same seed ⇒ byte-identical dataset. Different seed ⇒ different.
- **★ `median(logged_at − datetime) > 0`.** A generator emitting `logged_at == datetime` is not exercising ADR-8, and every timestamp test downstream would pass vacuously.
- Confounding is present: `corr(total_bolus, post_bg) > 0` in the emitted data.
- Lows occur at the configured rate, ±tolerance.

**Adversarial:** the temptation is a generator that emits clean, well-dosed,
unconfounded meals — because it is easier to write and the model scores well on
it. **That generator answers no question.** RQ-1 exists for exactly this.

### S-309 — Generator emits rescues and correction events — REQ-012, 013, INV-7
**AC:** Hypo-rescued meals emitted with `hypo_treatment = true` **and** the pre-rescue BG recorded (see decision log DL-008). Standalone correction events emitted with `food_in_window` both true and false.
**TDD:** A dataset of 100 meals with 20 rescued ⇒ `get_hypo_events()` returns exactly 20. **★ The INV-7 regression guard, now with a generator that can actually produce the condition.**

### S-310 [SAFETY] — ★ Generator isolation — REQ-055
**AC:** No module under `core/`, `features/`, `models/` or `prescribe/` imports the generator package or reads its ground-truth parameters.
**TDD:** **AST/import-graph test** asserting the dependency never exists. Attempting the import in a test fixture fails the suite.
**Adversarial:** the fastest way to make a model look good is to let it see the answer key — usually by accident, via a shared config object. **This test is the entire credibility of every number the build produces.**

### S-304 [SAFETY] — ★ Backup + restore drill — REQ-050, 051, 052
**AC:** `app.db` **never** in a synced folder. Hourly `sqlite3 .backup` → synced folder. Nightly CSV. `cli restore-drill`.
**TDD:** Backup during an active write yields a valid DB. Restored snapshot is byte-identical.
**★ THE STORY IS NOT DONE UNTIL THE DRILL HAS BEEN RUN FOR REAL.** A lost run is a re-run you did not budget for.

---

## EPIC 3b — Logging UI ★ DEPRIORITISED — BUILD LAST, IF AT ALL

> **There is no patient.** These stories describe a logging surface for a subject
> who does not exist. They are **retained as specification** — they are the
> reference for what a real logging flow would have to do, and `05b`'s
> accessibility requirements remain the standard — but they are **not on the
> critical path** and may never be built.
>
> If real logging is ever wanted, this epic is where it starts, and `00a §8`
> applies: restoring clinical use is not a matter of flipping a flag.

### S-301 — Meal log form — REQ-001, 002
**AC: A repeat meal is ≤4 taps + 2 numbers.** Optional fields collapsed, never blocking. `localStorage` draft-save.
**TDD:** **An automated flow test that counts taps and asserts ≤4.** This is a *tested* requirement, not an aspiration. Kill the form mid-entry ⇒ draft survives.

### S-302 [SAFETY] — Bolus timing — REQ-003
**AC:** Signed offset. **Cannot be skipped or silently defaulted.**
**TDD:** Submission without a timing choice is rejected. "15 min before" ⇒ `-15`.

### S-303 — Post-meal reading + test-time prompt — REQ-010, 011, 014
**AC:** <15s. `post_bg_time` reported. Prompt shows **reported mealtime + 120**.
**TDD:** Log at 09:40 for an 08:00 meal ⇒ prompt says **10:00 AM**, not 11:40. Retrospective entry **asks**, never assumes.

### S-305 [SAFETY] — Hypo rescue capture — REQ-012, INV-7
> **Moved to EPIC 3a (S-309).** The generator must *produce* rescued meals; the
> UI capture path is EPIC 3b. **INV-7's regression guard is not deferred** — it
> runs against generated data from S-309 onward.

### S-306 — Correction-event capture — REQ-013
**The highest-value data in the system** — the only causally clean read on ISF.
> **Generator side moved to EPIC 3a (S-309).** The UI prompt path stays here.
**AC:** Prompted when a correction bolus has no meal. +4h follow-up. `iob_at_start` computed.
**TDD:** `food_in_window = true` ⇒ excluded from ISF derivation.

### S-307 — Researcher dashboard — REQ-053
**AC:** Valid rate, exclusions by reason, **`median(logged_at − datetime)`**, days-since-last-log, meals-to-Gate-1.
**TDD:** The lag metric is computed from the two distinct columns, not fabricated. **Against synthetic data this metric checks the generator** (S-308), not adherence.

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

### S-503 [SAFETY] — ★ ICR/ISF constrained OLS — REQ-032, REQ-056, INV-8
**★ This is H-2. The single most important story in the build.**
**AC:** Sign-constrained `β_carb ≥ 0`, `β_ins ≥ 0`. If the **unconstrained** fit gives `β_ins < 0`, **log a prominent warning naming confounding-by-indication**, then constrain. Cross-check against correction events; **on disagreement, prefer the correction events.** **`β_ins == 0` exactly is a distinct outcome** — it makes `ICR = ISF/β_carb` undefined and must raise, not divide (decision log DL-009).
**TDD:**
- **★ Take the confounded dataset from S-308 — where bolus positively correlates with post-meal BG — assert the unconstrained fit gives `β_ins < 0`, the warning fired, and the constrained fit gives `β_ins ≥ 0`.**
- **Parameter recovery (REQ-056):** constrained `β_ins` is compared against the generator's true ISF, with an error bar. Recovery within tolerance is the H-2 result; failure is equally reportable.
- `β_ins == 0` ⇒ raises rather than producing `ICR = 0`.
- **RQ-3:** sweep the generator's confounding strength; report where the constraint stops recovering the true sign.

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
**★ No headline number may be quoted before this is merged and green.**
**TDD:** `max(train.datetime) < min(test.datetime)` **every fold.** **No `date` in both train and test in any fold** (basal is constant within a day ⇒ day-level leakage). Grep — `shuffle=True` appears nowhere. **`elapsed_min` and `post_bg` never appear in the feature vector** (decision log DL-006).
**★ H-5 — the suite must be shown to bite:** deliberately introduce a leak (a shuffled split, a shared day across folds, `post_bg` in the features) and **assert the suite catches each one.** A leakage suite never tested against an actual leak is decoration.
**Adversarial:** **If the model performs suspiciously well, this is why.** Synthetic data leaks more easily than real data — the generator knows the answer. Investigate before celebrating.

### S-702 — Metric suite — REQ-035
**AC:** Hypo recall @ fixed FAR (**primary**), Brier, reliability diagram, MAE, Clarke grid, off-by-one. **Plain accuracy is NOT reported.**
**TDD:** Golden — published Clarke pairs land in documented zones. Grep — `accuracy_score` absent from the reporting module.

### S-703 — ★ Gate enforcement — REQ-057, `03 §3`
**No longer blocks EPIC 9.** The gates are now a **readiness ladder** — they label
how much a result can be claimed, not who may see it.
**AC:** Gates evaluated from **live data on every call. Never cached** (ADR-7 — unchanged). Every `prediction_log` row records the gate state at the time.
**TDD:**
- **n=200 but hypo recall below baseline ⇒ Gate 1 STILL CLOSED.** Volume alone never opens it. **Unchanged, and it is the whole point** — the gate is a claim about the model, and row count is not evidence for it.
- **Gates close as well as open** (decision log DL-004): a gate that opened, then had its condition falsified by a refit, reports CLOSED on the next evaluation. **A closing gate suppresses ML output but leaves the clinical baseline visible.**
- No fixture, mock, flag or env var alters a computed gate state. A stubbed gate produces a mislabelled result.

---

## EPIC 8 — Guardrails & Output

### S-801 [SAFETY] — Output guardrails — REQ-044, 046
**TDD:** Each of the five conditions has a triggering test. Diffuse posterior at max p=0.39 ⇒ "uncertain"; at 0.41 ⇒ a state. **Baseline says 3, model says 5 ⇒ both returned, `conflict=true`, no winner picked.** Predicted 601 ⇒ raises; 600 ⇒ does not.

### S-802 [SAFETY] — Prediction log — REQ-045, INV-9
**TDD:** **Mock the persistence layer to fail ⇒ assert NO prediction is returned.** Write-then-display ordering is **enforced, not incidental.**

### S-803 [SAFETY] — Kill switch — REQ-047
**TDD:** Bad run ⇒ trips, output suppressed, baseline shown. **A subsequent good prediction does NOT silently re-enable it.**

### S-804 — Risk readout — REQ-058
> **INV-2 retired** (`00a §3.1`) — there is no patient surface, so there is
> nothing to gate. The readout is built for the researcher.
**AC:** **Hypo risk is the headline** — unchanged, because it is the primary metric. Plain language alongside the raw distribution. Refusal is a rendered state, never a blank. **Carries the non-clinical-use banner** (REQ-058). Never phrased as advice.
**TDD:** A refusal renders as a refusal, not as a missing number. **The banner is present on every rendering path that shows a number** — including the refusal and conflict paths.

### S-805 — Shadow-mode dashboard
Calibration, hypo recall, Clarke grid, predictions vs actuals, `β_insulin < 0` warnings.

---

## EPIC 9 — Prescriptive

> **UNBLOCKED** (`00a §3.1`). INV-1 is retired and Gate 2 opens on declared
> parameters, so nothing gates this epic.
>
> **This does not make it a dose calculator.** Its output is a number in a study.
> INV-3 and INV-4 are **kept in full** — not as protection for anyone, but
> because they are the behaviour under test (H-4), and because a 40 U output is
> how you find out the arithmetic is wrong.

### S-901 [SAFETY] — Bolus calculator — REQ-042, 043, 058
**AC:** The clinical formula per `07 §11`, **including the cap in the function itself**. **No ML in this path** (ADR-10 — unchanged). INV-3/4 enforced. Full arithmetic displayed. Carries the non-clinical-use banner.
**TDD:**
- **INV-4:** BG 79 ⇒ refuses. BG 80 ⇒ computes.
- **INV-3:** `carbs_g = 900` (typo for 90) ⇒ **capped at 15 U AND flagged implausible.** Assert **both** the cap and the flag.
- **INV-3:** Negative computed dose ⇒ returns 0.0.
- **Rounding is explicit** (decision log DL-007): components are **not** rounded before summing. Assert the exact total, then the displayed value.
- Golden: 5 hand-computed doses to 2 dp.
- Property: non-decreasing in carbs; non-increasing in IOB; never negative; never > 15.

---

## EPIC 10 — Results ★ NEW

> Without this epic the build produces artefacts and no conclusions. **A result
> that was never written down did not happen.**

### S-1001 — Answer H-1..H-5
**AC:** One section per hypothesis. Each states the claim, the evidence, the number **with its interval**, and the verdict — including "not answerable at this n" where that is the honest outcome.
**TDD:** Every claim in the write-up resolves to a test or a recorded metric. **An unsourced number fails the build.**

### S-1002 — Parameter recovery report — REQ-056
**AC:** Derived ISF and ICR against the generator's true values, with error bars. Correction-event estimate vs. OLS estimate vs. truth (H-3).

### S-1003 — Reproduction record
**AC:** Seed, generator parameters, model version, data hash, `00a §4` parameter version, **and the gate state at the time of the run** recorded for every quoted result.
**TDD:** **Gate state is stamped, never read live** (DL-004) — a run recorded at Gate 1 still reports Gate 1 after a refit closes the gate. **A result whose seed was not recorded cannot be reproduced and must not be quoted.**

---

## Traceability

BA maintains **REQ-nnn → story → test → status** in `docs/traceability.md`.
**Any REQ without a covering test is a visible gap.**

Hypotheses trace too: **H-n → story → test → result** (`01-prd.md` §1). An
unanswered hypothesis at EPIC 10 is a visible gap in the same way.
