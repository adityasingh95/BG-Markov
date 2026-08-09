# Traceability Matrix

*Owner: BA. Any requirement without a covering test is a visible gap, and is
listed as one here rather than left to be noticed later.*

**Status at this commit: nothing is implemented.** The branch carries the
specification and the decisions taken on it. Every row below is `⬜ Not started`
by design — the matrix exists now so that no story can close without it being
updated, not because there is progress to report.

Three things trace: **REQ → story → test**, **INV → story → test**, and
**H → story → result**. The third is new in research mode and is the one that
decides whether the build produced anything.

---

## 1. H-n → story → result

**The deliverable.** An unanswered hypothesis at EPIC 10 is a gap in exactly the
way an untested REQ is.

| H | Question | Story | Answered in | Status |
|---|---|---|---|---|
| H-1 | Ordinal model vs. clinical baseline on hypo recall at n≈150 | S-501, S-601, S-702 | S-1001 | ⬜ |
| H-2 | Does the INV-8 sign constraint recover the true insulin effect from confounded data | S-308, **S-503** | S-1001, S-1002 | ⬜ |
| H-3 | Does correction-event ISF beat the OLS estimate against ground truth | S-309, S-502, S-503 | S-1002 | ⬜ |
| H-4 | Do the guardrails refuse on the right cases and answer on the rest | S-801, S-901 | S-1001 | ⬜ |
| H-5 | Does the leakage suite catch a deliberately planted leak | **S-701** | S-1001 | ⬜ |

## 2. INV-n → story → test

| INV | Status | First enforced by | Test | Status |
|---|---|---|---|---|
| INV-1 | **Retired** (`00a §3.1`, DL-001) | — | S-104 asserts **no such function exists** | ⬜ |
| INV-2 | **Retired** (`00a §3.1`, DL-001, DL-010) | — | S-104 asserts absence | ⬜ |
| INV-3 | Kept | S-104, S-901 | Cap **and** flag both asserted; property: never <0, never >15 | ⬜ |
| INV-4 | Kept | S-104, S-901 | BG 79 refuses / BG 80 computes | ⬜ |
| INV-5 | **Retired** as invariant; copy rule (`00a §6`) | — | S-104 asserts absence | ⬜ |
| INV-6 | Kept | S-104, S-801 | 601 raises / 600 does not | ⬜ |
| INV-7 | Kept — **most important** | S-203, S-309 | 100 meals, 20 rescued ⇒ training excludes 20, `get_hypo_events()` returns 20 | ⬜ |
| INV-8 | Kept — **the hypothesis** | S-503 | Confounded dataset ⇒ unconstrained `β_ins < 0`, warning fires, constrained `β_ins ≥ 0` | ⬜ |
| INV-9 | Kept | S-802 | Persistence fails ⇒ **nothing returned** | ⬜ |

## 3. REQ-nnn → story → test

### Logging — EPIC 3b, deprioritised
REQ-001..014 belong to the logging UI, which is not on this build's critical
path (`00a §5`, DL-002). **Retained as specification, untested until 3b is
built.** REQ-004 and REQ-005 are the exceptions: they are enforced at the data
layer by S-202 and exercised by the generator (S-308), so they are live now.

| REQ | Story | Test | Status |
|---|---|---|---|
| REQ-004, 005 | S-202, S-308 | Reported vs. logged times differ; AST test on `datetime.now()` | ⬜ |
| REQ-012, 013 | **S-309** | Generator emits rescues and correction events | ⬜ |
| REQ-001..003, 006..011, 014 | S-301..S-303, S-306 (EPIC 3b) | — | ⏸ Deferred |

### Data & derivation
| REQ | Story | Test | Status |
|---|---|---|---|
| REQ-020 | S-401 | Monotonic decrease on (0, td); 6 golden pairs to 4 dp | ⬜ |
| REQ-021 | S-402 | 24→30 U step: strictly between at +1d, within 0.5 at +5d | ⬜ |
| REQ-022 | S-203 | Window boundaries 104/105 and 135/136 | ⬜ |
| REQ-023 | S-203, S-309 | The INV-7 regression guard | ⬜ |
| REQ-024 | S-403 | Non-monotonicity permitted by the encoding | ⬜ |

### Model
| REQ | Story | Test | Status |
|---|---|---|---|
| REQ-030 | S-501 | Zero carbs/bolus/IOB ⇒ post = pre; 5 golden cases | ⬜ |
| REQ-031 | S-601 | Grep `multi_class` absent; probabilities sum to 1 | ⬜ |
| REQ-032 | S-503 | See INV-8 | ⬜ |
| REQ-033 | S-502 | 4 events ⇒ reported only; 5 ⇒ applied | ⬜ |
| REQ-034 | S-701 | Temporal ordering + no shared day, every fold | ⬜ |
| REQ-035 | S-702 | Clarke goldens; grep `accuracy_score` absent | ⬜ |

### Safety & validity
| REQ | Story | Test | Status |
|---|---|---|---|
| ~~REQ-040, 041, 048, 049~~ | — | **Retired** — DL-001 | ✂ Retired |
| REQ-042, 043 | S-901 | Cap + flag; 900 g typo case; BG 79/80 | ⬜ |
| REQ-044 | S-801 | 601 raises, 600 does not | ⬜ |
| REQ-045 | S-802 | Write-before-return | ⬜ |
| REQ-046 | S-801 | All five refusal conditions | ⬜ |
| REQ-047 | S-803 | Trips on drift; a good prediction does **not** re-arm it | ⬜ |
| **REQ-055** | **S-310** | Import-graph test: generator unreachable from the model | ⬜ |
| REQ-056 | S-503, S-1002 | Derived vs. true ICR/ISF, with error bars | ⬜ |
| REQ-057 | S-701, S-703 | Held-out temporal evaluation | ⬜ |
| REQ-058 | S-804, S-901 | Banner on every path that renders a number | ⬜ |

### Operations
| REQ | Story | Test | Status |
|---|---|---|---|
| REQ-050, 051, 052 | S-304 | Backup during write is valid; restore byte-identical; **drill executed** | ⬜ |
| REQ-053 | S-307, **S-311** | Lag metric from two distinct columns; daily view renders invalid rows | ⬜ |
| REQ-054 | S-201, S-103 | Profile change creates a new row, never an update | ⬜ |

---

## 4. Known gaps — carried deliberately

These are recorded because a gap that is written down is a decision, and a gap
that is not is an accident.

| Gap | Where | Why it is open |
|---|---|---|
| `macro_confidence < 50` is unreachable | DL-012 | Only 95 and 60 are ever assigned, so the `low_confidence` rule cannot fire. S-308 can emit low-confidence rows deliberately, which makes the rule testable rather than dead. |
| `pre_bg_time` has no specified source | DL-013 | Absent from the F-1 flow and the tap budget — **the exact place an implementation reaches for `now()`.** Belongs to EPIC 3b; S-308 must emit it explicitly so the field is exercised meanwhile. |
| Insulin pen dose granularity | DL-007 | Pens deliver in 0.5/1 U steps; 7.96 U is not deliverable. Harmless while the number is never injected. **Must be settled before any clinical use** — and rounding up is the unsafe direction. |
| REQ-001..014 untested | EPIC 3b | The logging UI is deferred. If it is ever built, these become live gaps immediately. |

## 5. Decisions affecting this matrix

`docs/decision-log.md` — DL-001 (research mode), DL-002 (build order), DL-004
(gates close), DL-005 (bolus ceiling), DL-006 (`elapsed_min`), DL-008 (`hypo_bg`),
DL-009 (`β_ins == 0`), DL-011 (nullable follow-up columns).
