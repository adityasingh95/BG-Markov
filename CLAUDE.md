# CLAUDE.md — Agent Operating Manual

## What this system is

**A research build.** It tests whether a 2-hour post-meal glucose model can be made
to work on small, confounded, single-subject data, and whether the guardrails in
`docs/07-clinical-model-spec.md` are the right ones.

**It is not for clinical use. There is no patient and no endocrinologist, and
nothing here waits on a clinical sign-off.** Read `docs/00a-research-mode.md`
before you touch anything — it decides what blocks and what does not.

The subject is simulated: a 59-year-old woman with 30 years of Type 1 Diabetes and
impaired hypoglycaemia awareness, who cannot reliably feel a low. That framing
still drives the objective function — a missed low costs more than a missed high,
so hypo recall stays primary — but no real person is exposed to any output.

A defect here is not a bug ticket: it is a wrong answer you will believe. Write
code accordingly.

## Context to load before doing anything

`README.md` → `docs/00-glossary.md` → `docs/00a-research-mode.md` → `docs/10-backlog.md` (find next story) → the docs that story references.

**Precedence:** `docs/00a-research-mode.md` wins on scope and gating — what blocks, what is retired, which parameters are declared. `docs/07-clinical-model-spec.md` wins on all clinical and model matters. If another doc appears to contradict either, stop and raise it. Do not resolve the contradiction yourself.

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

| ID | Invariant | Status |
|---|---|---|
| INV-1 | ~~Prescriptive module disabled until Gate 2 passes.~~ | **RETIRED** (`00a §3.1`) — no clinical gate. ICR is a declared parameter. |
| INV-2 | ~~No patient-visible model output until Gate 1 passes.~~ | **RETIRED** (`00a §3.1`) — no patient surface exists. |
| INV-3 | Recommended bolus never negative; never exceeds `MAX_BOLUS_U` (15 U). | **KEPT** — a 40 U output is a bug signal. |
| INV-4 | No bolus recommended when `current_bg < 80`. | **KEPT** — a behaviour under test. |
| INV-5 | ~~The system never recommends reducing fingerstick frequency.~~ | **RETIRED** as an invariant; retained as a **copy rule** (`00a §6`). |
| INV-6 | Predicted BG outside [20, 600] mg/dL raises a hard error. | **KEPT** — 620 means the model is broken. |
| INV-7 | Hypo-rescued meals excluded from outcome regression, **retained as hypo events**. | **KEPT — most important in this build.** |
| INV-8 | `β_insulin` constrained ≥ 0 in every fitted model. Insulin cannot raise glucose. | **KEPT — this is the hypothesis under test.** |
| INV-9 | Every prediction is written to `prediction_log` **before** it is returned. | **KEPT** — an incomplete log cannot be analysed. |

**Numbering is deliberately unchanged.** Retired invariants keep their numbers so
every cross-reference in the pack still resolves and the retirement stays visible
instead of vanishing. Retirements are recorded in the decision log with a
reversal path.

**Rules:**
1. Each **kept** invariant is **one named function in `core/safety.py`**. Nowhere else. No re-implementation. Retired invariants have no function; `core/safety.py` carries a comment naming each retirement and pointing at `00a §3.1`.
2. Invariants raise `SafetyViolation`. **Never `assert`** — asserts are stripped under `python -O`.
3. `core/safety.py` imports nothing from the project. This prevents circular weakening.
4. **No fixture, mock, config flag, or env var may bypass a kept invariant.** SDET writes a test proving this for each.
5. If Dev needs to weaken a kept invariant to make a story work, **the story is wrong, not the invariant.**
6. **Retiring an invariant is a documented decision, never a code change.** Deleting a guardrail because research mode "probably" covers it is the failure this table exists to prevent. If it is not listed RETIRED above, it is in force.

### The three that will be under most pressure

- **INV-7 (hypo-rescued meals retained).** The obvious refactor — "invalid rows get dropped from training" — silently deletes exactly the lows the model exists to predict. The model then trains on a world with no lows and scores hypo recall against a dataset containing none: **an excellent-looking result that means nothing.** S-203 has a regression guard. Do not delete it when it becomes inconvenient.
- **INV-8 (sign-constrained `β_insulin`).** In this build the constraint is not a safety measure bolted onto a model — **it is the thing being tested.** The generator can be configured to dose in response to carbs and pre-BG, producing a dataset in which naive OLS concludes insulin raises glucose. Whether the constraint rescues that fit is a headline result. Report it either way.
- **ADR-8 (reported timestamps).** Defaulting a clinical timestamp to `datetime.now()` is the most natural thing to write and it is wrong. The subject is modelled as logging at the laptop 40 minutes after eating. Conflating log time with event time fabricates `bolus_offset_min` and `elapsed_min` — with no error, no warning, and no way to detect it afterwards. **In synthetic data this is exactly where a generator bug hides.**

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

- A test cannot pass without weakening a **kept** invariant or a validity guardrail (`00a §3.2`).
- Docs conflict.
- A **declared research parameter** (`00a §4`) needs changing. Changing one invalidates every result produced before it.
- Retiring anything not already listed RETIRED.
- **The model performs suspiciously well.** Almost always leakage — and synthetic data leaks far more easily than real data, because the generator knows the answer. Investigate before celebrating.
- `β_insulin` negative in an unconstrained fit. Constrain it, but **report it as a finding** — in this build it is a result, not a nuisance.
- Any model or `core/` module gaining the ability to read the generator's parameters. That invalidates the experiment.

**Research mode relaxes what blocks. It does not relax what is true.**

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

The most likely failure of this project is not a crash. It is a model that looks
good on retrospective data and is quietly wrong about a low.

That failure mode does not go away because no one is relying on the output. It
gets **easier** — a synthetic dataset will hand you a beautiful score if you let
it leak, and there is no patient outcome to contradict you. The only thing
standing between this build and a confident wrong conclusion is the validity
suite: forward-chaining CV, the leakage tests, INV-7, INV-8, and hypo recall as
the primary metric.

Every guardrail exists to make that failure **loud instead of silent.**
