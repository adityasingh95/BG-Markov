# Traceability Matrix

*Owner: BA. REQ-nnn → story → test → status. Any REQ without a covering test is
a visible gap. INV-n coverage is tracked in the second table.*

## REQ → story → test

| REQ | Story | Test(s) | Status |
|-----|-------|---------|--------|
| _(none — infra)_ | S-101 | `tests/unit/test_toolchain.py`, `tests/unit/test_version.py` | ✅ Done |
| **`05b §2`** (Accessibility NFR; no `REQ-nnn`) | S-102 | `tests/a11y/test_base_layout.py` (axe, inputmode, 18px, 48px, no-dish-`select`, 200 %-zoom reflow, colour-not-sole-signal) | ✅ Done |
| _(config infra; feeds REQ-041/042/054)_ | S-103 | `tests/unit/test_config.py`, `tests/safety/test_config_frozen.py` | ✅ Done |
| _(safety module; INV-1..9)_ | S-104 | `tests/safety/test_safety_invariants.py`, `tests/safety/test_safety_module_hygiene.py` | ✅ Done |
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
| **REQ-006** (every bolus → `bolus_log`) | S-201 | `test_bolus_log_roundtrips` | ✅ Schema done |
| **REQ-007** (daily Tresiba → `basal_log`) | S-201 | `test_all_tables_present…` (basal_log) | ✅ Schema done (form: S-302/EPIC 3) |
| **REQ-054** (constants versioned, never overwritten) | S-201 | `test_patient_profile_change_creates_a_new_row`, `test_patient_profile_is_immutable_in_place` | ✅ Done |

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
| INV-1 | `inv1_prescriptive_requires_gate2` | `test_safety_invariants.py::test_inv1_*`; precondition also guarded in `test_config_frozen.py` | ✅ S-104 | ⏳ S-703 / S-901 |
| INV-2 | `inv2_patient_output_requires_gate1` | `test_safety_invariants.py::test_inv2_*` | ✅ S-104 | ⏳ S-703 / S-804 |
| INV-3 | `inv3_bolus_within_bounds` | `test_safety_invariants.py::test_inv3_*` | ✅ S-104 | ⏳ S-901 |
| INV-4 | `inv4_bolus_allowed_at_bg` | `test_safety_invariants.py::test_inv4_*` | ✅ S-104 | ⏳ S-901 |
| INV-5 | `inv5_monitoring_not_reduced` | `test_safety_invariants.py::test_inv5_*` | ✅ S-104 | ⏳ output/advice stories |
| INV-6 | `inv6_predicted_bg_in_range` | `test_safety_invariants.py::test_inv6_*`; **wiring:** `test_baseline.py` (out-of-range prediction raises) | ✅ S-104 | ✅ **S-501** — enforced on the baseline's predicted BG (first prediction path); re-checked at the patient readout (S-8xx) |
| INV-7 | `inv7_rescued_excluded_and_retained` | `test_safety_invariants.py::test_inv7_*`; **wiring:** `test_repositories.py` (regression guard + wiring-bites); **ledger reconciliation:** `test_hypo_rescue.py` (row-deletion + flag-clear ⇒ raise) | ✅ S-104 | ✅ **S-203** wired + **S-305** independent ledger closes the DB-row-deletion gap (DL-019/H4) |
| INV-8 | `inv8_beta_insulin_non_negative` | `test_safety_invariants.py::test_inv8_*` | ✅ S-104 | ⏳ S-503 / S-603 |
| INV-9 | `inv9_prediction_persisted` | `test_safety_invariants.py::test_inv9_*` | ✅ S-104 | ⏳ S-802 |
| _module hygiene_ | no-`assert` (AST), zero internal imports (ADR-6), single-definition, `-O` still raises | `test_safety_module_hygiene.py` | ✅ S-104 | — |

S-101 introduces no invariant logic. It provides the ruff/mypy/pytest/coverage
gates that S-104 and S-105 rely on to be enforceable at all.

**S-103 note on INV-1:** the config's `prescriptive_enabled` is a *computed
precondition* (`icr is not None`), **not** the invariant. It can only force the
prescriptive path OFF, never ON, and cannot be assigned or injected (adversarial
tests prove this). INV-1 itself — "prescriptive disabled until Gate 2 passes",
evaluated from live data per ADR-7 — is implemented in `core/safety.py` (S-104)
and enforced at the gate (S-703). The config does **not** re-implement it.

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
    in the mypy + coverage gates. Next: S-502 [SAFETY] (ISF from correction events;
    consumes the S-306b `iob_at_start`; ≥5 clean events, never silently swaps,
    ISF ≤ 0 raises), S-503 [SAFETY] (★ constrained OLS — INV-8, the
    confounding-by-indication test). Then EPIC 6 (the ordinal model).
  - Post-ship, in parallel with data collection: **EPIC 4** (S-401 IOB engine —
    backfills `iob_at_start`; features), **EPIC 5** (S-501 ISF derivation from the
    correction events; the ordinal model), gated on live data — INV-1/INV-2 hold.
