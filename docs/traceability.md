# Traceability Matrix

*Owner: BA. REQ-nnn → story → test → status. Any REQ without a covering test is
a visible gap. INV-n coverage is tracked in the second table.*

## REQ → story → test

| REQ | Story | Test(s) | Status |
|-----|-------|---------|--------|
| _(none — infra)_ | S-101 | `tests/unit/test_toolchain.py`, `tests/unit/test_version.py` | ✅ Done |
| **`05b §2`** (Accessibility NFR; no `REQ-nnn`) | S-102 | `tests/a11y/test_base_layout.py` (axe, inputmode, 18px, 48px, no-dish-`select`, 200 %-zoom reflow, colour-not-sole-signal) | ✅ Done |
| _(config infra; feeds REQ-041/042/054)_ | S-103 | `tests/unit/test_config.py`, `tests/safety/test_config_frozen.py` | ✅ Done |
| _(safety module; INV-2..9 — INV-1 retired S-1011)_ | S-104 | `tests/safety/test_safety_invariants.py`, `tests/safety/test_safety_module_hygiene.py` | ✅ Done |
| _(forbidden-pattern guards; `09 §6`)_ | S-105 | `tests/forbidden/test_forbidden_patterns.py` | ✅ Done |
| **REQ-002** (per-meal capture) | S-201 | `test_schema.py` (meal_event round-trips; `_meal` helper) | ✅ Schema done (form: S-301) |
| **REQ-004** (clinical timestamps reported, never `now()`) | S-202 | `test_reported_timestamps.py` (differ; now() bound only to logged_at), plus S-105 `detect_datetime_now_on_clinical_ts` scanning `data/` | ✅ Done |
| **REQ-005** (`logged_at` ≠ `datetime`) | S-201, **S-202** | S-201 schema tests; **S-202** `test_reported_datetime_and_logged_at_differ`, `test_logged_at_uses_the_injected_clock` | ✅ Done (schema + write path) |
| _(derived features from reported times)_ | S-202 | `tests/unit/test_timestamps.py` (`bolus_offset_min`, `elapsed_min`); `test_elapsed_min_uses_reported_reading_time_not_entry_time` | ✅ Done |
| **REQ-022** (validity per 04 §5; elapsed stored when invalid) | S-203 | `tests/unit/test_validity.py`; `test_get_training_set_excludes_invalid_rows` | ✅ Done |
| **REQ-023 / INV-7** (rescued excluded from training, retained as hypo) | S-203 | `test_repositories.py` (★ regression guard 100/20; wiring-bites) | ✅ Done (INV-7 wired) |
| **REQ-009** (macros from dish table; free text lowers confidence) | S-204 | `tests/unit/test_macros.py`, `tests/integration/test_dishes.py` | ✅ Done (seed data pending, DL-015) |
| **REQ-001** (repeat meal ≤4 taps + 2 numbers) | S-301 | `tests/e2e/test_meal_log_flow.py` (★ tap-count, draft survival, optional collapsed) | ✅ Done |
| **REQ-002** (per-meal capture via `POST /api/meals`) | S-301 | `tests/integration/test_meals_api.py` (422 no offset; persists; test_at; bolus_log) | ✅ Done (form; correction-only events S-306) |
| **REQ-003** (signed offset; cannot be skipped/defaulted) | **S-301** (server 422) + **S-302** (client block) | `tests/integration/test_bolus_timing.py` (regression guards — the server 422 predates S-302, delivered by S-301's `MealCreate`; DL-018), `tests/e2e/test_bolus_timing.py` (the net-new S-302 client block + prompt; 15-before→−15) | ✅ Done (client + server) |
| **REQ-010** (post-BG entry <15s) | S-303 | `tests/e2e/test_post_bg_flow.py`; `PATCH …/post-bg` (one number + one time) | ✅ Done |
| **REQ-011** (late/retrospective asks real time) | S-303 | `test_post_bg_time_is_required` (422, never assumed); editable reported field | ✅ Done |
| **REQ-014** (test-time prompt = mealtime+120) | S-301, **S-303** | `test_test_time_prompt_is_reported_mealtime_plus_120` (10:00 not 11:40) | ✅ Done |
| **REQ-050** (hourly snapshot; app.db never in synced folder) | S-304 | `tests/safety/test_backup_restore.py` (synced rejected; backup-during-write valid) | ✅ Done |
| **REQ-051** (restore drill executed in month one) | S-304 | `test_restore_drill_is_ok_and_faithful` + **drill executed 2026-07-15** (`docs/durability-drills.md`) | ✅ Done (drill run) |
| **REQ-052** (nightly CSV export) | S-304 | `test_export_writes_a_csv_per_table_with_headers` | ✅ Done |
| **REQ-012 / INV-7** (hypo rescue captured; independent ledger reconciles rescued rows) | **S-305** | `tests/integration/test_hypo_rescue.py` (★ row-deletion ⇒ raise; flag-clear ⇒ raise; ledger has no cascading FK; migration; API appends) | ✅ Done (closes DL-019/H4) |
| **REQ-013** (correction-only events captured; +4 h follow-up; `iob_at_start` computed) | **S-306** + **S-306b** | `tests/integration/test_correction_events.py` (POST + bolus_log; +4h prompt at reported+4h; ★ clean-events exclude food_in_window==True AND NULL iob), `test_correction_schema.py`, `tests/a11y/test_corrections_form.py`; **S-306b** `test_correction_iob.py` (iob_at_start computed from prior boluses, excludes the correction; backfill; high/low-IOB clean filter) | ✅ Done — `iob_at_start` computed (S-306b discharged DL-020); ISF derivation S-502 |
| **REQ-053** (operator adherence dashboard: valid rate, exclusions, `median(logged_at − datetime)`, days-since-last-log) | **S-307** | `tests/integration/test_adherence.py` (valid/gate1 countdown; exclusions-by-reason; in-window rate; days-since-log; ★ median lag from the two distinct columns, asserted ≠ 0; empty-DB safe; `/api/adherence` + `/operator` render) | ✅ Done — **closes EPIC 3** |
| **REQ-020** (IOB derived from `bolus_log`; Fiasp exponential tp=55 td=240; no manual entry) | **S-401** | `tests/unit/test_iob.py` (★ monotone-decreasing on (0,td); ∈[0,1]; f(0)=1/f(240)=0/f(−5)=1; golden 6 pairs 4 dp; iob_at additive) + `detect_manual_iob` clean | ✅ Done — **opens EPIC 4** |
| **REQ-021** (effective basal = EWMA halflife 25h; multi-day carryover; not raw dose) | **S-402** | `tests/unit/test_basal.py` (★ step 24→30: +1d strictly between, +5d within 0.5 of 30; flat series constant; lockout change-day..+3d flagged, +4d clear) | ✅ Done |
| **REQ-024** (exercise one-hot + duration interactions; never numeric 0/1/2) | **S-403** | `tests/unit/test_exercise.py` (none=baseline; light/intense indicators + *_min; ★ light/60 vs intense/60 not scalar multiples ⇒ opposite-signed effects representable) | ✅ Done |
| **Feature pipeline** (`07` §5; pre_bg continuous; sample_weight; scaler train-folds-only; temporal CV) | **S-404** | `tests/unit/test_pipeline.py` (feature_vector, sample_weight, one-hot); `tests/leakage/test_leakage.py` (★ no target leakage; pre_bg not binned; forward-chaining folds ordered + day-disjoint; scaler train-fold ≠ full-set) | ✅ Done — **closes EPIC 4** |
| **REQ-030** (baseline predictor; bin via shared state fn; the bar to beat) | **S-501** | `tests/unit/test_baseline.py` (zero⇒post=pre; ★ directionality; 5 golden bg+state; INV-6 raises out of range), `tests/unit/test_state.py` (boundaries [54,80,181,251]; monotone) | ✅ Done — **opens EPIC 5** |
| **REQ-033** (ISF from correction events; ≥5 clean; never silent swap; ISF≤0 raises) | **S-502** | `tests/unit/test_isf.py` (5⇒applied source=derived; 4⇒default+derived reported; ★ ISF≤0 raises; no events⇒default), `tests/integration/test_isf_derivation.py` (confounded/pending excluded; +4h required) | ✅ Done — consumes S-306b iob_at_start |
| **REQ-032 / INV-8** (β_insulin sign-constrained ≥0; unconstrained-negative reported) | **S-503** | `tests/unit/test_params.py` (clean recovers ICR/ISF; ★ confounded ⇒ unconstrained β_ins<0, warning fired, applied β_ins≥0; INV-8 guard; cross-check prefers correction events) | ✅ Done — **closes EPIC 5** |
| **REQ-031** (one ordinal proportional-odds logit; `pre_bg` continuous; L2; hypo states up-weighted × macro-confidence) | **S-601** | `tests/unit/test_ordinal.py` (probabilities sum to 1; ★ ordinal sanity — `P(state≥4)` non-decreasing in `pre_bg`; multiplicative hypo×confidence weights; L2 shrinks feature coefs; one model covers all 5 states; `prob_at_least` above-range ⇒ 0) + forbidden greps (`multi_class`, per-state `fit()` loop, `accuracy_score` all absent) | ✅ Done — **opens EPIC 6**; `method="lbfgs"`→`"bfgs"` + absent-class refusal deferred (DL-025) |
| **REQ-031** (07 §8 escalation: proportional-odds test after every fit; escalate on rejection) | **S-602** | `tests/unit/test_brant.py` (PO-satisfying data passes, no raise; ★ threshold-varying data fails AND `check_proportional_odds` raises `ProportionalOddsViolation`; violation names the non-proportional predictor; `<3` states raises; omnibus/per-predictor df) | ✅ Done — Brant test + typed escalation; partial-PO *fitter* deferred to a real rejection on live data (DL-026); `statsmodels.api` unusable under scipy 1.18 → local Newton logits (DL-026) |
| **REQ-031 / INV-8** (07 §8 step 3: Bayesian ordinal at n≥200; priors encode INV-8 as a sign constraint; credible intervals not point estimates) | **S-603** | `tests/unit/test_bayesian_ordinal.py` (★ posterior `β_insulin` support only ≥0 on confounded data; HDI has positive width — an interval, not a point; ★ intervals widen as n shrinks; INV-8 wired on draws; `bayesian_gate_open` False@199/True@200; bad-col & `<3`-states raise) | ✅ Done — **closes EPIC 6**; PyMC `OrderedLogistic`, `HalfNormal` insulin prior (support ≥0 by construction, enters η negatively); PyMC added + numpy repinned 2.4.6 (DL-027) |
| **REQ-034 [SAFETY]** (forward-chaining temporal CV, never random; no `date` in both train and test in any fold; scaler train-only) | **S-701** | `tests/leakage/test_temporal_cv.py` (runner yields OOS preds, folds ordered+day-disjoint; ★ injected leaky fold — shared day / out-of-order — raises `TemporalLeakageError`; ★ shuffled random split rejected; scaler train-only under a test-fold outlier; ★ runs against the real `fit_ordinal`→`predict_proba`, OOS proba sum to 1; empty/scale-false edges) + forbidden grep (`shuffle=True` absent) | ✅ Done — **opens EPIC 7**; `models/validation.py::temporal_cv` re-asserts the temporal invariants on every fold at fit time (adversarial defense-in-depth) |
| **REQ-035** (metric suite: hypo recall @ fixed FAR **primary**, Brier, calibration, MAE, Clarke grid, off-by-one; **plain accuracy NOT reported**) | **S-702** | `tests/unit/test_metrics.py` (★ hypo recall @ FAR — threshold holds FAR≤target, recall correct, perfect/useless bounds; Brier golden + perfect⇒0; reliability well-calibrated + empty-bin skip; MAE golden; ★ Clarke goldens incl. the two **D** fails-to-detect cases `(50,120)`/`(300,150)` + **E** reversals; off-by-one & severe-state rates; module exposes **no** `accuracy`/`accuracy_score`) + forbidden grep (`accuracy_score` absent tree-wide) | ✅ Done — `models/metrics.py`; consumes S-701 OOS predictions; danger-weighted Clarke (D/E) is the point, not magnitude |
| **REQ-040/041 [SAFETY]** (no patient output before Gate 1 (INV-2); prescriptive hard-disabled before Gate 2 (INV-1); live every call, never cached — ADR-7) | **S-703** | `tests/safety/test_gates.py` (★ icr=null ⇒ `recommend_bolus` `GateNotPassed`; ★ **no bypass** — no override param, no env var; gate open ⇒ `NotImplementedError` not a fabricated dose; 149 closed / 150+recall>baseline open; ★ 200 w/ recall≤baseline **still closed** + tie closed; live-not-cached; `GateNotPassed` is a `SafetyViolation`; constant == adherence) | ✅ Done — **closes EPIC 7, UNBLOCKS EPIC 9**; `prescribe/gates.py` + `prescribe/bolus.py`; gates fail-closed, route through `core/safety` INV-1/INV-2; `prescribe` added to mypy + coverage gates |
| **REQ-044/046 [SAFETY]** (output guardrails — OOD, sparse, diffuse posterior, baseline conflict; predicted BG outside [20,600] hard error (INV-6); refusal is a valid output) | **S-801** | `tests/safety/test_guardrails.py` (OOD & sparse refuse `state=None`; ★ diffuse — max p=0.39 ⇒ "not confident", 0.41 ⇒ a state; ★ baseline 3 vs model 5 ⇒ both shown, `conflict=true`, **no winner** (`state=None`), 1-apart not a conflict; ★ absurd 601/19 raise INV-6, 600/20 do not, absurd checked before a refusal can mask it; clean confident path) | ✅ Done — **opens EPIC 8**; `models/guardrails.py`; never fills the silence with a number |
| **REQ-045 [SAFETY]** (every prediction written to `prediction_log` **before** it is returned — INV-9; write-then-display enforced, not incidental) | **S-802** | `tests/integration/test_prediction_log.py` (happy path — row persisted & queryable with correct fields by the time it returns; ★ mock persistence: `flush` leaves no id ⇒ INV-9 raises, `flush` raises ⇒ propagates — **no prediction returned** either way; `serve_prediction` maps a `GuardedPrediction`, persists first, sets `guardrail_fired` on a refusal; ★ serve refuses to return on a failed write) | ✅ Done — `data/predictions.py`; `record_prediction` flushes + `inv9_prediction_persisted` **before** the return; `serve_prediction` inherits the guarantee |
| **REQ-047 [SAFETY]** (kill switch on drift; **re-arming is manual only** — a later good run must not silently re-enable it) | **S-803** | `tests/integration/test_kill_switch.py` (drift `rolling<baseline` trips + persists; ★ after a trip a **good** run leaves it tripped — `evaluate_kill_switch` only ever *sets*; ★ `rearm(operator_confirmed=False)` raises `ManualReArmRequired` & stays tripped, `=True` clears it; healthy model untripped; unknown version raises) | ✅ Done — `prescribe/kill_switch.py`; state persisted on `model_artifact.kill_switch_tripped`; the only un-trip door is manual, a machine cannot open it; fails safe to the baseline |
| **REQ-040 [SAFETY]** (patient risk readout — hypo risk the headline; plain language; refusal a rendered state; **never advice**; INV-2 first patient-reachable surface) | **S-804** | `tests/safety/test_readout.py` (★ 149 valid meals ⇒ `build_patient_readout` raises `GateNotPassed`; ★ **no bypass** — no override param, no env var; hypo risk is the headline (State-2 ⇒ elevated/high, State-3 ⇒ in_range, State-5 ⇒ reduced); refusal rendered as a state (`state=None`, plain body, not a blank); ★ **never advice** — no `dose`/`bolus`/`units` attribute or directive; kill switch ⇒ baseline fallback; conflict shows both, no winner; severity/hypo_risk are **text** not colour) | ✅ Done — **closes EPIC 8**; `prescribe/readout.py`; `require_gate1` first, no bypass; a dose cannot ride a risk screen; signal is textual (a11y) |
| **REQ-048** (shadow mode ≥90 days — **enforced by S-1007**, `gate1_status(..., shadow_days)` + `data.repositories.shadow_days`, derived from `prediction_log`, never a stored flag; see the EPIC 10 section below) | **S-1007** | `tests/safety/test_gates.py` + `tests/integration/test_shadow_clock.py` (★ 89 ⇒ closed / 90 ⇒ open; ★ 500 days never substitutes for volume, baseline or promotion; ★ required, not defaulted; ★ no predictions ⇒ 0; earliest row not latest, not the row count; ★ backwards clock ⇒ 0; ★ not memoised; ★ `now` keyword-only, no default; ★ no `shadow*` column on any table) | ✅ Done 2026-07-18 — **first enforcement of REQ-048**; `SHADOW_MIN_DAYS = 90` traced to the requirement; `prescribe/gates.py` stays DB-free; DL-040 |
| **REQ-048** (operator reviews shadow output before any patient-visible output — the *evidence screen*) | **S-805** | `tests/unit/test_shadow.py` (report aggregates hypo recall @ FAR / calibration bins / Clarke grid / MAE / off-by-one / severe; predictions-vs-actuals confusion sums to n; ★ `unconstrained β_ins<0` ⇒ `beta_insulin_confounding=True`, healthy ⇒ False; Clarke **D** danger preserved; multiclass Brier when a distribution is supplied) | ✅ Done — `models/shadow.py::build_shadow_report`; composes the S-702 metrics (no plain-accuracy headline) + surfaces the INV-8/S-503 confounding alarm on the operator's Gate-1 evidence screen |
| **REQ-041/042/043 [SAFETY]** (prescriptive bolus calculator — clinical formula only, **no ML in the dose path**; INV-1/3/4; full arithmetic shown; suggestion for review) | **S-901** | `tests/safety/test_bolus.py` (★ INV-4 BG 79 refuses / 80 computes; ★ INV-3 carbs=900 typo ⇒ capped 15 U **AND** `implausible_input` flagged; negative ⇒ 0.0; ★ INV-1 icr=null ⇒ `GateNotPassed`, no bypass param/env; ★ **5 golden hand-computed doses** to 2 dp; property — non-decreasing in carbs, non-increasing in IOB; **no `models` import** in the dose path; arithmetic shown + framed as review) | ✅ Done — **closes EPIC 9 (final story)**; `prescribe/bolus.py::recommend_bolus`; ICR 9 / ISF 30 / target 135 clinician-confirmed (DL-032), read from the versioned profile — no hardcoded constant; human gate + code gate both cleared |
| **REQ-006** (every bolus → `bolus_log`) | S-201 | `test_bolus_log_roundtrips` | ✅ Schema done |
| **REQ-007** (daily Tresiba → `basal_log`) | S-201 (schema) · **S-1013 (capture)** | `tests/integration/test_basal_capture.py` (15) — ★ `time_taken` reported vs `logged_at` from an injectable clock fixed months away (ADR-8); ★ a repeat date **corrects**, audited old→new, never duplicates (two rows would double-count in the EWMA and show a titration that never happened); a first entry is **not** audited as a change; ★ `basal_doses` → `effective_basal` matches the S-402 EWMA with the timestamp built from the **reported** date + time (asserted not midnight, not the clock); ★ a 24→30 U step is **smoothed, not stepped**; ordered by reported date; non-positive refused; the endpoint **requires** `time_taken`. Plus `tests/forbidden/` `detect_raw_basal_dose_as_feature` | ✅ **Done 2026-07-18 — the gap DL-046 found is closed.** Previously ⚠️ schema-only: the row claimed *"form: S-302/EPIC 3"* and no such form existed, so **the model could not be fitted on real data at all**. **Unblocks S-1009.** Four guards seen to fire on a clean tree. |
| **REQ-054** (constants versioned, never overwritten) | S-201 (schema) · **S-1010 (the writer)** | `test_patient_profile_change_creates_a_new_row`, `test_patient_profile_is_immutable_in_place`; **S-1010** `test_appending_leaves_the_previous_version_completely_intact` | ✅ **Done.** Previously the schema *permitted* versioning with nothing exercising it — S-1010 adds the only code path that appends one. |
| **REQ-061** (operator updates ICR/ISF/target) | **S-1010** | `tests/integration/test_profile_update.py` (21) — ★ appending leaves the previous row intact **field-for-field** (an `UPDATE` would pass every "the calculator sees the new value" test and destroy the record of what it was actually using); ★ the calculator reflects a new version **on the next call**, not a cached one (ADR-7 in spirit); ★ out-of-range is **flagged and still written** (ICR 20 lands) — blocking would send the change to a hand-edit nobody audits; ★ a 10× typo flags on **relative** change, catching a misplaced decimal point without inventing an ISF band `04 §1` does not give; an ordinary 9 → 8.5 flags **nothing** (a screen that warns about everything warns about nothing); the first-ever version is not a "large change"; `icr`/`isf`/`target_bg` non-positive **refused with nothing written**; only **changed** fields audited old→new | ✅ **Done 2026-07-29 (DL-048).** Three plants seen to fire on a clean tree. |

> No `REQ-nnn` is claimed by S-101; it is an infrastructure story.
> **S-102** also maps to no numbered REQ — the backlog cites its requirement
> source directly as `05b §2` (Accessibility — Non-Negotiable). It is recorded
> above against that source so the accessibility floor is not an untraced gap.
> The numbered REQ register (`01-prd.md` §5) begins to be consumed at EPIC 2.

## INV → story → test

Legend: **Module ✅** = the invariant function + its positive/negative tests
exist in `core/safety.py` (S-104). **Wired** = called from the feature it
guards (per later story). A green Module row is necessary but not sufficient —
each invariant must still be *wired in* by the story that owns its feature.

| INV | Function (`core/safety.py`) | Test(s) | Module | Wired into feature |
|-----|-----------------------------|---------|--------|--------------------|
| ~~INV-1~~ **RETIRED** | ~~`inv1_prescriptive_requires_gate2`~~ — **removed** (S-1011, DL-035) | `test_safety_invariants.py::test_inv1_*`; **wiring:** `test_gates.py` + `test_bolus.py` (icr=null ⇒ `recommend_bolus` raises `GateNotPassed`; ★ no bypass param/env/flag; gate open ⇒ **computes a real dose**) | ✅ S-104 | ⛔ **RETIRED S-1011 (2026-07-18, DL-035)** — operator-directed de-gating. `recommend_bolus` now raises a plain `ValueError` on a missing/`<= 0` ICR; `test_bolus.py` asserts it is **neither** a `SafetyViolation` **nor** a `GateNotPassed`, and that the symbol is absent (not dormant). **INV-3/INV-4 unchanged; Gate 1/INV-2 unaffected. The number is not reused.** |
| INV-2 | `inv2_patient_output_requires_gate1` | `test_safety_invariants.py::test_inv2_*`; **wiring:** `test_gates.py` (149 ⇒ `require_gate1` raises; 150+recall>baseline ⇒ opens; ★ 200 w/ recall≤baseline still closed); `test_readout.py` (patient surface raises at 149, no bypass) | ✅ S-104 | ✅ **S-703** (`require_gate1`) + **S-804** — the patient risk readout (`prescribe/readout.py`) is the first patient-reachable surface and calls `require_gate1` on its first line, no bypass; ungated model output cannot reach her |
| INV-3 | `inv3_bolus_within_bounds` | `test_safety_invariants.py::test_inv3_*`; **wiring:** `test_bolus.py` (★ carbs=900 typo ⇒ capped 15 U **AND** `implausible_input` flagged; negative computed dose ⇒ 0.0) | ✅ S-104 | ✅ **S-901** — `recommend_bolus` caps + flags an implausible input (never a silent clip) and floors at 0; `inv3` re-asserts the bound |
| INV-4 | `inv4_bolus_allowed_at_bg` | `test_safety_invariants.py::test_inv4_*`; **wiring:** `test_bolus.py` (BG 79 ⇒ refuses; BG 80 ⇒ computes) | ✅ S-104 | ✅ **S-901** — `recommend_bolus` refuses to dose below BG 80 (treat the low first) |
| INV-5 | `inv5_monitoring_not_reduced` | `test_safety_invariants.py::test_inv5_*` | ✅ S-104 | ⏳ output/advice stories |
| INV-6 | `inv6_predicted_bg_in_range` | `test_safety_invariants.py::test_inv6_*`; **wiring:** `test_baseline.py` (out-of-range prediction raises); `test_guardrails.py` (absurd predicted BG raises, checked before any refusal can mask it) | ✅ S-104 | ✅ **S-501** (baseline prediction path) + **S-801** — the output guardrail evaluates INV-6 **first**, so a physiologically absurd BG is a hard error, never downgraded to a refusal message |
| INV-7 | `inv7_rescued_excluded_and_retained` | `test_safety_invariants.py::test_inv7_*`; **wiring:** `test_repositories.py` (regression guard + wiring-bites); **ledger reconciliation:** `test_hypo_rescue.py` (row-deletion + flag-clear ⇒ raise) | ✅ S-104 | ✅ **S-203** wired + **S-305** independent ledger closes the DB-row-deletion gap (DL-019/H4) |
| INV-8 | `inv8_beta_insulin_non_negative` | `test_safety_invariants.py::test_inv8_*`; **wiring:** `test_params.py` (applied β_ins≥0; unconstrained-negative reported); `test_bayesian_ordinal.py` (posterior support ≥0; wired on the sampled minimum) | ✅ S-104 | ✅ **S-503** (constrained OLS) + **S-603** (Bayesian ordinal: `HalfNormal` prior gives the posterior zero density below 0 — the sign constraint is the prior's support, not a clamp; the invariant is still asserted on the draws). The frequentist ordinal (S-601) does **not** gate a dose (ADR-10), so INV-8 does not constrain it there. |
| INV-9 | `inv9_prediction_persisted` | `test_safety_invariants.py::test_inv9_*`; **wiring:** `test_prediction_log.py` (write-before-return enforced; mocked persistence failure ⇒ no prediction returned) | ✅ S-104 | ✅ **S-802** — `data/predictions.py::record_prediction` flushes to `prediction_log` and asserts INV-9 **before** returning; a failed write raises, never degrades to an unlogged prediction |
| _module hygiene_ | no-`assert` (AST), zero internal imports (ADR-6), single-definition, `-O` still raises | `test_safety_module_hygiene.py` | ✅ S-104 | — |

S-101 introduces no invariant logic. It provides the ruff/mypy/pytest/coverage
gates that S-104 and S-105 rely on to be enforceable at all.

**S-103 note (updated by S-1011):** the config property is now `icr_present`
(`icr is not None`) — renamed from `prescriptive_enabled` when Gate 2 / INV-1 was
retired, because a property named "enabled" that enables nothing could be misread
as "the dose path is safely off". It reports state, never grants it; it cannot be
assigned or injected (adversarial tests prove this). Enforcement now lives in
`prescribe/bolus.py::recommend_bolus`, which raises a plain `ValueError` on a
missing or `<= 0` ICR. The config re-implements no invariant.

## Gaps / watch-list
- ~~The 90% coverage gate is enforced in **CI only** this session (DL-002).~~
  **Resolved (DL-004):** PyPI/npm egress is now open; the full dep set installs
  locally and the coverage gate (`--cov=core --cov-fail-under=90`) was verified
  locally this session as well as in CI.
- `api/` is exercised by the a11y suite but is **not** in `[tool.coverage.run]
  source` (still `core` only, per DL-003). `api/` is presentation; the DoD
  coverage bar is on `core/`, which S-102 does not touch. Widen `source` when
  business logic (not just template wiring) lands under `api/`.
- The a11y suite requires a Chromium build (DL-005). CI installs it; a runner
  without it turns the suite red rather than skipping silently — intentional.
- **INV-1..9 exist as functions with tests (S-104) but are not yet *wired* into
  the features they guard** (see the "Wired into feature" column). This is a
  tracked, expected gap — the invariants ship before the features per the build
  order. Each owning story must call its invariant and add the wiring test; do
  not let a feature ship guarding itself with an inline re-check instead of the
  `core/safety.py` function (the S-104 hygiene test forbids re-implementation).
- **Forbidden-pattern guards for not-yet-written code (S-105):** the manual-IOB
  and `pre_bg`-to-binner guards protect code that arrives in EPIC 4/5. When the
  shared state-binner is named (S-404/S-501), **add its name to `BINNER_NAMES`**
  in `tests/forbidden/test_forbidden_patterns.py`, or the pattern-8 guard scans
  for a function that does not exist and passes vacuously.

## Epic status
> **RED-first caveat (DL-017):** an independent audit found three deviations
> where a GREEN/implementation commit created or edited files under `tests/`
> (`9eff0ec` S-201, `b4e4cbf` S-103, `790e385` S-202). End state is correct and
> passing; see DL-017 for the decision on each. "RED-first" below is qualified by
> that entry, not unconditional.

- **EPIC 1 (Foundation) — COMPLETE.** S-101, S-102, S-103, S-104, S-105 — Done,
  green, RED-first (see DL-017 caveat for S-103).
- **EPIC 2 (Data Layer) — IN PROGRESS.**
  - **S-201 (schema + migrations) — Done.** 9 tables, Alembic initial migration,
    signed offset, DB-computed floored net-carbs, `logged_at`≠`datetime` with no
    now() default on clinical timestamps, append-only `patient_profile`.
  - **S-202 (reported timestamps, ADR-8) — Done.** Write-path discipline:
    `datetime`=reported, `logged_at`=injected system clock, `bolus_offset_min` /
    `elapsed_min` from reported times only. **First feature actively protected by
    the S-105 guard** (`detect_datetime_now_on_clinical_ts` scans `data/`, so
    `data/recording.py` cannot bind a now()-call to a clinical timestamp), plus a
    targeted write-path AST test (now() → `logged_at` only).
  - **S-203 (validity engine + INV-7) — Done.** Six exclusion rules (all
    applicable reasons); `get_training_set()` / `get_hypo_events()`. **First
    invariant wired into a feature** — `get_training_set()` calls INV-7, so a
    rescued meal cannot leak into training without raising. Regression guard
    (100 meals / 20 rescued) in place.
  - **S-204 (dish table, REQ-009) — Done.** Ingest path, portion scaling
    (2×roti=double), free-text ⇒ `macro_confidence=60` + queued. Seed macros are
    representative pending real IFCT-2017 data (DL-015).
- **EPIC 2 (Data Layer) — COMPLETE.** S-201..S-204 done, green, RED-first (see
  DL-017 caveat for S-201/S-202).
- **EPIC 3 (Logging & Durability) — ★ THE CRITICAL PATH — IN PROGRESS.**
  - **S-301 (meal-log form) — Done.** Repeat meal in **3 taps + 2 numbers**
    (favourite → BG → bolus → timing → LOG), `POST /api/meals` (offset required,
    server stamps `logged_at`, `test_at` = reported time + 120), `localStorage`
    draft that survives a kill. Risk-cue example relocated to `/components`
    (INV-2 — no model output on the form).
  - **S-302 (bolus timing) — Done.** REQ-003 enforced at both layers: schema
    (required, no default → 422) and form (empty offset blocked with a prompt;
    never auto-fills 0; empty ≠ a chosen 0).
  - **S-303 (post-meal reading + test-time prompt) — Done.** `PATCH
    …/post-bg` (reported `post_bg_time` required; `elapsed_min` from reported
    times; stored regardless of validity); `<15s` form with an editable reported
    "taken at"; test-time prompt = mealtime + 120.
  - **S-304 (backup + restore drill) — Done, drill EXECUTED.** `cli backup`
    (online snapshot), `cli export` (CSV/table), `cli restore-drill`;
    synced-folder guard. **★ The restore drill was run for real on 2026-07-15**
    (`docs/durability-drills.md`): ok=True, integrity ok, byte + data identical.
    Re-run monthly.
  - **S-305 (hypo-rescue capture) — Done.** New append-only `hypo_rescue_log`
    ledger, deliberately decoupled from `meal_event` (plain `meal_id`, no cascading
    FK). `get_recorded_rescue_meal_ids` = flagged ∪ ledgered feeds INV-7, so a
    hard-deleted rescued meal row (`rescued − hypo`) and a cleared `hypo_treatment`
    flag (`rescued & training`) now both raise. **Closes DL-019 / audit-H4** — the
    invariant was not re-implemented, only its `rescued_meal_ids` source made truer.
  - **S-306 (correction-only event capture) — Done.** Two-phase capture (log +
    +4 h follow-up) of a correction with no food — the clean ISF signal; the
    injection is written to `bolus_log` (REQ-006). `get_clean_correction_events`
    is the `07` §6 accessor; a NULL `iob_at_start` (deferred to S-401, DL-020) is
    excluded so the deferral cannot poison ISF. Accessible `/corrections` form.
  - **S-307 (operator adherence dashboard) — Done.** `data/adherence.py` +
    `GET /api/adherence` + `GET /operator`: valid-meals / 150-to-Gate-1 countdown,
    in-window rate, exclusions by reason, days-since-last-log, and the ★
    `median(logged_at − datetime)` transcription-lag metric computed from the two
    distinct columns (the ADR-8 payoff — the recall-bias early-warning). Read-only,
    operator-only, no model output.
  - **★ EPIC 3 is complete — the system is at the SHIP line.** Logging (meals,
    timing, post-BG, hypo rescue, correction events), durability (backup + drill),
    and the adherence cockpit are all in. Shipping starts the **Gate-1 clock**
    (150 valid meals ≈ 3 months of collection).
  - **EPIC 4 open — S-401 (IOB engine) Done.** `features/iob.py`: the Fiasp
    exponential IOB curve (tp=55, td=240), bounded [0,1], strictly decaying on
    (0,td), locked by 6 golden pairs; `iob_at` additive over `bolus_log`
    injections. Derived only — no manual-entry path (`detect_manual_iob` clean).
    Creates the `features/` package; the binner tripwire correctly stays scoped to
    `models/` (06 §arch).
  - **S-306b (discharge DL-020) — Done.** With the engine live,
    `correction_event.iob_at_start` is now computed at capture from prior
    `bolus_log` injections (`iob_at_start_at`), excluding the correction bolus
    itself; `backfill_correction_iob` fills any deferred NULLs. The `07` §6
    clean-ISF filter now runs on a real IOB value. IOB stays derived
    (`detect_manual_iob` clean).
  - **S-402 (effective basal) — Done.** `features/basal.py`: degludec EWMA
    (half-life 25 h) so a dose change ramps over days (not the forbidden raw dose),
    plus a 3-day titration lockout that suppresses basal guidance during the ramp.
  - **S-403 (exercise encoding) — Done.** `features/exercise.py`: one-hot
    light/intense indicators + duration interactions (none = baseline). light/60
    and intense/60 are not scalar multiples, so the model can represent
    opposite-signed effects (light lowers, intense raises) — the physiology a
    numeric 0/1/2 column forbids.
  - **★ S-404 (feature pipeline) — Done. EPIC 4 COMPLETE.** `features/pipeline.py`
    assembles the `07` §5 vector (pre_bg continuous, targets absent by
    construction, macro_confidence/100 as sample_weight, StandardScaler fit on
    train folds only); `features/cv.py` gives forward-chaining temporal folds (no
    day in train+test; train precedes test). New `tests/leakage/` suite (09 §7)
    runs every commit. scikit-learn pinned (DL-022). **All derived features — IOB,
    effective basal, exercise, and the leakage-safe pipeline — are in.**
  - **EPIC 5 open — S-501 (baseline model) Done.** `models/state.py` (`bg_to_state`,
    the shared binner on boundaries [54,80,181,251]) + `models/baseline.py`
    (07 §4 formula, INV-6 on the prediction). **Creating `models/` armed the H3
    binner tripwire** — it now runs and passes (`bg_to_state` registered); the
    `pre_bg`→binner input guard stays clean (baseline bins the output). models/ is
    in the mypy + coverage gates.
  - **S-502 [SAFETY] (ISF from correction events) — Done.** `models/isf.py`
    `derive_isf` (mean `(bg_before−bg_after)/units` over clean events) behind three
    guards: ≥5-event gate, never-silent-swap (both values returned), and a hard stop
    on any derived ISF ≤ 0. `data/repositories.py::derive_isf_from_correction_events`
    bridges the S-306/S-306b clean-event filter (food-free, low IOB) and requires a
    +4 h reading. Nothing mutates `patient_profile` — applying is an explicit
    operator step (REQ-054).
  - **★ S-503 [SAFETY] (constrained OLS) — Done. EPIC 5 COMPLETE.**
    `models/params.py` `fit_icr_isf`: the applied fit is `lsq_linear` with
    `b_bolus ≤ 0`, so `β_ins ≥ 0` by construction (INV-8, re-asserted); the
    *unconstrained* fit is computed and, when it wants `β_ins < 0` (insulin
    appearing to raise glucose — confounding by indication), a prominent WARNING is
    logged and the flag set — reported, never swallowed. `cross_check_isf` prefers
    the unconfounded correction-event ISF on material disagreement. scipy pinned
    (DL-024). **The baseline, the ISF/ICR estimators, and the state binner are all
    in — with INV-6 and INV-8 wired into real fits.**
  - **EPIC 6 open — S-601 (ordinal model) Done.** `models/ordinal.py`
    `fit_ordinal`: **one** `statsmodels OrderedModel` (proportional-odds logit,
    `distr="logit"`), `pre_bg` continuous, feature coefficients L2-penalised via a
    thin weighted subclass, and hypo states (1, 2) up-weighted **multiplicatively**
    with the macro-confidence weights. `predict_proba` rows sum to 1 and
    `prob_at_least(·, 4)` = `P(state≥4)` is monotone in `pre_bg` (structural under
    proportional odds). Deviations recorded (DL-025): the spec's `method="lbfgs"` is
    `"bfgs"` under the pinned statsmodels/scipy; an **unobserved** state is modelled
    honestly (observed states only, reported via `OrdinalFit.states`) rather than
    forced to a non-summing fit or a silent `P=0` for a missing hypo class — the
    latter refusal is deferred to the gate/risk stories (S-703/S-804). Forbidden
    greps (`multi_class`, per-state fit loop, `accuracy_score`) stay green; `pre_bg`
    reaches the binner only on the OUTPUT path.
  - **S-602 (Brant test + partial PO) Done.** `models/brant.py` `brant_test` runs the
    proportional-odds check after every fit: per-threshold binary logits (local Newton
    — `statsmodels.api`/`Logit` is unusable under scipy 1.18, DL-026), the Brant (1990)
    covariance sandwich, and an omnibus + per-predictor Wald χ². `check_proportional_odds`
    is the gate — it **raises `ProportionalOddsViolation`** (the escalation) on
    rejection, carrying the `violators` that a partial-PO fit would free. The partial-PO
    *fitter* is deferred to a real rejection on live data (DL-026): surface the
    modelling decision, do not default it.
  - **★ S-603 [SAFETY] (Bayesian ordinal) — Done. EPIC 6 COMPLETE.**
    `models/bayesian_ordinal.py` `fit_bayesian_ordinal`: PyMC `OrderedLogistic`,
    weakly-informative priors, and a `HalfNormal` prior on the insulin coefficient
    (support ≥0) that enters η with a **negative** sign — so INV-8 lives in the
    prior's support and every posterior draw is ≥0 by construction, for any data
    however confounded; the invariant is still asserted on the sampled minimum. Output
    is a **credible interval** (arviz HDI), not a point estimate, and the interval
    widens as n shrinks. `MIN_BAYESIAN_N=200` / `bayesian_gate_open` is the 07 §8
    production gate. PyMC added + numpy repinned 2.4.6 (DL-027, user-approved).
    **The ordinal model, its proportional-odds check, and the Bayesian form are all
    in — INV-8 now holds in both the OLS and the Bayesian fit.**
  - **RED-first caveat for S-601/S-602/S-603 (DL-028, audit 2026-07-17-01 F1):** each
    story's RED tests were real and seen to fail in their own `test(S-nnn): RED` commit,
    but three GREEN commits (`e746290`, `bc4f462`, `305f967`) edited `tests/` — adding
    edge tests and, in S-601, **loosening** the `HYPO_STATES` exactness assertion. A
    **recurrence of DL-017**; no safety invariant weakened. SDET has restored the exact
    `frozenset({1, 2}) == HYPO_STATES` pin and adopted the edge tests. "RED-first" for
    these three is **commit-granularity qualified** — see DL-028.
  - **★ S-701 [SAFETY] (temporal CV runner) — Done. EPIC 7 OPEN.**
    `models/validation.py::temporal_cv` drives the **actual** model across
    forward-chaining folds and — adversarially — **re-asserts on every fold** that
    `max(train.datetime) < min(test.datetime)` and that no calendar day straddles the
    split (`assert_temporal_split` raises `TemporalLeakageError`), so a leaky or shuffled
    split **raises instead of scoring**. The scaler is fit on the train fold only; the
    runner is model-agnostic and produces genuine **out-of-sample** predictions
    (verified end-to-end against `fit_ordinal`→`predict_proba`). `shuffle=True` stays
    absent (forbidden guard). This is the guard against the project's most likely
    failure — a model that looks brilliant on retrospective data and is quietly wrong
    about a low.
  - **S-702 (metric suite) — Done.** `models/metrics.py`: hypo recall @ fixed FAR
    (**primary**), multiclass Brier, reliability/calibration curve, MAE, the Clarke
    error grid (danger-weighted — D = failure to detect a low, E = reversed reading),
    off-by-one and severe-state-error rates. **Plain accuracy is not a function in the
    module** and `accuracy_score` is absent tree-wide (forbidden guard). Consumes the
    out-of-sample predictions from S-701.
  - **★ S-703 [SAFETY] (gate enforcement) — Done. EPIC 7 COMPLETE; EPIC 9 UNBLOCKED.**
    `prescribe/gates.py` evaluates both gates as pure, fail-closed functions of **live**
    inputs (never cached — ADR-7): Gate 1 (INV-2) opens only on ≥150 valid meals **AND**
    the model **strictly** beating the baseline on hypo recall (volume alone / a tie is
    inert); Gate 2 (INV-1) opens only on a confirmed ICR. `prescribe/bolus.py::recommend_bolus`
    checks Gate 2 on its first line every call and has **no bypass** — no override param,
    no env var, no config flag; `icr=null` ⇒ `GateNotPassed`, gate-open ⇒
    `NotImplementedError` (the dosing math is EPIC 9, never a fabricated dose). Both gates
    route through the `core/safety` invariants; `prescribe` is now in the mypy + coverage
    gates. **The prescriptive module cannot touch a dose, and she cannot see model output,
    until each gate is earned from live data.**
  - **★ S-801 [SAFETY] (output guardrails) — Done. EPIC 8 OPEN.** `models/guardrails.py`
    `guard_prediction` runs the five 07 §10 checks in order: absurd predicted BG raises
    INV-6 **first** (never masked by a refusal); out-of-distribution, sparse-region, and
    a diffuse posterior (max p ≤ 0.40) each **refuse** with `state=None`; a baseline
    conflict (> 1 state apart) returns **both** flagged with **no winner** picked. A
    refusal is a valid output — the layer never fills the silence with a number.
  - **★ S-802 [SAFETY] (prediction log) — Done.** `data/predictions.py::record_prediction`
    flushes the row to `prediction_log` and asserts `inv9_prediction_persisted` **before**
    it returns — write-then-display is enforced, not incidental: a mocked persistence
    failure (`flush` yielding no id, or raising) makes it raise and return **no**
    prediction. `serve_prediction` maps a `GuardedPrediction` (S-801) and persists first,
    inheriting the guarantee. Every returned prediction is therefore in the audit trail — a
    wrong-about-a-low is findable.
  - **★ S-803 [SAFETY] (kill switch) — Done.** `prescribe/kill_switch.py`:
    `evaluate_kill_switch` trips on drift (rolling hypo recall below the baseline) and
    **only ever sets** the flag — no sequence of good runs can un-trip it; the sole clear
    is `rearm(operator_confirmed=True)`, which raises `ManualReArmRequired` otherwise. State
    is persisted on `model_artifact.kill_switch_tripped`, so a restart cannot come up armed
    after a trip, and a tripped switch fails safe to the ML-free baseline.
  - **★ S-804 [SAFETY] (patient risk readout) — Done. EPIC 8 COMPLETE.**
    `prescribe/readout.py::build_patient_readout` is the first patient-reachable INV-2
    surface: it calls `require_gate1` on its first line (n=149 raises `GateNotPassed`; no
    override param, no env var), leads every readout with the **hypo-risk headline**,
    renders a refusal / conflict / kill-switch suppression as a definite **rendered state**
    (never a blank), carries the signal as **text** (`hypo_risk`/`severity`, not
    colour-only), and has **no** `advice`/`dose`/`bolus`/`units` field — a dose can never
    ride a risk screen. The HTML rendering of the readout is deferred to live-model wiring
    (no patient-visible prediction exists to render before then).
  - **S-805 (shadow-mode dashboard) — Done.** `models/shadow.py::build_shadow_report`
    composes the S-702 metric suite (hypo recall @ FAR, calibration, Clarke grid, MAE,
    off-by-one/severe) into the operator's pre-Gate-1 evidence report, with a
    predictions-vs-actuals confusion matrix and the **`β_insulin < 0` confounding alarm**
    on the same screen — no plain-accuracy headline. Operator-only (INV-2 governs patient
    output; the operator is the pre-Gate-1 audience).
  - **EPIC 8 COMPLETE** — output guardrails (S-801), prediction log/INV-9 (S-802), kill
    switch (S-803), patient readout/INV-2 (S-804), shadow-mode dashboard (S-805) all in.
  - **★ S-901 [SAFETY] (bolus calculator) — Done. EPIC 9 COMPLETE — the build is finished.**
    Both gates cleared: the **code gate** (S-703, green) and the **human gate** — the
    endocrinologist confirmed **ICR 9 g/U, ISF 30 mg/dL/U, target 135** (OQ-1/OQ-2/OQ-6,
    DL-032), stored in the versioned `patient_profile` and read as parameters (no hardcoded
    constant; updatable by a new profile version). `prescribe/bolus.py::recommend_bolus` is
    the clinical formula only — **no ML in the dose path** — behind the live Gate-2 check
    (INV-1, no bypass): it refuses below BG 80 (INV-4), caps at 15 U **and flags** an
    implausible input rather than silently dosing a typo (INV-3), floors at 0 (INV-3), shows
    the full arithmetic, and frames the number as a suggestion for review. Five golden
    hand-computed doses and the carbs/IOB monotonicity properties are pinned.
  - **BUILD COMPLETE.** EPICs 1–9 done; INV-1..9 all defined in `core/safety.py` and wired
    into real features with positive + negative tests; every forbidden pattern guarded; the
    prescriptive path is the clinical arithmetic only, behind two gates. The remaining work
    is operational, not code: collect ≥150 valid meals + ≥90 days shadow mode, then the
    operator's manual Gate-1 promotion on hypo recall.
  - Post-ship, in parallel with data collection: **EPIC 4** (S-401 IOB engine —
    backfills `iob_at_start`; features), **EPIC 5** (S-501 ISF derivation from the
    correction events; the ordinal model), gated on live data — INV-1/INV-2 hold.

- **EPIC 10 — Integration, UI & End-to-End Validation — BACKLOG (not started, DL-033).**
  Approved scope addition (operator, 2026-07-17). Builds the render layer that EPICs 5–9
  deferred, plus a synthetic-data generator and one end-to-end test. **Building the UI does
  not open any gate** — the patient/bolus screens call `require_gate1`/`require_gate2` first
  and render the refusal/baseline state before the gate. Status per story:
  - **REQ-055 → S-1001 (operator shadow dashboard UI) — Backlog.** Renders
    `build_shadow_report` (hypo-recall headline, Brier, calibration, Clarke grid,
    predictions-vs-actuals, `β_insulin < 0` alarm) + live gate status; operator-only; no
    plain accuracy; no dose. Test: `accuracy` absent from template; alarm renders; `axe`.
  - **REQ-040 / INV-2 → S-1002 [SAFETY] (patient readout UI) — Backlog.** Discharges the
    S-804 deferred presentation note. Route calls `require_gate1` first, no bypass; refusal/
    baseline is a rendered state, never a blank; **no dose field on the screen.**
  - **REQ-041/042/043 / INV-1/INV-3/INV-4 → S-1003 [SAFETY] (bolus calculator UI) —
    Backlog.** Route calls `require_gate2` first, no bypass; BG < 80 refuses; over-cap
    renders the flagged-implausible state; full arithmetic shown, framed as a suggestion,
    no autofill; imports nothing from `models/`.
  - **REQ-056 → S-1004 [SAFETY] (synthetic-data generator) — ✅ DONE 2026-07-18.**
    `synthetic/generator.py::generate(seed, days, start)` → `SyntheticDataset` (frozen
    dataclasses; **imports no Session/engine**, so calling it cannot contaminate a store).
    Tests `tests/unit/test_synthetic.py`: ★ same-seed **byte-identical** via a whole-dataset
    digest (not field-by-field — that silently stops covering fields added later); different
    seeds differ (else a constant passes); ★ **ADR-8 — `logged_at` strictly later than the
    reported `datetime`, never equal**, because equal timestamps would let an E2E run pass
    whether or not production respects the distinction; `elapsed_min` reconciles with
    **reported** times; ★ AST scan finds no clock read and no **global**-RNG call
    (`random.Random(seed)` exempt — SDET narrowed this on Dev's challenge, then re-verified
    the rule still bites); both bolus-offset signs occur; net carbs never negative; ★ hypo
    rate is a real **emergent** minority; ★ **`test_there_is_no_hypo_rate_knob`** — a caller
    who could dial the hypo rate could dial the headline metric; rescued meals exist with
    grams so INV-7 is testable end-to-end.
    Guard `tests/forbidden/::detect_synthetic_import` (S-105 lineage) — **proven to bite
    twice**: on a violating snippet via the pattern registry, and adversarially on a real
    planted `models/_probe_leak.py`, which failed the build and was then removed.
    **Placement deviates from the story text** (top-level `synthetic/`, not `tests/`) —
    **DL-039**, for SDET/Dev role separation. `synthetic/` joins `mypy --strict`; deliberately
    **not** added to the coverage gate (fixture code).
  - **REQ-057 → S-1005 [SAFETY] (end-to-end cycle test) — ✅ DONE 2026-07-18.**
    **The only artefact that checks the invariants across the seams.** The unit suite proves
    each holds *given its inputs*; nothing else proves those inputs are what the previous
    stage produced. `tests/integration/test_end_to_end_cycle.py` (12), one assertion per
    seam and named after it, over one seeded 120-day synthetic cycle written **through
    `annotate_validity`** rather than straight into the DB.
    ★ **Every seam seen to fail under a planted cross-stage violation** — rescued meals no
    longer excluded ⇒ the INV-7 assertion (and 4 more, the corruption propagating);
    `serve_prediction` returning before persisting ⇒ the INV-9 assertion; folds sharing one
    calendar date ⇒ the leakage assertion; the ICR check raising `GateNotPassed` ⇒ the
    "not a gate by another name" assertion (S-1011); the dashboard 403ing when the gate is
    shut ⇒ the INV-2 assertion, whose *other* half is that the readout refuses.
    ★ **New finding, asserted on real pipeline output:** the full cycle produces **188 valid
    meals**, clearing the 150 floor — and **Gate 1 is still shut** on the other four
    conditions. Volume is necessary and never sufficient (`03 §3`).
    ⚠️ **Process note (S-1005 outcome):** two plants were initially **no-ops**, and the
    suite's "all passed" nearly read as "the most important seam has no guard". A plant that
    does not change behaviour proves the reverse of what it looks like; plants are now
    marked and grepped for before the result is believed. Drives synthetic data
    through logging → INV-7 → features → fit → temporal CV → metrics → gates → readout →
    shadow dashboard → bolus, asserting INV-1/2/7/9 and gate refusals **across** the chain.
  - **★ Review addendum (2026-07-18, DL-034) — operational-spine stories added.** Holding
    S-1001–S-1005 against the full usage sequence exposed that Gate 1 opens automatically and
    `ModelArtifact.is_promoted` (schema, "manual only") is read nowhere — the manual-promotion
    pivot of the sequence was unwired. Conformance to `07 §Retraining` / REQ-048, not new
    gate decisions:
    - **REQ-058 → S-1006 [SAFETY] (Gate-1 manual promotion) — ✅ DONE 2026-07-18.**
      `gate1_status(..., is_promoted)` — **required, not defaulted** — opens only on
      `volume ∧ beats_baseline ∧ is_promoted`. `data/promotion.py::promote_model` /
      `revoke_promotion` are the **only** writers, both audited to `audit_log`
      (old→new, `changed_by`).
      Tests `tests/safety/test_gates.py` + `tests/integration/test_promotion.py` (17):
      ★ **the case the shipped code got wrong** — volume ✓ + beats-baseline ✓ + **not
      promoted ⇒ CLOSED**; ★ promotion alone never suffices (149 meals / recall ≤ baseline /
      a tie all stay closed) — promotion is the **last** condition, not a bypass;
      ★ **`is_promoted` is required** (omitting it raises `TypeError`), so a future default
      cannot quietly restore the old behaviour; no env var promotes; ★ **promoting v2 demotes
      v1 atomically**, both audited, because two promoted rows would make the served model
      depend on row order; unknown version raises and creates nothing; revoke clears + audits
      and takes effect on the next call (ADR-7); ★ **AST — no production module writes
      `is_promoted` outside `data/promotion.py`** (narrowed by SDET on Dev's challenge to the
      two real write paths, so `Gate1Status(is_promoted=…)` may still *report* it).
      **Closes DL-034 gap G1.**
    - **REQ-048 → S-1007 [SAFETY] (Gate-1 shadow ≥ 90 days) — ✅ DONE 2026-07-18. FIRST
      ENFORCEMENT AND FIRST TEST** — REQ-048 had existed since the PRD and was enforced
      nowhere: no code read it, no test covered it. `SHADOW_MIN_DAYS = 90` in
      `prescribe/gates.py`, commented with REQ-048 so tuning it is visibly *changing a
      requirement*; `gate1_status(..., shadow_days)` — **required, not defaulted** — opens
      only on `volume ∧ beats_baseline ∧ meets_shadow_period ∧ is_promoted`;
      `Gate1Status` reports `shadow_days` + `meets_shadow_period` for the S-1001 countdown.
      `data/repositories.py::shadow_days(session, *, now)` derives whole days from the
      **earliest** `prediction_log.created_at`; `prescribe/gates.py` stays **DB-free**.
      Tests `tests/safety/test_gates.py` + `tests/integration/test_shadow_clock.py` (17):
      ★ **the boundary** — 89 days with every other condition satisfied ⇒ **CLOSED**, 90 ⇒
      open; ★ **time is not evidence** — 500 shadow days with 149 meals / recall ≤ baseline /
      unpromoted all stay closed; ★ **`shadow_days` is required** (`TypeError` on omission),
      so a future default cannot restore the unenforced behaviour; 0/1/−7 days closed; no env
      var shortens it; ★ **no predictions ⇒ 0** (fails closed on day one); counted from the
      **earliest** row, not the latest (which would reset the clock every prediction) and not
      the row count (200 predictions in a week ≠ 200 days); insertion order is not chronology;
      ★ **a clock stepping backwards ⇒ 0, never negative**, and a future-dated row manufactures
      no elapsed time; ★ **not memoised** — the answer rises *and falls* with `now` in one
      session, and an earlier row inserted mid-session lengthens it immediately (ADR-7);
      ★ **`now` is keyword-only with no default**, asserted via the signature (ADR-8 — one
      sanctioned clock reader); ★ **no table may carry a `shadow*` column** — a stored
      `shadow_complete` would be set once and then lie forever;
      ★ `tests/safety/test_readout.py` — everything earned **except** the shadow period
      (day 89) still raises `GateNotPassed`: INV-2 does not grade the reason a gate is closed.
      Guards **seen to fire** before being reverted (clamp removed / `shadow_complete` column
      planted / default added). **Closes DL-034 gap G2.** Records: **DL-040**, and **DL-041** —
      which corrects this entry's original claim that S-1007 closed *the last* `03 §3`
      divergence. It did not: `03 §3` lists **five** Gate-1 conditions and
      `calibration acceptable (held-out)` is enforced nowhere, with **no threshold defined in
      any spec document**. Escalated as **OQ-9**; story **S-1012** written and **BLOCKED** —
      no number was invented to unblock it. Gate 1 is a conjunction, so the omission can only
      make it *more* permissive than the spec, and the four enforced conditions hold it shut
      today (nothing is promoted).
    - **OQ-9 / REQ-058 → S-1012 [SAFETY] (Gate-1 calibration condition) — ✅ DONE 2026-07-18.**
      **Closes the DL-041 divergence: Gate 1 now implements all five conditions `03 §3` lists.**
      The threshold was **escalated and answered, never invented** (OQ-9 → **DL-042**).
      `models/metrics.py::hypo_calibration` on `P(state ≤ 2)`: three risk bands, judged only at
      ≥ `HYPO_CALIB_MIN_BUCKET_N` (20) predictions, gap **≤ 0.10 understating / ≤ 0.20
      overstating**. `gate1_status(..., calibration_ok)` **required, not defaulted**;
      `gates.py` stays DB-free **and model-free** (it takes a `bool`, imports nothing new).
      Tests `tests/unit/test_calibration.py` + `tests/safety/test_gates.py` (18):
      ★ **the asymmetry** — two bands off by exactly 0.15, opposite verdicts (claimed 0.20 /
      happened 0.35 fails; claimed 0.50 / happened 0.35 passes); the gap asserted **signed**,
      so `abs()` cannot creep in unnoticed; boundaries exact both ways; ★ **19 is not evidence,
      20 is**; ★ **fails closed with an honest reason** — the reason string is asserted *not*
      to contain "acceptable"/"honest"/"good"/"fine"/"pass", because *cannot judge* is not
      *no problem*; a too-few band is still **reported** and decides nothing either way; one
      bad band fails the whole check; ★ **all five conditions required together** — each held
      false alone shuts the gate, **the test that would have caught DL-041**; `calibration_ok`
      required (`TypeError`); no env var flips it.
      Four guards **seen to fire** before revert: `abs(gap)`, "cannot judge" as a pass, the
      floor lowered 20→5, and the condition dropped from the conjunction.
      ⚠️ **One real defect caught by the SDET boundary test:** `0.30 − 0.20` is
      `0.10000000000000003`, so a bare `<=` failed DL-042 **at its own stated boundary** —
      the approved rule was unimplementable as written. Fixed with a documented
      `_FP_SLACK = 1e-9` (representation error only; the 0.101 case still fails).
    - **REQ-055 → S-1001a (operator shadow report card) — ✅ DONE 2026-07-18.**
      Discharges the S-805 deferred presentation note. `api/presenters.py` (pure view-model
      construction) + `GET /operator/shadow` + `operator_shadow.html`. **Badges are relative
      to the clinical baseline, never an invented absolute** (DL-042): `NOT_COMPARED` maps to
      an **empty label**, so a row with nothing to compare against shows no badge at all.
      Two sanctioned absolutes only: the calibration verdict (operator-approved) and Clarke
      **D/E**, dangerous by the measure's own construction.
      Tests `tests/unit/test_presenters.py` + `tests/integration/test_operator_shadow.py` +
      `tests/a11y/test_operator_shadow.py` (26 + 3):
      ★ **no baseline figure ⇒ no verdict and an empty label** — the row keeps its number and
      its meaning, and the absence is what is shown; a row never borrows a neighbour's
      comparison; ★ **direction asserted both ways** (recall higher-is-better, MAE
      lower-is-better) — one inverted comparison would flip a badge while the page rendered
      perfectly; comparison is **exact, no invented tolerance** (0.7100 vs 0.7099 is BETTER,
      not "about the same" — a looser notion of "beats the baseline" beside the gate's strict
      one would be the one the operator reads); ★ `β_insulin < 0` ⇒ ALARM **and the row is
      present when healthy**, so its absence cannot be read as clearance; ★ any Clarke **D/E**
      ⇒ ALARM regardless of baseline; ★ **"accuracy" in no field of any row**, and absent from
      the rendered page **and** the template source; ★ **`report=None` ⇒ no rows** (zeroed
      rows would read as "a model catching 0% of her lows" — a claim about a model that does
      not exist); ★ **renders with an empty database** (today's actual state, and the most
      likely thing to crash); ★ **all five Gate-1 conditions named**; ★ **Gate 2 appears
      nowhere** (retired, S-1011); no dose token in the template; axe clean; no horizontal
      overflow at 200% zoom; ★ checklist rows read met/unmet **in words**, not by icon and
      colour.
      Five guards **seen to fire** before revert — `NOT_COMPARED` labelled "Looks fine", a
      direction inverted, the empty-state early return removed, an "Overall accuracy" figure
      added, and the calibration row dropped to restore the pre-S-1012 four.
      `api.presenters` added to the **CI** coverage gate (self-corrected — the first commit
      message claimed it while it existed only on a local command line). Record: **DL-044**
      (the S-1001 split, plus two AC corrections: Gate 2 must not be shown, and the
      calibration *verdict* is a first-class row).
    - **REQ-058 → S-1001b [SAFETY] (the promotion control) — ✅ DONE 2026-07-18.**
      **Gate 1 now has a door.** `data/promotion.py` had existed since S-1006 with no
      reachable caller, so the gate could not open at all and manual promotion had never
      been exercised as a workflow — an unfinished feature that looked like safety.
      ★ **`Gate1Status.automatic_conditions_met`** — the four machine-checkable conditions,
      **excluding promotion**. `is_promoted` is itself one of the five, so `is_open` is false
      *by definition* at the moment of promotion; an endpoint gating on it refuses every
      promotion forever, and **a gate that can never open reads as caution, not as a bug**.
      `.failed_conditions` is one shared list so the 409 body and the screen cannot drift.
      `POST /api/operator/promote` **re-evaluates the gate from live data** (the UI disabling
      the button is a courtesy, not a control); **409** names *every* unmet condition; **400**
      without an explicit `confirmed`; **404** on an unknown version, creating nothing; audited
      via `data/promotion.py`. `POST /api/operator/revoke` has **no preconditions, ever**.
      Tests `tests/safety/test_promotion_api.py` (17) + `tests/integration/test_operator_shadow.py`:
      ★ **promotion succeeds when the four automatic conditions hold** (the test the story
      exists for — nothing else catches the `is_open` substitution); ★ Gate 1 actually reads
      OPEN afterwards; ★ each condition unmet **alone** ⇒ 409 naming itself (parametrised);
      ★ several unmet ⇒ **all** named; ★ **revoke works when the conditions no longer hold**;
      ★ **the client cannot assert its own readiness** — `preconditions_met`/`gate1_open`/
      `valid_meals=999` in the payload still gets 409, so the claim is provably *inert*;
      ★ **no `cli/` module calls `promote_model`** (AST) — the "refit then promote" cron job
      `07 §Retraining` forbids; confirmation required; both actions audited old→new; revoke
      effective on the next read (ADR-7); no env var or query param promotes.
      Four guards **seen to fire** before revert — `is_open` substituted (**7** fail, every
      one reading as "promotion refused"), preconditions added to revoke, the 409 truncated to
      the first condition, and a planted `_refit_and_ship()` in `cli/`.
      Records: **DL-044**. **Deferred:** whether a tripped kill switch blocks promotion
      (`03 §4` silent — inventing the rule would be unsanctioned tightening).
    - **REQ-040 / INV-2 → S-1002 [SAFETY] (patient readout UI) — ✅ DONE 2026-07-18.**
      Discharges the S-804 deferred presentation note — **the first patient-reachable model
      surface**. `GET /meals/{meal_id}/readout` + `readout.html`.
      ★ **Two branches, no third:** with Gate 1 closed the route renders an honest "nothing
      yet" state and **never constructs a readout**, so there is no object to accidentally
      render; catching `GateNotPassed` would put a rendering decision downstream of a safety
      exception. The gate is checked **twice** on the open path (route + the builder's first
      line, S-804) — the builder's is the one a future second caller cannot forget.
      **Pre-Gate-1 shows no number at all** — see **DL-045**, an escalated doc tension
      (`03 §3` "no output" vs the backlog AC's "baseline state") resolved conservatively.
      Tests `tests/safety/test_readout_ui.py` (14) + `tests/a11y/test_readout.py` (3):
      ★ closed ⇒ 200 and a plain state, **no risk claim and no baseline number**;
      ★ **`build_patient_readout` never called while closed** (monkeypatched to explode);
      ★ no bypass by query param, header or env var; ★ **no dose-like token in the template
      source or the rendered page** — S-804 made a dose impossible to *pass*, but nothing
      stops a template writing one into a sentence; ★ **never scolds** (`05b §8`) and
      ★ **never suggests testing less** (INV-5); hypo risk the headline in text; refusal
      rendered as words with "Test as usual" (`05b §5.3`); conflict shows **both**, no winner
      (`05b §5.4`); kill switch ⇒ baseline wording, still no dose; axe clean; no horizontal
      overflow at 200% zoom.
      Four guards **seen to fire** before revert — the route catching `GateNotPassed`, a dose
      in prose, a baseline projection pre-Gate-1, and a scolding line.
      ⚠️ **Three SDET defects recorded**, all "green for the wrong reason": 7 of 14 tests
      passed before the route existed (absence asserted against a 404 body); the post-Gate-1
      tests patched the readout but not the gate, so they graded the closed branch; and the
      a11y suite pointed at a nonexistent meal, so axe was grading FastAPI's error page.
    - **REQ-042/043, INV-3, INV-4, REQ-020 → S-1003 [SAFETY] (bolus calculator UI) —
      ✅ DONE 2026-07-18.** `recommend_bolus` had been tested since S-901 with nothing
      rendering it. **`api/bolus.py` is a separate router precisely so "no ML in the dose
      path" is checkable by inspection** — `api/app.py` imports `models.metrics`/`shadow`
      for the dashboard, so the property would be untestable if the dose routes lived there.
      Three states decided by **branching, never catching**: profile-incomplete (and it must
      **not read as a gate** — Gate 2 is retired), treat-the-low-first (checked *before*
      `recommend_bolus`, so no partially-computed dose is ever in scope), and the suggestion.
      `data/repositories.py::active_profile` (latest `effective_from`, tie-broken on
      `profile_id`). `at` is **reported**, not `now()` (ADR-8) — IOB is computed at the time
      she says she will inject.
      Tests `tests/safety/test_bolus_ui.py` (22) + `tests/a11y/test_bolus.py` (4):
      ★ **no IOB `<input>` exists** (every `<input>` parsed, not grepped) — IOB is
      *subtracted*, so an underestimate raises the dose, and unlike carbs or BG there is
      nothing to check it against; ★ **BG 79 refuses / 80 computes** — the INV-4 boundary on
      the screen, pinned to `BOLUS_BG_FLOOR` so the dose path cannot drift from the warning
      band (DL-043); ★ **`carbs_g=900` renders a VISIBLE flag**, asserted with `<code>`
      blocks stripped and as its own risk-cue element; ★ **five golden doses to 2 dp**,
      hand-verified before being committed as spec; ★ **`api/bolus.py` imports nothing from
      `models/`** (AST) and never catches a safety exception; ★ **no form carries the dose
      into a log** — `bolus_log` is the source of truth for IOB (`04 §2`), so a suggestion
      recorded as an injection corrupts every later calculation; axe clean; numeric keypad;
      no horizontal overflow at 200% zoom; the flag is not colour-only.
      ⚠️ **A real hole found by planting, in the guard that mattered most:** deleting the
      visible warning block left **all 21 tests passing**, because `recommend_bolus` embeds
      "…implausible, please re-check" inside its `arithmetic` string and the assertion was
      satisfied by the working — the line she is least likely to read. Fixed; the plant now
      fails twice. **This is the argument for planting violations rather than trusting a
      green suite.**
      ⚠️ **Recorded limitation:** the AST guard checks *direct* imports. `api/bolus.py` →
      `data.repositories` → `models.isf` (module-level, unrelated to dosing). No model output
      enters the dose path (`prescribe.bolus` + `features.iob`, both pure), but the transitive
      closure is not clean. Follow-up: split `data/repositories.py`.
      ⚠️ Also fixed a **real layout defect** measured from the DOM rather than guessed: the
      shared `.risk` flex child's `min-width: auto` pushed the page 2px sideways at 200% zoom.
    - **REQ-059 → S-1008 (live per-meal prediction wiring) — ✅ DONE 2026-07-18.**
      `prescribe/serving.py::serve_meal_prediction` — pure orchestration, no model logic:
      features → promoted model → guardrails → **persist (INV-9)** → serve. Baseline when no
      model is promoted. `data/repositories.py::get_promoted_artifact` is the **first code to
      read `is_promoted`** (unread since S-201) and **fails closed** — no promoted row ⇒ `None`
      ⇒ baseline.
      Tests `tests/integration/test_serving.py` (12): ★ **INV-9 — monkeypatch `serve_prediction`
      to raise ⇒ nothing served** (S-802's discipline re-asserted *through the wiring*, where a
      well-meaning `try/except` would downgrade a failed write to an unlogged prediction); the
      returned `prediction_id` resolves to a real row; ★ **no promoted model ⇒ `predict_proba`
      is never called** (spy asserts the *absence* of the call, so "baseline" holds because the
      model never ran, not because the output looked baseline-shaped); ★ **promoted ≠ most
      recent** — a newer unpromoted artifact is ignored, and an unpromoted one is ignored even
      when it is the only one; refusals persist as values (`guardrail_fired` set), not
      exceptions; INV-6 still raises through the chain.
      ★ **Prediction is not gated; display is.** `serve_meal_prediction` takes **no gate
      argument** and an AST guard asserts the module never calls `require_gate1` or
      `build_patient_readout` — **verified adversarially**: planting `require_gate1()` in the
      module makes the guard fail. Gating prediction would stop shadow mode accruing the
      evidence Gate 1 needs, and the deadlock would look like caution.
    - **REQ-060 → S-1009 (monthly refit cadence) — Backlog.** New unpromoted artifact per
      `07 §Retraining`.
    - **REQ-061 → S-1010 (patient-profile update surface) — ✅ Done 2026-07-29.** Append-only
      new profile version; updatable ICR/ISF/target read live. Refuses nonsense, flags the
      unusual, blocks neither (DL-048). ★ The refusal now lives in `data.profile` **as well
      as** `ProfileVersionCreate`: `target_bg <= 0` was refused only at the HTTP door, and
      every other caller — a CLI, a migration, a fixture — came in past it. A guard that
      depends on which door you used is not a guard.
    - **REQ-056 → S-1004 reclassified `[SAFETY]`** — forbidden-import guard moved into
      `tests/forbidden/`.
    - **REQ-041 / INV-1 → S-1011 [SAFETY] (retire Gate 2 / ICR gate) — PLANNED, not started
      (DL-035, 2026-07-18).** Operator-requested de-gating: ICR becomes a plain profile value
      with a `ValueError` present/>0 check (not a `SafetyViolation`). INV-1 to be marked
      **retired** (not renumbered). Invariant-table edits are deferred to S-1011 execution,
      which is gated on an explicit operator "go".
