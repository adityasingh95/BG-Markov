# 09 — Test Plan

*Purpose: test layering, coverage, safety-invariant testing, TDD strategy.*
*Read before: writing any test.*

---

## 1. Philosophy

**Tests are written first, and are seen to fail, before any implementation exists.**

Green-before-red is a **process failure**. If it happens, the test is deleted and rewritten from scratch. A test written after the code it tests was **shaped by that code** and will not catch the bug you actually made.

**SDET owns `tests/` absolutely. Dev never edits it.** If a test seems wrong, Dev escalates — Dev does not change it.

---

## 2. Layers

| Layer | Location | Runs | Purpose |
|---|---|---|---|
| **Safety** | `tests/safety/` | Every commit | **The kept invariants — INV-3, 4, 6, 7, 8, 9. Adversarial.** Assume a future refactor will try to weaken these. INV-1/2/5 retired (`00a §3.1`). |
| **Property** | `tests/property/` | Every commit | `hypothesis`. Monotonicity, bounds, invariance. |
| **Golden** | `tests/golden/` | Every commit | Hard-coded clinical values. Locks curves against silent regression. |
| **Unit** | `tests/unit/` | Every commit | Pure functions. |
| **Grep/AST** | `tests/forbidden/` | Every commit | **Forbidden patterns.** Cheap, and they will fire. |
| **Integration** | `tests/integration/` | Every commit | Repositories, API routes, end-to-end flows. |
| **Leakage** | `tests/leakage/` | Every commit | **Temporal splits.** The one class of bug that makes a model look brilliant and be useless. |
| **A11y** | `tests/a11y/` | Pre-merge | `axe`. 200% zoom. |

**Coverage:** ≥ 90% on `core/`, `features/`, `models/`, `prescribe/`. Build fails below.

---

## 3. ★ Safety Testing

`core/safety.py` holds the **kept** invariants — INV-3, 4, 6, 7, 8, 9. It **imports nothing from the project** (ADR-6) — this prevents circular weakening under refactor. INV-1, 2 and 5 are retired (`00a §3.1`); the module names each retirement in a comment so a documented retirement can never be confused with a silent deletion.

### Rules

1. Each invariant has a **positive and a negative** test.
2. Invariants raise `SafetyViolation`. **Never `assert`** — asserts are stripped under `python -O`. **There is a static test enforcing no `assert` appears in `core/safety.py`.**
3. **Each invariant has a "no bypass" test** proving no fixture, mock, config flag, or environment variable can defeat it.
4. A grep test proves no other module re-implements an invariant's logic.

### The tests most likely to be under pressure

| Test | Why it will be attacked |
|---|---|
| **Generator isolation (REQ-055)** | The fastest way to make a model look good is to let it see the answer key — usually by accident, via a shared config object. **This test is the credibility of every number the build produces.** |
| **INV-7 regression guard** | 100 meals, 20 rescued → `get_hypo_events()` returns exactly 20. This exists **specifically** to catch a future refactor that drops invalid rows. It will look like dead weight. **It is not.** |
| **INV-8 confounding** | Requires deliberately constructing a dataset where insulin *appears* to raise glucose. Someone will call it unrealistic. **It is the realistic case.** |
| **INV-9 write-before-return** | Requires mocking a persistence failure and asserting **nothing** is returned. Easy to weaken into "logs a warning." |

---

## 4. Property Tests

| Property | Story |
|---|---|
| `iob_fraction` is **monotonically decreasing** on (0, td) | S-401 |
| `iob_fraction(t) ∈ [0, 1]` for all t | S-401 |
| Predicted probabilities **sum to 1.0** (±1e-6) | S-501 |
| As `pre_bg` rises (all else fixed), `P(state ≥ 4)` is **non-decreasing** | S-501 |
| Bolus recommendation is **non-decreasing in carbs**, **non-increasing in IOB** | S-901 |
| Bolus recommendation is **never negative**, **never > 15** | S-901 |

---

## 5. Golden Tests

Clinical curves must not drift silently under refactor.

| Golden | Content |
|---|---|
| **Fiasp IOB curve** | 6 hard-coded `(t, fraction)` pairs, asserted to 4 dp |
| **Baseline model** | 5 hand-computed predictions |
| **Bolus calculator** | 5 hand-computed doses, exact to 2 dp |
| **Clarke error grid** | Published reference pairs land in documented zones |
| **State binning** | Every boundary: 53/54, 79/80, 180/181, 250/251 |

---

## 6. ★ Forbidden-Pattern Tests

Cheap. They **will** fire — a coding agent stuck at 2am on an ordinal model will reach for `LogisticRegression`, because it is the pattern-matched answer and it is in the source material this project came from.

| Pattern | Test |
|---|---|
| `multi_class` anywhere | grep |
| `for state in range(1, 6): ... fit(` | AST |
| `train_test_split(..., shuffle=True)` | grep |
| `accuracy_score` in the reporting module | grep |
| `assert` in `core/safety.py` | AST |
| Manual IOB assignment | AST |
| **`datetime.now()` populating `datetime`, `pre_bg_time`, `post_bg_time`, or a bolus time** | **AST — the most important one** |
| `pre_bg` passed to the state-binning function on the **input** path | AST |

---

## 7. ★ Leakage Tests

**The one class of bug that makes a model look brilliant and be useless.** If the model performs suspiciously well, **this is why** — investigate before celebrating.

| Test | Assertion |
|---|---|
| Temporal ordering | `max(train.datetime) < min(test.datetime)` in **every** fold |
| Day-boundary | **No `date` appears in both train and test in any fold.** Basal is constant within a day. |
| Scaler fitting | Scaler statistics from a train fold differ from those of the full set |
| No target leakage | `post_bg` and `elapsed_min` never appear in the feature vector |

---

## 8. Per-Story TDD Strategy

Every story in `10-backlog.md` carries a **TDD strategy** block. Those are a **floor, not a ceiling.** SDET expands them.

**The TDD strategy names:**
1. The **failing test to write first**.
2. The **invariants** touched.
3. The **adversarial case** — how a future refactor would break this, and the test that catches it.

---

## 9. What "Done" Means

- [ ] Tests written first; **seen to fail**.
- [ ] All AC met.
- [ ] `mypy --strict` clean; `ruff` clean.
- [ ] Coverage ≥ 90% on touched core modules.
- [ ] Every touched invariant: **positive + negative + no-bypass** tests passing.
- [ ] `[SAFETY]` stories: PR contains a **written argument** for why the invariant holds. A green build is not sufficient.
- [ ] Forbidden-pattern tests green.
- [ ] BA has updated the traceability matrix (`docs/traceability.md`) and the decision log.

---

## 10. What The Tests Are Actually For

The most likely failure of this project is **not a crash**.

It is a model that looks good on retrospective data and is quietly wrong about a low.

**Research mode does not soften this — it sharpens it.** With no patient outcome
to contradict a bad model, and a generator that will hand you a beautiful score
the moment you let it leak, the test suite is the *only* thing standing between
this build and a confident wrong conclusion.

Every test in `tests/safety/` and `tests/leakage/` exists to make that failure **loud instead of silent.**

When one of them is in your way, **that is the test working.**
