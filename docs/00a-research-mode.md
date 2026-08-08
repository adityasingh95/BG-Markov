# 00a — Research Mode

*Purpose: declares what this build is for, what that relaxes, and what it does not.*
*Read before: everything except `00-glossary.md`.*

---

## 1. What this build is

**This is a research build. Its purpose is to test whether the modelling approach
in `07-clinical-model-spec.md` works.** It is not built to predict for, prescribe
to, or otherwise inform the care of any person.

There is no patient. There is no endocrinologist. Nothing here waits on a
clinical sign-off, and no output of this system may be used to make a treatment
decision.

The original pack was written for a specific real person. That framing is
retained in the documents where it explains *why* a design choice was made —
the asymmetry between a missed high and a missed low is still the right
objective function, and hypo recall is still the primary metric. What is removed
is the machinery that existed to protect a real person from an unproven system.

## 2. Precedence

| Matter | Authority |
|---|---|
| Scope, gating, what blocks what | **This document** |
| Clinical and model matters | `07-clinical-model-spec.md` |
| Everything else | The document that owns it |

This document never overrides `07` on a clinical or modelling question. It only
answers *"does this need a human's permission to proceed?"* — and in this build,
the answer is always no.

---

## 3. ★ The distinction that governs every change below

The guardrails in this pack are of two kinds. They are not relaxed together.

### 3.1 Clinical-authorization gates — RELAXED

These exist to stop an unvalidated system from reaching a person who could be
harmed by it. With no such person, they gate nothing.

| Retired | Was | Now |
|---|---|---|
| **INV-1** | Prescriptive module hard-blocked until an endocrinologist confirms ICR | ICR is a declared research parameter (§4). The prescriptive module is buildable. **Its output is a number in a study, not a dose.** |
| **INV-2** | No patient-visible model output until Gate 1 | There is no patient surface. Model output is always visible to the researcher, always labelled with its gate state and model version. |
| **INV-5** | Never recommend reducing fingerstick frequency | No one is being advised. Retired as an invariant; retained as a **copy rule** for any UI text (§6). |
| **Gate 2** | Blocked on OQ-1 and OQ-2 | Opens on declared parameters (§4). |
| **Gate 1's 90-day shadow clock** | 90 calendar days of prospective logging | Replaced by **held-out temporal evaluation** — the scientific content of the requirement without the calendar. |
| **OQ-1 .. OQ-7** | Blocking questions for the endocrinologist | Closed as **declared research assumptions** (§4). None blocks. |

### 3.2 Validity guardrails — KEPT, AND THEY MATTER MORE HERE

These have nothing to do with clinical approval. They are what makes a result
*true*. A theory verified with these removed is not verified.

| Kept | Why it is load-bearing in a research build |
|---|---|
| **INV-3** | Bounds on the recommendation are how you detect that the arithmetic has gone wrong. A dose of 40 U in a study is a **bug signal**. |
| **INV-4** | Same: a refusal below 80 is a behaviour under test, not a courtesy. |
| **INV-6** | A predicted BG of 620 means the model is broken. Hard error. |
| **INV-7** | ★ **The single most important one here.** Drop rescued meals and you train on a world with no lows, then measure hypo recall against a dataset that contains none. The result would look excellent and mean nothing. |
| **INV-8** | ★ The sign constraint is **the hypothesis under test**. Whether it rescues a confounded fit is a headline result, not a safety detail. |
| **INV-9** | Write-before-return is what makes the prediction log a complete record. An incomplete log cannot be analysed afterwards. |
| **ADR-6** | `core/safety.py` keeps zero internal imports. Prevents circular weakening. |
| **ADR-7** | Gates evaluated live, never cached. |
| **ADR-8** | ★ Reported vs. logged timestamps. In synthetic data this is where a generator bug hides silently. **The most important forbidden pattern remains the most important.** |
| **ADR-10** | No ML in the dose calculation. The causal/predictive split is part of what is being tested. |
| **Leakage suite** (`09 §7`) | ★ Forward-chaining CV, no shared days across folds, no target leakage. **If the model performs suspiciously well, this is still why.** |
| **Forbidden patterns** (`09 §6`) | Unchanged. Every one of them is a correctness trap, not a policy. |
| **Metric suite** (`07 §9`) | Hypo recall @ fixed FAR stays primary. Plain accuracy stays unreported. |

**INV numbering is unchanged.** Retired invariants keep their numbers and are
marked retired, so every cross-reference in the pack still resolves and the
retirement stays visible rather than vanishing.

---

## 4. Declared research parameters

These replace OQ-1..OQ-7. They are **declared, not confirmed** — chosen to be
internally consistent and clinically plausible, with stated provenance. Every one
is versioned per REQ-054 and carries its source.

| Parameter | Value | Provenance | Was |
|---|---|---|---|
| `ICR` | **8.3** g/U | 500-rule: 500 / 60 U TDD | OQ-1, blocked Gate 2 |
| `ISF` | **30** mg/dL/U | 1800-rule: 1800 / 60 U TDD | OQ-2, blocked Gate 2 |
| `isf_source` | `declared` | New enum value alongside `default` \| `endo` \| `derived` | — |
| `target_bg` | **135** | Midpoint of 120–150 | OQ-6 |
| State boundaries | **[54, 80, 181, 251]** | As specified in `03 §1` | OQ-5 |
| `hypo_unaware` | **true** | Modelling assumption; drives the loss asymmetry | OQ-4 |
| `TDD` | **60** U | Study subject definition | — |
| Basal : bolus | **45 : 55** | Mid-range of the 40–50% guidance in `00-glossary.md` | OQ-3 |

**ISF derivation from correction events (`07 §6`) is retained in full.** It is no
longer a route to unblocking a gate — it is now a **result**: does the derivation
recover the ISF the generator was configured with? That is a direct test of the
method, and it is more informative than the gate it used to open.

> ⚠ The warning in `00-glossary.md` and `07 §1` about ISF being the most
> dangerous constant **still stands and must not be deleted.** It explains the
> asymmetry that makes hypo recall the primary metric. It is now a statement
> about the objective function rather than about her.

---

## 5. Data source — synthetic, with known ground truth

There is no real logging, so there is no 150-meal adherence clock, and **the
argument that "the model is not the bottleneck" no longer holds.** The build
order in `10-backlog.md` is re-ordered accordingly.

Data comes from a **generator with declared ground-truth parameters**. This is
strictly better than observational data for the purpose:

1. **The true parameters are known.** ICR, ISF and the true β values are inputs
   to the generator, so parameter recovery becomes measurable — an error bar,
   not an opinion.
2. **Confounding can be dialled in deliberately.** The generator can be told to
   dose in response to carbs and pre-BG, producing exactly the dataset in which
   naive OLS learns *insulin raises glucose*. INV-8 either rescues it or does
   not, and that is the experiment.
3. **Lows can be made to occur at a known rate**, so hypo recall has a
   denominator you actually trust.
4. **Leakage is detectable.** With known ground truth, a suspiciously good score
   can be attributed rather than argued about.

**The generator is not part of the system under test.** It lives in its own
package, is never importable from `core/`, `features/`, `models/` or
`prescribe/`, and its parameters are never readable by the model. A test
enforces this — a model that can see the generator's parameters proves nothing.

Real or public datasets may be substituted later; nothing in the pipeline may
depend on data being synthetic.

---

## 6. What is still forbidden

Relaxing the clinical gates does not license any of the following.

| Forbidden | Why |
|---|---|
| Presenting any output as clinical guidance | The system is not validated, and in this build it never will be. |
| Removing the non-clinical-use banner from any surface that renders a number | The banner is the thing that stops this being mistaken for the other kind of system. |
| Text suggesting reduced glucose testing | Retired as INV-5, retained as a copy rule. It costs nothing and it stays. |
| Real patient data of any kind | Out of scope. Nothing here is built to hold it. |
| Deleting a validity guardrail from §3.2 | If one is in the way, that is the guardrail working. Escalate. |
| Silently changing a §4 parameter | Versioned, never overwritten (REQ-054). A changed parameter invalidates prior results. |

## 7. Escalate — still

The list in `CLAUDE.md` shrinks but does not vanish. Still escalate:

- A test cannot pass without weakening a **§3.2** guardrail.
- Documents conflict.
- **The model performs suspiciously well.** Unchanged, and more likely here:
  synthetic data is much easier to leak than real data.
- `β_insulin` negative in an unconstrained fit — now a **finding to report**,
  not just a warning to log.
- A §4 parameter needs changing.

## 8. If this ever stops being a research build

Restoring clinical use is **not** a matter of flipping a flag. It requires
reinstating INV-1, INV-2 and INV-5, restoring the gates and the shadow-mode
clock, and answering OQ-1..OQ-7 with an actual endocrinologist. The retirements
in §3.1 are recorded in the decision log with that reversal path attached.

**Nothing in this build should be read as evidence that the system is safe to
use. It is evidence about a method, and only that.**
