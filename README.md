# Glycaemic Prediction & Bolus Support — Spec Pack

A single-patient system that predicts 2-hour post-meal blood glucose and (once clinically gated) supports insulin dose calculation.

**Patient:** 59F, Type 1 Diabetes, 30 years duration. Fiasp (bolus), Tresiba (basal). TDD ~60 U.
**Users:** the patient; her son as operator/developer.
**Deployment:** single laptop, localhost. v1.

---

## ⚠️ Read this before anything else

This system is built for **one real person who cannot reliably feel a low.** After 30 years of T1D her glucagon counter-regulatory response is presumed absent and her adrenergic response blunted. She can be at 50 mg/dL and feel fine.

Every unusual constraint in this pack — the gates, the guardrails, the shadow mode, the refusal to ship a dose calculator on an unconfirmed number — exists because of that fact.

**A defect here is not a bug ticket.** When a guardrail is in your way, that is the guardrail working.

---

## Read order

| # | Doc | Purpose |
|---|-----|---------|
| — | `CLAUDE.md` | **How the agents work.** Dev/SDET/BA roles, TDD loop, forbidden patterns, escalation. Read first. |
| 00 | `docs/00-glossary.md` | Clinical and technical terminology. Read before anything else — the domain is unfamiliar. |
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

## Running & verifying the build (EPIC 1–2 shipped)

Requires **Python 3.12** and (for the accessibility tests) an internet
connection so Playwright can fetch a Chromium build the first time.

```bash
# 1. Verify everything the way CI does — one command.
#    Creates .venv, installs pinned deps, runs ruff + mypy --strict +
#    pytest with the 90%-on-core coverage gate.
./scripts/verify.sh

# 2. See the EPIC-2 safety behaviour on a real SQLite DB (readable walk-through:
#    portion scaling, reported-vs-logged timestamps, and INV-7 keeping rescued
#    lows out of training while retaining them as hypo events).
. .venv/bin/activate
python scripts/demo_epic2.py

# 3. Run the accessible logging shell (S-102) and open it in a browser.
./scripts/run_app.sh          # -> http://127.0.0.1:8000

# 4. Watch the whole pipeline end-to-end on SYNTHETIC data (no DB, fixed seed):
#    data in -> feature pipeline -> ordinal model -> operator shadow report ->
#    the two gates -> the patient readout -> the bolus calculator (INV-1/3/4,
#    the 900 g typo flagged not dosed, the already-low refusal, the null-ICR block).
#    On the seeded draw the model does NOT beat baseline, so Gate 1 stays CLOSED —
#    that refusal is the system working, not failing.
python scripts/demo_end_to_end.py
```

What "green" means here: lint clean, `mypy --strict` clean on `core`/`api`/`data`,
and every safety test (`tests/safety/`), forbidden-pattern guard
(`tests/forbidden/`), validity/leakage guard, and browser accessibility check
(`tests/a11y/`, real Chromium) passing. The build status is enforced in CI on
every push (`.github/workflows/ci.yml`).

**What is built so far:** EPIC 1 (foundation, safety invariants INV-1..9,
forbidden-pattern suite) and EPIC 2 (schema + migrations, reported timestamps,
validity engine + INV-7, dish table). EPIC 3 (logging & durability — the
critical path) is next.

---

## Operating rules for the executing agent

**Session start — every session, no exceptions:**
1. Read `CLAUDE.md`.
2. Read `docs/00-glossary.md`. The domain is clinical; the terms are not guessable.
3. Read `docs/10-backlog.md` §Build Order. Identify the next story.
4. Confirm the story's `[SAFETY]` status and which INV-n it touches.

**Stop and ask. Do not decide these yourself:**
- A test cannot pass without weakening a safety invariant.
- Two documents conflict. (Precedence: `07-clinical-model-spec` > all others on clinical/model matters.)
- A clinical constant (ICR, ISF, target BG, state boundaries) needs choosing or changing.
- A gate condition needs relaxing to make progress.
- The model performs *suspiciously well* — this is almost always leakage. Investigate; do not celebrate.
- `β_insulin` comes out negative in an unconstrained fit.

**Never work around a blocked gate. The gates are the product.**

**Mark every assumption.** If you must proceed on an assumption, state it explicitly and add it to the Open Questions in `01-prd.md`. BA owns that list.

**Scope reminder.** v1 is a single laptop, localhost, no auth, no reminders, no CGM. Deferred items are listed in `01-prd.md` §Non-Goals. Do not build them.

---

## Critical path

The model was the whole design conversation. **It is not the bottleneck.**

Gate 1 needs **150 valid meals** — roughly three months of her logging. Everything downstream of data collection can be built *while* that clock runs. Every week spent on the ordinal model before logging is live is a week added to the **end** of the project.

```
Ship EPIC 1–3 (logging live)  →  Gate 1 clock starts  →  build the model in parallel
```

Two hard rules:
1. **S-304 (backup + restore drill) runs in month one, before there is real data to lose.** An untested backup is not a backup. Ten weeks of her life does not come back.
2. **EPIC 9 (bolus calculator) does not start until S-703 (gate enforcement) is merged and green.** The calculator is five lines and it is the most dangerous code in the system.
