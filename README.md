# Glycaemic Prediction & Bolus Support — Spec Pack

A research build that tests whether a 2-hour post-meal blood glucose model can be
made to work on small, confounded, single-subject data — and whether the
guardrails in `07-clinical-model-spec.md` are the right ones.

**Subject:** a simulated 59F, Type 1 Diabetes, 30 years duration. Fiasp (bolus), Tresiba (basal). TDD ~60 U.
**Users:** the researcher. There is no patient.
**Deployment:** single laptop, localhost. v1.

---

## ⚠️ Read this before anything else

**This is a research build. It is not for clinical use, and no output of it may
inform a treatment decision.** There is no patient and no endocrinologist, and
nothing here waits on a clinical sign-off. See `docs/00a-research-mode.md` —
read it before any other document except the glossary.

The pack was originally written for a specific real person who could not
reliably feel a low. That framing survives wherever it explains **why** a design
choice was made: the asymmetry between a missed high and a missed low is still
the right objective function, and hypo recall is still the primary metric.

What that means for the guardrails, in one line each:

- **The gates that protected a person are retired** — INV-1, INV-2, INV-5,
  Gate 2's clinical block, the 90-day shadow clock, OQ-1..OQ-7.
- **The guardrails that make a result true are kept** — INV-3/4/6/7/8/9, the
  leakage suite, forward-chaining CV, reported timestamps (ADR-8), the
  forbidden-pattern tests, and hypo recall as the primary metric.

The second list is not clinical red tape. Strip INV-7 and the model trains on a
world with no lows, then scores hypo recall against a dataset that contains
none. **It would look excellent and mean nothing** — which is the exact failure
this build exists to detect.

**A defect here is not a bug ticket.** When a guardrail is in your way, that is
the guardrail working.

---

## Read order

| # | Doc | Purpose |
|---|-----|---------|
| — | `CLAUDE.md` | **How the agents work.** Dev/SDET/BA roles, TDD loop, forbidden patterns, escalation. Read first. |
| 00 | `docs/00-glossary.md` | Clinical and technical terminology. Read before anything else — the domain is unfamiliar. |
| 00a | `docs/00a-research-mode.md` | **What this build is for.** What the research framing relaxes, what it does not, and the declared parameters that replace the open clinical questions. |
| 01 | `docs/01-prd.md` | Problem, users, scope, non-goals, success criteria, REQ-nnn register, open questions. |
| 02 | `docs/02-functional-spec.md` | Flow-level behaviour. The logging flow is the critical path. |
| 03 | `docs/03-state-model.md` | Glycaemic states, record lifecycle, gate state machine. |
| 04 | `docs/04-data-model.md` | Entities, fields, validity rules. |
| 05 | `docs/05-api-contract.md` | Endpoints, payloads, errors. |
| 05b | `docs/05b-ui-ux-spec.md` | Accessibility, logging ergonomics, risk-readout language. |
| 06 | `docs/06-tech-architecture.md` | Stack, laptop topology, ADRs, durability. |
| 07 | `docs/07-clinical-model-spec.md` | **Domain core.** IOB curve, basal EWMA, baseline, ordinal model, ICR/ISF derivation, guardrails. |
| 08 | `docs/08-scenario-pack.md` | Gherkin scenarios, including the safety scenarios. |
| 09 | `docs/09-test-plan.md` | Test layering, coverage, safety-invariant testing, TDD strategy. |
| 10 | `docs/10-backlog.md` | Epics, stories, acceptance criteria, per-story TDD strategy. |
| — | `KICKOFF-PROMPT.md` | Paste into Claude Code to begin. |

---

## Operating rules for the executing agent

**Session start — every session, no exceptions:**
1. Read `CLAUDE.md`.
2. Read `docs/00-glossary.md`. The domain is clinical; the terms are not guessable.
3. Read `docs/00a-research-mode.md`. It decides what blocks and what does not.
4. Read `docs/10-backlog.md` §Build Order. Identify the next story.
5. Confirm the story's `[SAFETY]` status and which INV-n it touches.

**Stop and ask. Do not decide these yourself:**
- A test cannot pass without weakening a **validity guardrail** (`00a §3.2`).
- Two documents conflict. (Precedence: `00a` on scope and gating; `07-clinical-model-spec` on clinical/model matters.)
- A declared research parameter (`00a §4`) needs changing. It invalidates prior results.
- The model performs *suspiciously well* — this is almost always leakage, and synthetic data leaks more easily than real data. Investigate; do not celebrate.
- `β_insulin` comes out negative in an unconstrained fit. **Report it as a finding.**

**Mark every assumption.** If you must proceed on an assumption, state it explicitly and record it in the decision log. BA owns that list.

**Scope reminder.** v1 is a single laptop, localhost, no auth, no reminders, no CGM. Deferred items are listed in `01-prd.md` §Non-Goals. Do not build them.

---

## Critical path

**With no real subject there is no adherence clock, so the model *is* the
bottleneck.** This inverts the original build order, which was written when
three months of a real person's logging stood between EPIC 1 and any result.

Data comes from a generator with declared ground-truth parameters
(`00a §5`), so the experiment can run as soon as the generator and the
features exist.

```
EPIC 1 (Foundation) → EPIC 2 (Data) → EPIC 3a (Generator)
                                            │
                                    ★ DATA AVAILABLE
                                            │
                      EPIC 4 (Features) → EPIC 5 (Baseline) → EPIC 6 (Model)
                                        → EPIC 7 (Validation)
                                        → EPIC 8 (Guardrails/Output)
                                        → EPIC 9 (Prescriptive)
                                            │
                                    EPIC 3b (Logging UI) — last
```

Three hard rules:
1. **The generator is not part of the system under test.** It lives in its own package, and no module under `core/`, `features/`, `models/` or `prescribe/` may import it or read its parameters. A test enforces this. A model that can see the answer key proves nothing.
2. **S-501 (the clinical baseline) is still built before any ML.** It takes an afternoon, and it remains the bar the model must beat. If the ordinal model cannot beat it, that is the finding.
3. **The validity guardrails in `00a §3.2` are not negotiable for speed.** They are the difference between a result and a number.
