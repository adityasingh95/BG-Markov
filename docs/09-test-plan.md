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
| **Safety** | `tests/safety/` | Every commit | **INV-2..9 (INV-1 retired, S-1011). Adversarial.** Assume a future refactor will try to weaken these. |
| **Property** | `tests/property/` | Every commit | `hypothesis`. Monotonicity, bounds, invariance. |
| **Golden** | `tests/golden/` | Every commit | Hard-coded clinical values. Locks curves against silent regression. |
| **Unit** | `tests/unit/` | Every commit | Pure functions. |
| **Grep/AST** | `tests/forbidden/` | Every commit | **Forbidden patterns.** Cheap, and they will fire. |
| **Integration** | `tests/integration/` | Every commit | Repositories, API routes, end-to-end flows. |
| **Leakage** | `tests/leakage/` | Every commit | **Temporal splits.** The one class of bug that makes a model look brilliant and be useless. |
| **A11y** | `tests/a11y/` | Pre-merge | `axe`. 200% zoom. |
| **End-to-end** | `tests/e2e/` | Every commit | **The whole chain on synthetic data.** Catches invariants that hold in isolation but are bypassed by the wiring between stages. |

**Coverage:** ≥ 90% on `core/`, `features/`, `models/`, `prescribe/`, `data.predictions`. Build fails below.

### 2.1 End-to-end / chain-level testing — REQ-057 **[SAFETY]**

Unit safety tests prove each invariant holds *where it is defined*. They cannot prove the
**wiring** between stages preserves it. This layer drives one synthetic dataset through
logging → validity/INV-7 → features → fit → temporal CV → metrics → gates → readout → shadow
report → bolus, and asserts across the chain:

| Assertion | Why it can only be caught here |
|---|---|
| **INV-7 across the chain** | A rescued low is absent from the training set the model is *actually fit on*, yet present in `get_hypo_events()` **and** in the hypo-recall denominator. Unit tests check the repository; only this checks what the fit consumed. |
| **INV-2 end-to-end** | With <150 valid meals the patient path refuses while the operator dashboard still renders. |
| **INV-9 end-to-end** | Every prediction served in the run was persisted *before* it was returned. |
| **No temporal leakage** | Every fold satisfies `max(train.datetime) < min(test.datetime)` and shares no `date` across train/test. |
| **Gate refusals** | Each gate refuses for the right reason, with no bypass, through the real call path. |

**This must not be allowed to degrade into a smoke test.** "It ran without raising" is not an
assertion. Every case above names a specific wrong-state and fails on it.

### 2.2 Synthetic data — REQ-056 **[SAFETY]**

The generator that feeds the E2E layer is itself safety-relevant.

- **Seeded and reproducible** — a fixed seed yields byte-identical output, or a failure is not
  investigable.
- **Honours reported-timestamp discipline** (ADR-8): no generated clinical `datetime` comes from
  the system clock.
- **Never importable by production code.** A guard in `tests/forbidden/` asserts `core/`,
  `models/`, `prescribe/`, `api/`, and `data/` do not import it. Synthetic rows must never reach
  a real fit, and must never be presented as her data.

---

## 3. ★ Safety Testing

`core/safety.py` holds **INV-2..INV-9** (INV-1 retired, S-1011 — **the number is not reused**). It **imports nothing from the project** (ADR-6) — this prevents circular weakening under refactor.

### Rules

1. Each invariant has a **positive and a negative** test.
2. Invariants raise `SafetyViolation`. **Never `assert`** — asserts are stripped under `python -O`. **There is a static test enforcing no `assert` appears in `core/safety.py`.**
3. **Each invariant has a "no bypass" test** proving no fixture, mock, config flag, or environment variable can defeat it.
4. A grep test proves no other module re-implements an invariant's logic.

### The tests most likely to be under pressure

| Test | Why it will be attacked |
|---|---|
| **The ICR error's *kind*** | INV-1 is retired (S-1011). A bad ICR must raise a plain `ValueError` — **never** a `SafetyViolation`/`GateNotPassed`, and never a re-introduced gate under a new name. `test_bolus.py` pins this explicitly, because "something raised" is not the same assertion. |
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
- [ ] BA has updated the traceability matrix.

---

## 10. What The Tests Are Actually For

The most likely failure of this project is **not a crash**.

It is a model that looks good on retrospective data, **gets trusted**, and is quietly wrong about a low — in a woman who cannot feel one.

Every test in `tests/safety/` and `tests/leakage/` exists to make that failure **loud instead of silent.**

When one of them is in your way, **that is the test working.**
