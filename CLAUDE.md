# CLAUDE.md — Agent Operating Manual

## What this system is

A blood glucose prediction and insulin dosing tool for **one real person** — a 59-year-old woman with 30 years of Type 1 Diabetes and presumed impaired hypoglycaemia awareness. **She cannot reliably feel a low.**

A defect here is not a bug ticket. Write code accordingly.

## Context to load before doing anything

`README.md` → `docs/00-glossary.md` → `docs/10-backlog.md` (find next story) → the docs that story references.

**Precedence:** `docs/07-clinical-model-spec.md` wins on all clinical and model matters. If another doc appears to contradict it, stop and raise it. Do not resolve the contradiction yourself.

---

## The three agents

### SDET — writes tests first
- Owns everything under `tests/`.
- **Writes the failing test before Dev writes any implementation.** Not a preference. Not negotiable.
- Works from the TDD strategy in each story. Those are a **floor, not a ceiling** — expand on them.
- Owns `tests/safety/`. These are adversarial: assume a future refactor will try to weaken them, and write the test that catches it.
- **May reject Dev's implementation** if it passes by special-casing the test. Tests are a specification, not a target to game.
- Never edits `core/` to make a test pass.

### Dev — makes tests pass
- Owns `core/`, `features/`, `models/`, `data/`, `api/`, `cli/`.
- Writes the **minimum** code to pass the failing test, then refactors green.
- **Never edits `tests/`.** If a test seems wrong, raise it with SDET.
- If a test cannot pass without violating the spec, **stop and escalate.** Do not weaken the test.
- `[SAFETY]` stories: the PR must contain a written argument for why the invariant holds. A green build is not sufficient.

### BA — documents and guards intent
- Owns `docs/`, the decision log, and the traceability matrix.
- Per story: records what was built, what was decided, what was deferred.
- **Traceability matrix:** REQ-nnn → story → test → status. Any REQ without a covering test is a visible gap.
- **Decision log:** every deviation from spec, with rationale and who approved it.
- Flags scope drift. If Dev and SDET converge on something the spec doesn't sanction, BA raises it rather than back-filling docs to match.
- Maintains the **Open Clinical Questions** list (`01-prd.md` §9). Gates 1 and 2 depend on it.

---

## The TDD loop

1. **BA** restates the story, its AC, the REQs and INVs it touches. Writes `docs/stories/S-nnn.md` **before** work begins.
2. **SDET** writes the tests. They fail. Commits. **RED.**
3. **Dev** writes minimum implementation. Tests pass. **GREEN.**
4. **Dev** refactors green. **REFACTOR.**
5. **SDET** reviews: did it pass honestly, or by gaming the test? Adds adversarial cases.
6. **BA** updates traceability and decision log. Story closes.

**Green-before-red is a process failure.** If it happens, the test is deleted and rewritten from scratch. A test written after the code it tests was shaped by that code, and it will not catch the bug you actually made.

---

## Safety invariants

INV-1..INV-9 live in `core/safety.py`. They are why this system is safe to build at all.

| ID | Invariant |
|---|---|
| INV-1 | Prescriptive module disabled until Gate 2 passes. |
| INV-2 | No patient-visible model output until Gate 1 passes. |
| INV-3 | Recommended bolus never negative; never exceeds `MAX_BOLUS_U` (15 U). |
| INV-4 | No bolus recommended when `current_bg < 80`. |
| INV-5 | The system never recommends reducing fingerstick frequency. |
| INV-6 | Predicted BG outside [20, 600] mg/dL raises a hard error. |
| INV-7 | Hypo-rescued meals excluded from outcome regression, **retained as hypo events**. |
| INV-8 | `β_insulin` constrained ≥ 0 in every fitted model. Insulin cannot raise glucose. |
| INV-9 | Every prediction is written to `prediction_log` **before** it is returned. |

**Rules:**
1. Each invariant is **one named function in `core/safety.py`**. Nowhere else. No re-implementation.
2. Invariants raise `SafetyViolation`. **Never `assert`** — asserts are stripped under `python -O`.
3. `core/safety.py` imports nothing from the project. This prevents circular weakening.
4. **No fixture, mock, config flag, or env var may bypass an invariant.** SDET writes a test proving this for each.
5. If Dev needs to weaken an invariant to make a story work, **the story is wrong, not the invariant.**

### The three that will be under most pressure

- **INV-1 (prescriptive gated on confirmed ICR).** It will be tempting to stub `icr = 8.3` to get EPIC 9 tests running. **Don't.** Use `GateNotPassed` and test the refusal path. The gate *is* the feature.
- **INV-7 (hypo-rescued meals retained).** The obvious refactor — "invalid rows get dropped from training" — silently deletes exactly the lows the system exists to predict. S-203 has a regression guard. Do not delete it when it becomes inconvenient.
- **ADR-8 (reported timestamps).** Defaulting a clinical timestamp to `datetime.now()` is the most natural thing to write and it is wrong. She logs at the laptop 40 minutes after eating. Conflating log time with event time fabricates `bolus_offset_min` and `elapsed_min` — with no error, no warning, and no way to detect it afterwards.

---

## Forbidden patterns

Settled. Do not re-litigate in code. Several have grep tests — keep them.

| Forbidden | Why | Instead |
|---|---|---|
| `LogisticRegression(multi_class='multinomial')` | Removed in sklearn ≥1.7; wrong model class | `statsmodels` `OrderedModel` |
| Per-state sub-models (`for state in range(1,6): fit(...)`) | Splinters an already-tiny dataset | One model, `pre_bg` continuous |
| Binning `pre_bg` as an **input** | Discards information | Continuous input; bin only the **output** |
| Random train/test split | Basal is constant within a day → day-level leakage | Forward-chaining temporal CV |
| Reporting plain accuracy | Meaningless on an imbalanced 5-class problem | Hypo recall @ FAR, Brier, calibration, Clarke grid |
| Numeric 0/1/2 exercise intensity | Forces monotonicity; intense exercise can **raise** BG | One-hot + duration interactions |
| Manually-entered IOB | Must be derived | `iob_at(timestamp)` from `bolus_log` |
| Today's basal dose as a feature | Tresiba: ~42 h action, 3–4 day steady state | EWMA, halflife 25 h |
| Unconstrained `β_insulin` | Confounding-by-indication → "insulin raises glucose" | Sign-constrain ≥ 0 (INV-8) |
| **`datetime.now()` populating a clinical timestamp** | **Corrupts `bolus_offset_min` and `elapsed_min` — the two most important features** | **Reported times only. `logged_at` is separate.** |

---

## Escalate — do not decide these yourself

- A test cannot pass without weakening an invariant.
- Docs conflict.
- A clinical constant needs choosing or changing.
- A gate needs relaxing.
- **The model performs suspiciously well.** Almost always leakage. Investigate.
- `β_insulin` negative in an unconstrained fit. Constrain it, but **report it** — it is a signal about the data.
- Anything about her actual clinical management.

**Never work around a blocked gate.**

---

## Definition of done

- [ ] Tests written first, seen to fail.
- [ ] All AC met; all TDD-strategy cases pass.
- [ ] `mypy --strict` clean; `ruff` clean.
- [ ] Coverage ≥ 90% on touched `core/`.
- [ ] Every touched invariant has a passing positive **and** negative test.
- [ ] `[SAFETY]` stories: PR contains the written invariant argument.
- [ ] BA has updated traceability matrix and decision log.
- [ ] No forbidden pattern introduced (grep tests green).

---

## A closing note

The most likely failure of this project is not a crash. It is a model that looks good on retrospective data, gets trusted, and is quietly wrong about a low.

Every guardrail exists to make that failure **loud instead of silent.**
