# 04 — Data Model

*Purpose: entities, fields, validity rules.*
*Read before: `05-api-contract.md`, `07-clinical-model-spec.md`.*

Storage: **SQLite**, WAL mode. Migrations: **Alembic**. Timezone: **IST**, stored as UTC.

---

## ⚠️ The rule that governs this entire document

**`datetime` is what she reports. `logged_at` is the system clock. They are never the same field and one is never used for the other.**

She logs at the laptop, not at the table — often 30–40 minutes after eating. If any clinical timestamp is defaulted to `now()`, then `bolus_offset_min` and `elapsed_min` become fiction, the model is fit on times that never happened, and **there is no error, no warning, and no way to detect it afterwards.**

`datetime.now()` populating a clinical timestamp is a **forbidden pattern** with a grep test (S-105).

---

## 1. `patient_profile` — versioned, one active row

| Column | Type | Null | Notes |
|---|---|---|---|
| `profile_id` | int PK | No | |
| `effective_from` | date | No | **Version every change. Never overwrite.** (REQ-054) |
| `icr` | float | **Yes** | g carb per unit. Expected 7–10. **Null no longer blocks a gate** (Gate 2 retired, S-1011) — the calculator raises `ValueError` on null/`<= 0`. |
| `isf` | float | No | mg/dL per unit. Default 30. |
| `isf_source` | enum | No | `default` \| `endo` \| `derived` |
| `target_bg` | int | No | 135 |
| `bolus_brand` | text | No | `Fiasp` |
| `basal_brand` | text | No | `Tresiba` |
| `hypo_unaware` | bool | No | Default **true**. Drives alert asymmetry. |

## 2. `bolus_log` — source of truth for IOB

**Every injection. No exceptions.** IOB is derived from this table and nowhere else.

| Column | Type | Null | Notes |
|---|---|---|---|
| `bolus_id` | int PK | No | |
| `datetime` | datetime | No | **REPORTED.** When she injected. |
| `logged_at` | datetime | No | System clock. |
| `units` | float | No | > 0 |
| `bolus_type` | enum | No | `meal` \| `correction` \| `combined` |
| `meal_id` | int FK | Yes | Null for standalone corrections |
| `logged_by` | enum | No | `patient` \| `operator` |

## 3. `basal_log` — daily Tresiba

| Column | Type | Null | Notes |
|---|---|---|---|
| `date` | date PK | No | |
| `units` | float | No | |
| `time_taken` | time | No | **REPORTED.** |
| `logged_at` | datetime | No | |

> Tresiba has ~42 h duration and 3–4 day steady state. **Today's dose is not today's effect.** The model uses `effective_basal` (EWMA, halflife 25 h) — see `07` §3.

## 4. `meal_event` — the training record

| Column | Type | Null | Notes |
|---|---|---|---|
| `meal_id` | int PK | No | |
| `datetime` | datetime | No | **REPORTED — when she ATE.** |
| `logged_at` | datetime | No | **System clock. Never used for `datetime`.** |
| `logged_by` | enum | No | `patient` \| `operator` |
| `meal_type` | enum | No | `breakfast` \| `lunch` \| `dinner` \| `snack` |
| `pre_bg` | int | No | mg/dL |
| `pre_bg_time` | datetime | No | **REPORTED.** |
| `post_bg` | int | Yes | mg/dL |
| `post_bg_time` | datetime | Yes | **REPORTED.** |
| `elapsed_min` | int | Yes | **Computed from reported times.** Stored even when invalid. |
| `meal_bolus_units` | float | No | Carb coverage |
| `correction_bolus_units` | float | No | 0 if none. **Separate field** — needed to separate carb coverage from correction. |
| `bolus_offset_min` | int | No | **SIGNED. Negative = pre-bolus.** Cannot be skipped. |
| `carbs_g` | float | No | |
| `protein_g` | float | No | |
| `fat_g` | float | No | |
| `fiber_g` | float | No | |
| `net_carbs_g` | float | No | Computed: `max(0, carbs_g − fiber_g)` |
| `macro_confidence` | int | No | 0–100. Default 95; free-text dish → 60. Used as `sample_weight`. |
| `ex_intensity` | enum | No | `none` \| `light` \| `intense` |
| `ex_duration_min` | int | No | 0 if none |
| `ex_offset_min` | int | Yes | Minutes post-meal that exercise began |
| `pre_ex_intensity` | enum | No | Exercise in the **4 h before** the meal |
| `pre_ex_duration_min` | int | No | |
| `hypo_treatment` | bool | No | Rescue carbs taken in the window |
| `hypo_treatment_g` | float | Yes | |
| `snack_during_window` | bool | No | |
| `notes` | text | Yes | Free text: illness, stress, alcohol, sleep, injection site |
| `is_valid` | bool | No | Computed — §5 |
| `exclusion_reasons` | text | Yes | Computed. **All applicable reasons**, not just the first. |

## 5. Validity Rules

Computed at write time. See `03-state-model.md` §2.

| Rule | `exclusion_reason` |
|---|---|
| `post_bg` is null | `missing_outcome` |
| `elapsed_min` outside [105, 135] | `outside_window` |
| `hypo_treatment = true` | `rescued` |
| `snack_during_window = true` | `uncontrolled_intake` |
| Previous meal < 3 h prior | `iob_cob_contamination` |
| `macro_confidence < 50` | `low_confidence` |

### INV-7 **[SAFETY]**

```python
get_training_set()   # excludes ALL invalid rows
get_hypo_events()    # INCLUDES rescued rows, as State 1 or 2
```

A rescued meal appears in the second and not the first. **Both accessors must exist, and the hypo accessor must be tested against a dataset containing rescues.**

### Nothing is hard-deleted
Invalid records persist. `elapsed_min` is stored regardless. Adherence cannot be diagnosed from discarded data.

### Escape hatch (decide from data, not now)
The ±15 min window is a **choice, not a law**. If the adherence dashboard shows >30% of meals lost to `outside_window` by ~n=40, **widen to ±30 and add `elapsed_min` as a model feature** rather than discarding the record. With data scarcity as the binding constraint, modelling the elapsed time beats throwing the meal away.

## 6. `correction_event` — the highest-value data

Standalone corrections with **no food** in the window. The **only causally clean data the system collects** — nothing confounds it, which is what makes it the trustworthy source for ISF.

| Column | Type | Null | Notes |
|---|---|---|---|
| `event_id` | int PK | No | |
| `datetime` | datetime | No | **REPORTED.** |
| `logged_at` | datetime | No | |
| `bg_before` | int | No | |
| `bg_after` | int | No | Reading at **+4 h** |
| `bg_after_time` | datetime | No | **REPORTED.** |
| `units` | float | No | |
| `iob_at_start` | float | No | Computed. Valid only if < 0.5 |
| `food_in_window` | bool | No | If true → invalid for ISF derivation |

**Derived ISF** = mean of `(bg_before − bg_after) / units` over events with `iob_at_start < 0.5` **and** `food_in_window = false`. **Requires ≥ 5 valid events** to override the default (`07` §6).

## 7. `dish` — the adherence mechanism

She eats from a repertoire of 30–60 recurring dishes. This table is what makes a repeat meal a 4-tap operation instead of a 15-field form. **It is not a nice-to-have; it is the reason she keeps logging.**

| Column | Type | Null | Notes |
|---|---|---|---|
| `dish_id` | int PK | No | |
| `name` | text | No | |
| `portion_unit` | text | No | `katori` \| `roti` \| `cup` \| `piece` |
| `carbs_g` | float | No | Per one standard portion |
| `protein_g` | float | No | |
| `fat_g` | float | No | |
| `fiber_g` | float | No | |
| `source` | enum | No | `IFCT2017` \| `USDA` \| `label` \| `estimated` |
| `is_favourite` | bool | No | |
| `needs_review` | bool | No | Free-text entries queued for the operator |

Source: **IFCT 2017** (NIN Hyderabad) for Indian home cooking; USDA FoodData Central for packaged items.

## 8. `prediction_log` — INV-9 **[SAFETY]**

**Every prediction is written here BEFORE it is returned to any caller.** If the write fails, the prediction is not returned.

| Column | Type | Null | Notes |
|---|---|---|---|
| `prediction_id` | int PK | No | |
| `created_at` | datetime | No | System clock — correct here |
| `meal_id` | int FK | Yes | |
| `model_version` | text | No | **Required.** Without it, shadow-mode analysis is uninterpretable. |
| `gate_state` | text | No | Gate at time of prediction |
| `input_features` | json | No | Full feature vector |
| `predicted_distribution` | json | No | P(state) for all 5 |
| `baseline_state` | int | No | The clinical baseline's prediction |
| `guardrail_fired` | text | Yes | Which refusal condition, if any |
| `actual_state` | int | Yes | **Backfilled** when the reading arrives |

This is the **only real validation set** and the drift detector.

## 9. `model_artifact`

| Column | Type | Null | Notes |
|---|---|---|---|
| `version` | text PK | No | |
| `fit_date` | datetime | No | |
| `data_hash` | text | No | Hash of the training set |
| `n_rows` | int | No | |
| `feature_list` | json | No | |
| `metrics` | json | No | Hypo recall, Brier, calibration, Clarke |
| `is_promoted` | bool | No | **Manual promotion only** — see below |
| `kill_switch_tripped` | bool | No | **Manual re-arm only** |

### `is_promoted` is a **gate input**, not a label **[SAFETY]**

`gate1_status()` **reads this column**: Gate 1 opens only on
`volume ∧ beats_baseline ∧ calibration ∧ shadow_days ≥ 90 ∧ is_promoted` (REQ-058, S-1006).

> ✅ **All five are enforced** as of 2026-07-18: volume, beats-baseline, `calibration_ok`
> (S-1012 — the rule is OQ-9/DL-042, computed by `models/metrics.py::hypo_calibration`),
> `shadow_days` (S-1007), `is_promoted` (S-1006). Each is **required, not defaulted**, so a
> call site cannot omit a condition and still compile.

- Set **only** by the explicit operator promotion action (`POST /api/operator/promote`). No
  refit, scheduled job, or metric threshold may write it (`07 §Retraining`).
- **Fails closed:** absent, unknown, or unreadable ⇒ *not promoted*.
- A refit writes a **new row with `is_promoted = false`** (REQ-060). Promotion never inherits.

> ✅ **Wired 2026-07-18 (S-1006).** `gate1_status()` now reads it, and it is written **only**
> by `data/promotion.py::promote_model` / `revoke_promotion` — both audited, with the incumbent
> demoted in the same transaction so two promoted rows cannot exist. An AST test asserts no
> other production module writes the flag.

**The shadow clock** (`shadow_days`, REQ-048) is derived from `prediction_log` timestamps —
first logged shadow prediction to now. It is **never a stored boolean**, because a stored flag
can be set once and then lie forever.

> ✅ **Wired 2026-07-18 (S-1007, DL-040).** `data/repositories.py::shadow_days(session, *, now)`
> returns whole days from the **earliest** `prediction_log.created_at`; `gate1_status()` requires
> it. `now` is injected (ADR-8 — `core/clock.py` stays the one wall-clock reader) and the result
> is clamped at 0, so clock skew or a future-dated row reads as *not yet*. A test asserts **no
> table carries a `shadow*` column**, so the stored-flag shortcut is closed structurally.

## 10. `audit_log`

Every edit to a clinical record. She *will* mistype a BG; edits are permitted within 24 h and always audited.

| Column | Type | Null |
|---|---|---|
| `audit_id` | int PK | No |
| `table_name` | text | No |
| `record_id` | int | No |
| `field` | text | No |
| `old_value` | text | No |
| `new_value` | text | No |
| `changed_at` | datetime | No |
| `changed_by` | enum | No |
