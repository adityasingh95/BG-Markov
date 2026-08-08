# Kickoff Prompt

Paste into a fresh Claude Code session at the repo root, with this spec pack in `./` .

---

You are building a **glycaemic prediction and bolus support system** for one real person: a 59-year-old woman with 30 years of Type 1 Diabetes.

**She cannot reliably feel a low.** After 30 years, her glucagon counter-regulatory response is presumed absent and her adrenergic response blunted. She can be at 50 mg/dL and feel fine. **Every unusual constraint in this spec pack exists because of that fact.**

A defect here is not a bug ticket.

## Before you write anything

Read, in this order:
1. `README.md` — read order and operating rules
2. `CLAUDE.md` — your operating manual. Agent roles, the TDD loop, safety invariants, forbidden patterns.
3. `docs/00-glossary.md` — **the domain is clinical and the terms are not guessable.** Do not skip this.
4. `docs/10-backlog.md` §BUILD ORDER — find the next story.

Then read the docs that story references.

**Precedence:** `docs/07-clinical-model-spec.md` wins on all clinical and model matters.

## How you work

Three agents, strict TDD:

- **SDET** writes the failing test **first**. Owns `tests/`. Never edits `core/`.
- **Dev** writes the minimum code to pass. Owns `core/`. **Never edits `tests/`.**
- **BA** documents, maintains the traceability matrix (REQ → story → test) and the decision log.

**Green-before-red is a process failure.** If it happens, delete the test and rewrite it from scratch.

## The rules that will feel inconvenient

They are all load-bearing. Do not work around them.

1. **`datetime.now()` must never populate a clinical timestamp.** She logs at the laptop, not at the table. Conflating log time with event time silently corrupts `bolus_offset_min` and `elapsed_min` — the two most important features — with no error and no way to detect it afterwards.

2. **Hypo-rescued meals are excluded from training but RETAINED as hypo events (INV-7).** The natural refactor — "drop invalid rows" — would silently delete every low she ever had. The model would then be trained on a world where she never goes low, and it would look fine.

3. **The bolus calculator is hard-blocked until Gate 2 (INV-1).** You will want to stub `icr = 8.3` to get its tests running. **Don't.** Test the refusal path. The gate *is* the feature.

4. **`β_insulin` is sign-constrained ≥ 0 (INV-8).** In observational data, insulin *appears* to raise glucose — because she doses more for bigger meals. That correlation is real. Inverting it into dosing advice is a hypo pathway.

5. **No ML in the dose calculation.** The clinical formula is causal. The model is not.

6. **Never work around a blocked gate.** The gates are the product.

## Escalate — do not decide these yourself

- A test cannot pass without weakening a safety invariant.
- Documents conflict.
- A clinical constant needs choosing or changing.
- **The model performs suspiciously well.** This is almost always leakage. Investigate; do not celebrate.
- `β_insulin` comes out negative in an unconstrained fit.

## Start here

**Build order is in `docs/10-backlog.md`. Begin with EPIC 1, S-101.**

Two things to internalise before you start:

**The critical path is EPIC 3, not the model.** Gate 1 needs 150 valid meals — about three months of her logging. Everything downstream can be built *while that clock runs*. **Every week spent on the ordinal model before logging is live is a week added to the end of the project.**

**S-304 (the restore drill) runs in month one, before there is real data to lose.** An untested backup is not a backup, and three months of her life does not come back.

---

Confirm you have read `CLAUDE.md` and `docs/00-glossary.md`, then state which story you are starting and which invariants it touches.
