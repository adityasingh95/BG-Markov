# 01 — Product Requirements

*Purpose: problem, users, scope, success criteria, requirement register, open questions.*
*Read before: `02-functional-spec.md`.*

---

## 1. Problem

> **Research build.** See `00a-research-mode.md`. There is no patient. Nothing
> here is used to predict for, prescribe to, or inform the care of any person.

### The question under test

**Can a 2-hour post-meal glucose model be made trustworthy on small,
confounded, single-subject data — and are the guardrails in `07` the right ones?**

Broken into testable claims:

| # | Claim |
|---|---|
| H-1 | An ordinal model on ~150 observations can beat the clinical baseline **on hypo recall**, or it cannot — and either answer is a result. |
| H-2 | Confounding by indication will make a naive fit conclude that insulin *raises* glucose, and **the INV-8 sign constraint recovers the correct sign.** |
| H-3 | ISF derived from unconfounded correction events (`07 §6`) **recovers the generator's true ISF** more closely than the OLS estimate does. |
| H-4 | The guardrail suite (`07 §10`) refuses on the cases it should refuse on, and does not refuse on the cases it should answer. |
| H-5 | Forward-chaining CV and the leakage suite **detect** a deliberately introduced leak, rather than producing a flattering score. |

### The modelled subject

The simulated subject has **impaired hypoglycaemia awareness** — the glucagon
counter-regulatory response gone, adrenergic response blunted, capable of being
at 50 mg/dL and feeling fine.

This is retained because it sets the **objective function**: a missed low costs
far more than a missed high. The system is therefore evaluated **primarily on
lows.** Not time-in-range, not plain accuracy — hypo recall. Every design
decision resolves in that direction, and that has not changed.

### What makes this hard

- **Data is scarce.** ~150 meals is the working sample size — the amount a real subject would produce in about three months. **The generator could emit a million rows; it must not.** The scarcity is the experimental condition, not an accident, and a result obtained at n=10,000 answers a question nobody asked.
- **The data is confounded.** Bolus is *chosen in response to* carbs and pre-meal BG. Naively fitted, the model learns that insulin **raises** glucose. Inverting that into dosing advice is a hypo pathway. (See `07` §7.)
- **Inputs are noisy.** Self-reported carbs carry 20–50% error. Fingersticks carry ±15%. This caps achievable accuracy regardless of model choice.
- **The stakes are asymmetric.** A missed hyper is a bad afternoon. A missed hypo, in someone who cannot feel it, is not.

## 2. Users

| User | Role |
|---|---|
| **Researcher** | The only user. Builds and runs the system, configures the generator, reviews model output and metrics. Sole audience for everything. |
| **Simulated subject** | Not a user. A parameterisation of the generator (`00a §5`) — 59F, T1D 30y, TDD 60 U, hypo-unaware. Produces meals, readings and boluses. Consumes nothing. |

The patient-facing surface described in `05b-ui-ux-spec.md` is **not built** in
this build (EPIC 3b, deprioritised — see `10-backlog.md`). Its accessibility and
language requirements are retained as specification: they describe what would
have to be true before any such surface existed, and they are the reference for
`00a §6`'s copy rules.

## 3. Scope — v1

- **Synthetic subject generator** with declared ground truth, confounded dosing, and a known hypo rate (`00a §5`). Isolated from everything below (REQ-055).
- Storage for meals, boluses, basal, exercise and correction events; validity engine.
- Derived features: IOB (Fiasp curve), effective basal (Tresiba EWMA), exercise encoding.
- Clinical baseline model — the bar.
- Constrained parameter estimation (ICR/ISF), and ISF from correction events.
- Ordinal logistic risk model.
- Validation harness: forward-chaining temporal CV, leakage suite, calibration, Clarke grid, hypo recall.
- Prediction log, output guardrails, kill switch, researcher dashboard.
- Bolus calculator — **unblocked; its output is a number in a study, not a dose.**
- Backup with a tested restore path.
- **Results write-up** answering H-1..H-5 (EPIC 10).

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
| **Anything reducing fingerstick frequency** | Copy rule, `00a §6`. Costs nothing; it stays. |
| **ML in the dose calculation** | The formula is causal; the ML is not. See `07` §7. **ADR-10 is unchanged** — the causal/predictive split is part of what is under test. |
| **Any real patient data** | Nothing here is built to hold it. Synthetic only (`00a §5`). |
| **A patient-facing surface** | EPIC 3b, deprioritised. There is no patient. |

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

### Safety & validity

Retired requirements keep their IDs so cross-references resolve. See `00a §3`.

| ID | Requirement | Priority |
|---|---|---|
| ~~REQ-040~~ | ~~No patient-visible model output before Gate 1. (INV-2)~~ | **RETIRED** — no patient surface. |
| ~~REQ-041~~ | ~~Prescriptive module hard-disabled before Gate 2. (INV-1)~~ | **RETIRED** — ICR is declared (`00a §4`). |
| REQ-042 | Bolus never negative, never above 15 U; a cap event is **flagged**, not silently clipped. (INV-3) | P0 |
| REQ-043 | No bolus recommended below BG 80. (INV-4) | P0 |
| REQ-044 | Predicted BG outside [20, 600] raises a hard error. (INV-6) | P0 |
| REQ-045 | Every prediction is persisted **before** being returned. (INV-9) | P0 |
| REQ-046 | Output guardrails per `07` §10 (OOD, sparse region, diffuse posterior, baseline conflict, absurd value). | P0 |
| REQ-047 | Kill switch on drift; **re-arming is manual only.** | P1 |
| ~~REQ-048~~ | ~~Shadow mode ≥ 90 days before patient-visible output.~~ | **RETIRED** — replaced by REQ-057. |
| ~~REQ-049~~ | ~~Never recommends reducing fingerstick frequency. (INV-5)~~ | **RETIRED** as an invariant; retained as a copy rule (`00a §6`). |
| REQ-055 | **The generator is not importable from `core/`, `features/`, `models/` or `prescribe/`**, and its ground-truth parameters are never readable by the model. Enforced by test. | P0 |
| REQ-056 | **Parameter recovery is reported**: derived ISF/ICR against the generator's true values, with error bars. | P0 |
| REQ-057 | **Held-out temporal evaluation** replaces the 90-day shadow clock. No calendar requirement; the scientific content is retained. | P0 |
| REQ-058 | **Every surface rendering a number carries the non-clinical-use banner** (`00a §6`). | P0 |

### Operations
| ID | Requirement | Priority |
|---|---|---|
| REQ-050 | Hourly consistent DB snapshot to a cloud-synced folder. `app.db` **never** inside that folder. | P0 |
| REQ-051 | **A restore drill is executed early**, before there are results to lose. Cheap, and a lost run is a re-run you did not budget for. | P0 |
| REQ-052 | Nightly CSV export. The data and results must outlive the code. | P0 |
| REQ-053 | Researcher dashboard: valid-meal rate, exclusion reasons, `median(logged_at − datetime)`, days-since-last-log. **In synthetic data the lag metric checks the generator**, not adherence — a generator that emits `logged_at == datetime` is not exercising ADR-8. | P0 |
| REQ-054 | Clinical constants are **versioned**, never overwritten. | P0 |

## 6. Success Criteria

**A criterion is met when it produces a defensible answer — not when the answer
is favourable.** H-1 resolving against the model is a success.

| # | Criterion | Tests |
|---|---|---|
| SC-1 | **A generator producing ~150 valid meals with declared ground truth**, including lows at a known rate and dosing behaviour that is confounded by design. | H-2, H-3 |
| SC-2 | The ordinal model is scored against the clinical baseline **on hypo recall**, on a held-out temporal fold. Beating it is one result; failing to is an equally reportable one — carbs and insulin may explain nearly everything. | H-1 |
| SC-3 | Calibration reported on held-out folds, with the reliability diagram shown, not summarised away. | H-1 |
| SC-4 | **Parameter recovery measured**: derived ISF and ICR compared against the generator's true values, with error bars. | H-3 |
| SC-5 | **The leakage suite is shown to bite** — a deliberately introduced leak is caught by the temporal-CV and day-boundary tests rather than producing a flattering score. | H-5 |
| SC-6 | The guardrail suite is exercised against each of its five refusal conditions. | H-4 |
| SC-7 | The restore drill has been executed and logged. Still cheap, still the difference between having results and not. | — |

## 7. Explicit Trade-offs Accepted

| Trade-off | Cost | Why accepted |
|---|---|---|
| No CGM | Lose pre-meal trend (a strong predictor), the 3–5 h insulin tail, ~288 readings/day | Retained as a **constraint of the experiment**: the question is whether the method works on fingerstick-only data. Giving the generator CGM-density data would answer a different question. |
| 2-hour endpoint | A perfect 2 h reading can be followed by a hypo at 3.5 h. High-fat meals peak at 4–6 h, outside the window entirely. | Accepted. **The model does not predict late lows**, and no result may be stated as though it does. |
| Raw bolus, not residual | Confounding-by-indication remains in the features | **Deliberate — this is H-2.** Removing the confounding would remove the thing being tested. |
| Discrete output states | 80–180 "target" is a 100-point band; the boundary at 180 is within meter noise | Accepted. `pre_bg` remains continuous as an **input**, which recovers most of the loss. |
| Synthetic data | Results are about the method on data of this shape, **not about any real person's physiology.** A generator can only exhibit the structure it was given. | Accepted, and it is the point. Ground truth is what makes H-2 and H-3 measurable at all. **RQ-1 guards the obvious failure**: a generator too clean to be a real test. |

## 8. Constraints

- Single simulated subject. **No design choice may be justified by "what if we scale."**
- Python is forced (statsmodels/PyMC).
- **Data can be regenerated, but results cannot be reproduced across a parameter change.** A `00a §4` parameter change invalidates every result produced before it — hence REQ-054, versioned and never overwritten.
- The system must remain comprehensible in two years, to someone who has forgotten how it works and is trying to judge whether the result still stands.

## 9. Open Questions — CLOSED as declared assumptions

**All seven are closed.** There is no endocrinologist and no patient, so none of
them blocks. They are resolved as **declared research parameters** (`00a §4`) —
chosen to be internally consistent and clinically plausible, with stated
provenance. BA still owns this table.

| # | Was | Resolved as | Was blocking |
|---|---|---|---|
| OQ-1 | Confirm ICR | **8.3 g/U** — 500-rule, 500/60 | ~~Gate 2~~ |
| OQ-2 | Confirm ISF = 30 | **30 mg/dL/U** — 1800-rule, 1800/60. `isf_source = declared` | ~~Gate 2~~ |
| OQ-3 | Basal:bolus split | **45:55** — mid-range of the 40–50% guidance | ~~Data quality~~ |
| OQ-4 | Confirmed hypo unawareness? | **Assumed true.** It is what makes hypo recall the primary metric | ~~Alert tuning~~ |
| OQ-5 | State 2 upper boundary at 80 | **80 mg/dL**, as specified in `03 §1` | ~~State model~~ |
| OQ-6 | Is the 120–150 target intentional | **target_bg = 135** | ~~Baseline, prescriptive~~ |
| OQ-7 | Is she aware of and does she approve | **Not applicable — there is no patient.** | ~~Everything~~ |

> ⚠ **Declared is not confirmed.** These are inputs to an experiment, not
> clinical facts, and no result produced with them may be read as a statement
> about anyone's actual insulin requirements. The ISF warning in
> `00-glossary.md` and `07 §1` stands: it explains the loss asymmetry that makes
> hypo recall primary, and it must not be deleted.

### Genuinely open — research questions

| # | Question | Affects |
|---|---|---|
| RQ-1 | Does the generator produce a realistically confounded dataset, or one that is too easy? A model that beats the baseline on unrealistically clean data has shown nothing. | H-1, H-2 |
| RQ-2 | Is n≈150 enough to distinguish "the model does not help" from "the model is underpowered"? Report the confidence interval, not just the point estimate. | H-1 |
| RQ-3 | At what confounding strength does the INV-8 constraint stop rescuing the fit? | H-2 |
