# 01 — Product Requirements

*Purpose: problem, users, scope, success criteria, requirement register, open questions.*
*Read before: `02-functional-spec.md`.*

---

## 1. Problem

A 59-year-old woman with 30 years of Type 1 Diabetes manages her insulin by judgement and habit. Her son wants to give her two things:

1. **Foresight** — before she eats, an honest estimate of where her blood sugar will land in two hours, and in particular **whether she is at risk of going low.**
2. **Arithmetic** — a dose calculator that does the standard clinical maths reliably, including insulin-on-board, which is easy to forget and easy to get wrong.

### The fact that drives everything

**She has presumed impaired hypoglycaemia awareness.** After 30 years, the glucagon counter-regulatory response is typically gone and the adrenergic response blunted. She can be at 50 mg/dL and feel fine.

The system therefore exists **primarily to predict lows.** Not to optimise time-in-range, not to maximise accuracy — to catch hypos. Every design decision resolves in that direction.

### What makes this hard

- **Data is scarce.** ~3 meals/day. Gate 1 needs 150 valid meals ≈ 3 months. This is a small-n problem and must be modelled as one.
- **The data is confounded.** Bolus is *chosen in response to* carbs and pre-meal BG. Naively fitted, the model learns that insulin **raises** glucose. Inverting that into dosing advice is a hypo pathway. (See `07` §7.)
- **Inputs are noisy.** Self-reported carbs carry 20–50% error. Fingersticks carry ±15%. This caps achievable accuracy regardless of model choice.
- **The stakes are asymmetric.** A missed hyper is a bad afternoon. A missed hypo, in someone who cannot feel it, is not.

## 2. Users

| User | Role |
|---|---|
| **Patient** | 59F, T1D 30y. Logs meals, readings, boluses. Sees risk output **only after Gate 1**. May be logging while cognitively impaired by a low. |
| **Operator** | Her son. Builds and runs the system. Reviews shadow-mode output. Logs on her behalf. Sole audience for model output pre-Gate 1. |

## 3. Scope — v1

- Meal, bolus, basal, exercise, and correction-event logging on a laptop (localhost).
- Derived features: IOB (Fiasp curve), effective basal (Tresiba EWMA), exercise encoding.
- Clinical baseline model.
- Ordinal logistic risk model, gated.
- Validation harness: temporal CV, calibration, Clarke grid, hypo recall.
- Shadow-mode prediction log and operator dashboard.
- Bolus calculator — **gated on the endocrinologist, not on code.**
- Backup with a tested restore path.

## 4. Non-Goals

Explicitly not built. Do not build these.

| Non-goal | Reason |
|---|---|
| **CGM integration** | Deliberate scope decision. Fingersticks only. |
| **Reminders (Telegram/SMS/push)** | Deferred. Replaced by a "set a phone alarm for HH:MM" prompt. Written up and shelved; restore if adherence fails. |
| **VPS / TLS / auth / remote access** | v1 is localhost. Laptop FDE is the security boundary. |
| **PWA / offline queue** | Localhost — always online. `localStorage` draft-save retained. |
| **Automated basal titration** | Out of scope. Tresiba's 3–4 day lag makes it hazardous. |
| **Carb counting from photos** | Out of scope. |
| **Native mobile app** | Deferred. |
| **Anything reducing fingerstick frequency** | **INV-5. Never.** |
| **ML in the dose calculation** | The formula is causal; the ML is not. See `07` §7. |

## 5. Requirement Register

### Logging
| ID | Requirement | Priority |
|---|---|---|
| REQ-001 | A repeat meal is loggable in **≤4 taps + 2 numbers**. | P0 |
| REQ-002 | Pre-meal BG, meal macros, meal bolus, and correction bolus are captured per meal. | P0 |
| REQ-003 | `bolus_offset_min` is captured as a **signed** value (negative = pre-bolus) and cannot be skipped. | P0 |
| REQ-004 | Every clinical timestamp is **reported by the user**, never defaulted to `now()`. | P0 |
| REQ-005 | `logged_at` (system clock) is stored separately from `datetime` (reported). | P0 |
| REQ-006 | Every bolus — meal, correction, or standalone — is written to `bolus_log`. | P0 |
| REQ-007 | Daily Tresiba dose and time are logged. | P0 |
| REQ-008 | Exercise: intensity, duration, and offset within the window; plus pre-meal exercise. | P0 |
| REQ-009 | Macros auto-populate from a dish table; free-text entry lowers `macro_confidence`. | P0 |
| REQ-010 | Post-meal BG entry takes **<15 seconds**. | P0 |
| REQ-011 | Late and retrospective entry supported; the system asks for the real time, never assumes. | P0 |
| REQ-012 | Hypo rescue during the window is captured (flag + grams). | P0 |
| REQ-013 | Correction-only events (no food) are captured with a +4 h follow-up reading. | P0 |
| REQ-014 | After logging, the app displays the time to test (`meal time + 120 min`). | P1 |

### Data & Derivation
| ID | Requirement | Priority |
|---|---|---|
| REQ-020 | IOB derived from `bolus_log` using the Fiasp exponential curve (tp=55, td=240). Never entered. | P0 |
| REQ-021 | Effective basal = EWMA of daily Tresiba doses, halflife 25 h. | P0 |
| REQ-022 | Records are validated per `04-data-model.md` §5; `elapsed_min` stored even when invalid. | P0 |
| REQ-023 | **Hypo-rescued meals are excluded from outcome regression but retained as hypo events.** (INV-7) | P0 |
| REQ-024 | Exercise intensity is one-hot encoded with duration interactions. Never numeric 0/1/2. | P0 |

### Model
| ID | Requirement | Priority |
|---|---|---|
| REQ-030 | The clinical baseline model is implemented **first** and its score recorded as the bar to beat. | P0 |
| REQ-031 | The risk model is a **single** ordinal logistic regression with `pre_bg` continuous. | P1 |
| REQ-032 | `β_insulin` is sign-constrained ≥ 0 in every fit. (INV-8) | P0 |
| REQ-033 | ISF is derived from correction events once ≥5 clean ones exist. | P1 |
| REQ-034 | Validation uses forward-chaining temporal CV. Never a random split. | P0 |
| REQ-035 | Metrics: hypo recall @ fixed FAR (primary), Brier, calibration, Clarke grid, off-by-one. **Never plain accuracy.** | P0 |

### Safety
| ID | Requirement | Priority |
|---|---|---|
| REQ-040 | No patient-visible model output before Gate 1. (INV-2) | P0 |
| ~~REQ-041~~ | ~~Prescriptive module hard-disabled before Gate 2. (INV-1)~~ **RETIRED 2026-07-18 (S-1011, DL-035).** ICR is an ordinary versioned profile value; a missing/`<= 0` ICR raises `ValueError`. REQ-042/043 (INV-3/INV-4) still bind the dose path. | — |
| REQ-042 | Bolus never negative, never above 15 U; a cap event is **flagged**, not silently clipped. (INV-3) | P0 |
| REQ-043 | No bolus recommended below BG 80. (INV-4) | P0 |
| REQ-044 | Predicted BG outside [20, 600] raises a hard error. (INV-6) | P0 |
| REQ-045 | Every prediction is persisted **before** being returned. (INV-9) | P0 |
| REQ-046 | Output guardrails per `07` §9 (OOD, sparse region, diffuse posterior, baseline conflict). | P0 |
| REQ-047 | Kill switch on drift; **re-arming is manual only.** | P1 |
| REQ-048 | Shadow mode ≥ 90 days before patient-visible output. | P0 |
| REQ-049 | The system never recommends reducing fingerstick frequency. (INV-5) | P0 |

### Operations
| ID | Requirement | Priority |
|---|---|---|
| REQ-050 | Hourly consistent DB snapshot to a cloud-synced folder. `app.db` **never** inside that folder. | P0 |
| REQ-051 | **A restore drill is executed in month one**, before real data exists. | P0 |
| REQ-052 | Nightly CSV export. Her data must outlive the code. | P0 |
| REQ-053 | Operator adherence dashboard: valid-meal rate, exclusion reasons, `median(logged_at − datetime)`, days-since-last-log. | P0 |
| REQ-054 | Clinical constants are **versioned**, never overwritten. | P0 |

### Integration, UI & validation (EPIC 10)
| ID | Requirement | Priority |
|---|---|---|
| REQ-055 | The operator shadow report is **rendered** (hypo recall @ FAR headline, Brier, calibration, Clarke grid, predictions-vs-actuals, `β_insulin < 0` alarm, live gate status). Operator-only; **never plain accuracy**; no dose on the screen. | P1 |
| REQ-056 | A **seeded** synthetic-data generator produces a full logging cycle for tests/demos, honouring reported-timestamp discipline (ADR-8). **Never used on, imported by, or presented as, real patient data.** | P1 |
| REQ-057 | An **end-to-end test** exercises the full pipeline on synthetic data and asserts the safety invariants (INV-2/7/9) and gate behaviour hold **across** the chain, not just in unit isolation. | P1 |
| REQ-058 | Gate 1 opens **only on an explicit, audited manual promotion** (`is_promoted`); metrics alone never open it. Conforms `07 §Retraining` ("Promotion is manual, on hypo recall"). *(Added 2026-07-18, DL-034.)* | P0 |
| REQ-059 | On each logged meal the live prediction path runs features → model → guardrails → **persist (INV-9) → serve**, using the currently-promoted model (baseline if none promoted). *(Added 2026-07-18, DL-034.)* | P0 |
| REQ-060 | Monthly refit over a trailing 6-month window, older data down-weighted, writing a **new unpromoted** model artifact. Conforms `07 §Retraining`. *(Added 2026-07-18, DL-034.)* | P1 |
| REQ-061 | An operator action appends a **new** `patient_profile` version (updatable ICR/ISF/target); prior versions retained; the calculator reads the latest live. *(Added 2026-07-18, DL-034.)* | P1 |

*REQ-048 (shadow mode ≥ 90 days before patient-visible output) gained its first covering story
and its first enforcement in **S-1007, done 2026-07-18** (DL-040) — it was previously enforced
nowhere. Rendering of the patient readout (INV-2,
REQ-040) and the bolus calculator (INV-3/4, REQ-042–043) is covered by those existing
requirements; EPIC 10 adds their render layer without relaxing any runtime gate.*

## 6. Success Criteria

| # | Criterion |
|---|---|
| SC-1 | **150 valid meals logged.** Everything else is downstream of this. If adherence fails, the project fails. |
| SC-2 | The ordinal model beats the clinical baseline **on hypo recall** on a held-out temporal fold. If it doesn't, that is a real finding — carbs and insulin explain nearly everything — and the baseline ships alone. |
| SC-3 | Calibration is acceptable on prospective (not retrospective) data. |
| SC-4 | The restore drill has been executed and logged. |
| SC-5 | The endocrinologist has confirmed ICR, ISF, and the state boundaries. |

## 7. Explicit Trade-offs Accepted

| Trade-off | Cost | Why accepted |
|---|---|---|
| No CGM | Lose pre-meal trend (a strong predictor), the 3–5 h insulin tail, ~288 readings/day | Patient/operator decision. Note: the original rationale (sensor lag) does not hold at a 2 h horizon — the real constraint is cost/availability. |
| 2-hour endpoint | A perfect 2 h reading can be followed by a hypo at 3.5 h. High-fat meals peak at 4–6 h, outside the window entirely. | Accepted. **The model does not predict late lows and must not be trusted to.** |
| Raw bolus, not residual | Confounding-by-indication remains in the features | Mitigated by INV-8 and by keeping ML out of dosing entirely. Residual is a future enhancement. |
| Discrete output states | 80–180 "target" is a 100-point band; the boundary at 180 is within meter noise | Accepted. `pre_bg` remains continuous as an **input**, which recovers most of the loss. |
| Laptop-only | She cannot log away from home. Restaurant meals — the high-carb, hard-to-estimate ones — are lost or recalled. | Accepted for v1. Known bias in the training distribution. |

## 8. Constraints

- Single patient. **No design choice may be justified by "what if we scale."**
- Python is forced (statsmodels/PyMC).
- Data cannot be re-collected. Loss is permanent.
- The system must remain comprehensible to the operator in two years, when he has forgotten how it works and she still depends on it.

## 9. Open Questions — Clinical Decisions

**BA owns this list. Gate 1 depends on it.**

> **Retitled 2026-07-18 (DL-042).** Was *"Open Questions — Endocrinologist"*. Standing operator
> direction: *"don't depend on an endocrinologist for anything."* These are still **clinical
> decisions that Dev and SDET never make** (CLAUDE.md) — only the escalation path changed: they
> go to **the operator**, who decides. The BA's obligation is correspondingly higher: put a
> concrete, plainly-worded proposal in front of the operator rather than parking the question
> behind someone who may never answer it. OQ-1/2/6 were already closed this way (DL-032).

| # | Question | Blocks |
|---|---|---|
| OQ-1 | **Confirm ICR.** Expected 7–10 g/U (500/60 ≈ 8.3). | ~~**Gate 2**~~ **RESOLVED 2026-07-17: ICR = 9 g/U** (endocrinologist-confirmed; DL-032). Opens Gate 2. |
| OQ-2 | **Confirm ISF = 30.** Consistent with 1800/60, but a population heuristic. **An ISF too low causes over-dosing.** | ~~**Gate 2**~~ **RESOLVED 2026-07-17: ISF = 30 mg/dL/U** (endocrinologist-confirmed; DL-032). Opens Gate 2. |
| OQ-3 | **Basal:bolus split.** Tresiba should be ~40–50% of TDD (24–30 U). If materially higher, she may be **over-basalized** — which causes unexplained lows in someone who cannot feel them. **Check before collecting data.** | Data quality |
| OQ-4 | Does she have **confirmed** impaired hypoglycaemia awareness? The spec assumes yes. | Alert tuning |
| OQ-5 | Confirm State 2 upper boundary at **80** mg/dL (raised from the standard 70). | **RESOLVED 2026-07-18 by the operator (DL-043): the line stays at 80.** Anything below 80 is a low. Buys ~10 mg/dL of warning time for someone who cannot feel one coming, and matches the existing `BOLUS_BG_FLOOR = 80` (INV-4) so one number means one thing. Accepted cost: more false alarms in the 70–79 band, and hypo-recall figures are not directly comparable to published literature anchored at 70. No code change — `STATE_BOUNDARIES` was already `(54, 80, 181, 251)`; the *caveat* is what closed. |
| OQ-6 | Confirm the 120–150 correction target is intentional for her age and duration. | **CONFIRMED 2026-07-17: target = 135 mg/dL still valid** (DL-032). |
| OQ-7 | Is she aware of and does she approve of this system? | Everything |
| **★ OQ-9** | **What makes held-out calibration "acceptable"?** — **RESOLVED 2026-07-18 by the operator (DL-042).** Was: `03 §3` / `04 §9` list it as a Gate-1 condition with no threshold defined anywhere, so it was enforced nowhere (DL-041). **Answer: a deliberately coarse, asymmetric rule on the hypo probability** — 3 buckets (<20% / 20–50% / >50%), a bucket counts only at **≥ 20 predictions**, and the gap between claimed and observed rate must be **≤ 10 points when it UNDERSTATES risk** and **≤ 20 points when it overstates**. No qualifying bucket ⇒ **not acceptable** (fails closed). | **UNBLOCKS Gate 1's fifth condition.** Story **S-1012** is unblocked. |
| **★ OQ-8** | **REVISIT — the Markov question (operator-flagged, 2026-07-18).** The project began as a Markov-chain design (DL-038) and was built as a pooled ordinal regression instead. **Revisit once ≥150 real meals exist**, when the small-n argument that drove the six deviations can be tested rather than assumed. Specifically: (a) is there now enough data per pre-meal state to make a transition-matrix view informative *as a diagnostic*, alongside — never replacing — the pooled model? (b) does binning `pre_bg` measurably lose anything, measured on real data? (c) does the name still fit? **Not blocking; do not act on this before the data exists.** | Post-Gate-1 review |
