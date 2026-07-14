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
| INV-6 | `inv6_predicted_bg_in_range` | `test_safety_invariants.py::test_inv6_*` | ✅ S-104 | ⏳ S-801 |
| INV-7 | `inv7_rescued_excluded_and_retained` | `test_safety_invariants.py::test_inv7_*`; **wiring:** `test_repositories.py` (regression guard + wiring-bites) | ✅ S-104 | ✅ **S-203** — `get_training_set()` calls it (S-305 adds capture) |
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
- **EPIC 1 (Foundation) — COMPLETE.** S-101, S-102, S-103, S-104, S-105 — Done,
  green, RED-first throughout.
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
  - Next: **S-204** dish table (REQ-009) — closes EPIC 2.
