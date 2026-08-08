# 05 — API Contract

*Purpose: endpoints, payloads, errors.*
*Read before: implementing `api/`.*

FastAPI. Server-rendered Jinja + HTMX for UI routes; JSON for data routes. Bound to `127.0.0.1`. **No auth in v1** — laptop FDE is the security boundary (ADR-9).

---

## 0. Conventions

- All write endpoints are **idempotent** — the client generates a UUID per record.
- **Every clinical timestamp is supplied by the client as a reported value.** The server **never** substitutes `now()` for `datetime`, `pre_bg_time`, `post_bg_time`, or a bolus time. It stamps `logged_at` itself.
- Errors: `{ "error": "...", "code": "...", "detail": {...} }`

### Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `GATE_NOT_PASSED` | 403 | Feature blocked by Gate 1 or 2. **Not bypassable.** |
| `SAFETY_VIOLATION` | 422 | An INV-n was violated |
| `GUARDRAIL_REFUSED` | 200 | **A refusal is a valid outcome**, not an error. Body carries the reason. |
| `VALIDATION_ERROR` | 422 | Schema/field validation |
| `BG_TOO_LOW_FOR_BOLUS` | 422 | INV-4 — treat the low first |
| `IMPLAUSIBLE_INPUT` | 422 | INV-3/6 — capped and flagged |

---

## 1. Meals

### `POST /api/meals`
Log a meal (pre-meal).

```json
{
  "idempotency_key": "uuid",
  "datetime": "2026-07-13T08:00:00+05:30",
  "meal_type": "breakfast",
  "pre_bg": 142,
  "pre_bg_time": "2026-07-13T07:55:00+05:30",
  "dish_selections": [{"dish_id": 12, "portions": 2}],
  "carbs_g": 48.0, "protein_g": 14.0, "fat_g": 9.0, "fiber_g": 6.0,
  "macro_confidence": 95,
  "meal_bolus_units": 6.0,
  "correction_bolus_units": 0.5,
  "bolus_offset_min": -10,
  "ex_intensity": "none", "ex_duration_min": 0,
  "pre_ex_intensity": "none", "pre_ex_duration_min": 0,
  "notes": null,
  "logged_by": "patient"
}
```

**Server:** stamps `logged_at`; computes `net_carbs_g`; writes a `bolus_log` row per bolus component.
**Never** substitutes `now()` for `datetime` or `pre_bg_time`.

**200:**
```json
{ "meal_id": 481, "test_at": "2026-07-13T10:00:00+05:30",
  "message": "Logged. Set a phone alarm for 10:00 AM to test." }
```
`test_at` = **reported `datetime` + 120 min**. Never `logged_at + 120`.

**422** if `bolus_offset_min` is absent (REQ-003 — it cannot be skipped).

### `PATCH /api/meals/{id}/post-bg`

```json
{ "post_bg": 168,
  "post_bg_time": "2026-07-13T10:05:00+05:30",
  "hypo_treatment": false,
  "hypo_treatment_g": null,
  "snack_during_window": false,
  "ex_intensity": "light", "ex_duration_min": 20, "ex_offset_min": 40 }
```

**`post_bg_time` is required and reported.** The server does not default it.
Computes `elapsed_min` from **reported** times; computes validity; **stores the record regardless**.

**200:**
```json
{ "meal_id": 481, "elapsed_min": 125, "is_valid": true, "exclusion_reasons": [] }
```

### `GET /api/meals` · `GET /api/meals/{id}` · `PATCH /api/meals/{id}`
List (filterable by validity), fetch, edit (within 24 h, audit-logged).

---

## 2. Boluses & Basal

### `POST /api/boluses`
Standalone bolus (typically a correction). `datetime` reported.
If `bolus_type = "correction"` and `meal_id` is null, the response prompts for a correction-event follow-up.

```json
{ "bolus_id": 903, "prompt_correction_event": true,
  "message": "Not eating in the next 4 hours? Log a follow-up BG at 2:15 PM." }
```

### `POST /api/basal` · `GET /api/basal/effective?at=<ts>`
Daily Tresiba dose. Effective basal returns the EWMA value plus `titration_lockout` (true for 3 days after any change).

---

## 3. Correction Events

### `POST /api/correction-events`
### `PATCH /api/correction-events/{id}/followup`

```json
{ "bg_after": 148, "bg_after_time": "2026-07-13T14:20:00+05:30", "food_in_window": false }
```

**200:**
```json
{ "event_id": 44, "is_valid_for_isf": true, "implied_isf": 34.0,
  "clean_events_count": 3, "events_needed_for_gate2": 5 }
```

`implied_isf` is **reported, not applied.** ISF only changes once ≥5 clean events exist (`07` §6), and the change is surfaced to the operator, never silent.

---

## 4. Prediction

### `POST /api/predict` **[SAFETY]**

~~**INV-2:** below Gate 1 → `403 GATE_NOT_PASSED` for the patient.~~ **RETIRED** (`00a §3.1`) — no patient surface. Output is always returned to the researcher, **labelled with its gate state and model version** so a preliminary result is never mistaken for a Gate 1 one.
**INV-9:** the prediction is written to `prediction_log` **before** the response is sent. If the write fails, **no response is returned.** **Unchanged** — an incomplete log cannot be analysed afterwards, and the log is the only real validation set.

**200 — normal:**
```json
{
  "distribution": {"1": 0.01, "2": 0.13, "3": 0.71, "4": 0.13, "5": 0.02},
  "hypo_risk": 0.14,
  "headline": "About a 1 in 7 chance of going low.",
  "baseline_state": 3,
  "model_state": 3,
  "conflict": false,
  "model_version": "v3-2026-07-01",
  "prediction_id": 1188
}
```

**200 — guardrail refusal (`07` §9). A refusal is a valid outcome:**
```json
{ "refused": true, "reason": "diffuse_posterior",
  "message": "Not confident enough to predict this one.",
  "baseline_state": 3, "prediction_id": 1189 }
```

**200 — baseline conflict.** Both are returned. **The system does not pick a winner.**
```json
{ "conflict": true, "baseline_state": 3, "model_state": 5,
  "message": "The two methods disagree. Showing both." }
```

---

## 5. Prescriptive **[SAFETY]**

### `POST /api/bolus-recommendation`

~~**INV-1:** `icr is None` → `403 GATE_NOT_PASSED`.~~ **RETIRED** (`00a §3.1`) — ICR is a declared parameter (8.3), so the endpoint is reachable.

**The response is a number in a study, not a dose.** It carries the
non-clinical-use banner (REQ-058). **INV-3 and INV-4 below are unchanged** — they
are the behaviour under test (H-4), and an out-of-range output is how the
arithmetic announces it is wrong.

```json
{ "carbs_g": 60, "current_bg": 190 }
```

**200:**
```json
{
  "suggested_units": 7.9,
  "breakdown": { "carb_dose": 7.2, "correction": 1.8, "iob_deduction": -1.1 },
  "arithmetic": "60 ÷ 8.3 = 7.2 U | (190 − 135) ÷ 30 = 1.8 U | IOB − 1.1 U",
  "capped": false,
  "disclaimer": "A suggestion for your review — not an instruction. Always check it yourself."
}
```

- **`422 BG_TOO_LOW_FOR_BOLUS`** if `current_bg < 80` (INV-4).
- **`capped: true` + `IMPLAUSIBLE_INPUT`** if the raw dose exceeds 15 U (INV-3) — **flagged, never silently clipped.**
- Never negative.
- **No ML anywhere in this path.**

---

## 6. Operator

| Endpoint | Purpose |
|---|---|
| `GET /api/operator/gates` | Gate status; what blocks each; valid-meal count |
| `GET /api/operator/adherence` | Valid rate, exclusions by reason, **`median(logged_at − datetime)`**, days-since-last-log |
| `GET /api/operator/shadow` | Predictions vs actuals, calibration, hypo recall, Clarke grid |
| `GET /api/operator/warnings` | Unconstrained `β_insulin < 0` warnings, drift, backup failures |
| `POST /api/operator/profile` | New **versioned** profile row. Never an update. |
| `POST /api/operator/kill-switch/rearm` | **Manual only.** Never automatic. |

## 7. Dishes

`GET /api/dishes/search?q=` · `GET /api/dishes/favourites` · `POST /api/dishes` · `GET /api/dishes/needs-review`

## 8. CLI (not HTTP)

```
python -m cli refit          # monthly. Candidate model; promotion is manual.
python -m cli drift-check    # weekly. May trip the kill switch.
python -m cli export         # full CSV. Her data must outlive the code.
python -m cli backup         # hourly (cron)
python -m cli restore-drill  # ★ RUN IN MONTH ONE, before there is data to lose
python -m cli derive-isf     # ISF from correction events
python -m cli baseline       # score the clinical baseline — the bar to beat
```
