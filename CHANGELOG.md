# Changelog

Version gates for BG-Markov. Each released version is an **annotated git tag** and a
known-good, CI-green state — a deliberate rollback target.

> **Why this file exists.** This system is used by one real person who cannot reliably feel a
> low. Before changing a working build we mark the working build, so returning to it is one
> command and not an archaeology exercise.

---

## [Unreleased] — 1.1.0.dev0 — EPIC 10 (Integration, UI & End-to-End Validation)

In progress. See `docs/10-backlog.md` EPIC 10 (S-1001…S-1011) and DL-033/034/035.
Nothing in EPIC 10 has shipped yet at the time of this entry.

**Rollback target for all EPIC 10 work: `v1.0.0-epic9`.**

---

## [1.0.0-epic9] — 2026-07-18

**The complete build, EPICs 1–9.** Tagged `v1.0.0-epic9`.

The last state before EPIC 10 (UI render layer, synthetic data, end-to-end tests, and the
planned Gate-2 retirement) begins. Product code here is identical to commit `4bf5289`
(*"docs(S-901): traceability … EPIC 9 complete, build finished"*); the commits between that
and this tag are documentation and the demo script only — no `core/`, `models/`, `features/`,
`prescribe/`, `data/`, `api/`, or `cli/` change.

### What works at this tag
- **EPIC 1 — Foundation.** Config loader, the nine safety invariants in `core/safety.py`,
  the forbidden-pattern test suite.
- **EPIC 2 — Data layer.** Schema + migrations, **reported timestamps** (ADR-8: `datetime`
  reported, `logged_at` separate), validity engine with **INV-7**, dish table.
- **EPIC 3 — Logging & durability.** Meal form (≤4 taps + 2 numbers), required signed bolus
  timing, post-meal reading, backup + **an executed restore drill**, hypo-rescue capture,
  correction events, operator adherence dashboard.
- **EPIC 4 — Derived features.** IOB (Fiasp exponential, always derived — never entered),
  effective basal (Tresiba EWMA, 25 h halflife), exercise one-hot + duration interactions,
  the feature pipeline.
- **EPIC 5 — Baseline & parameters.** The clinical baseline model (*the bar to beat*), ISF
  from correction events, sign-constrained ICR/ISF fit (**INV-8**).
- **EPIC 6 — The model.** One proportional-odds ordinal logit (`pre_bg` continuous, L2, hypo
  up-weighted), Brant test, Bayesian ordinal with an INV-8 sign-constrained prior.
- **EPIC 7 — Validation.** Forward-chaining temporal CV (no random split), the metric suite
  (**hypo recall @ fixed FAR is primary; plain accuracy is never reported**), gate enforcement.
- **EPIC 8 — Guardrails & output.** Output guardrails, prediction log (**INV-9**: persisted
  before returned), kill switch (manual re-arm only), patient risk readout (**INV-2**),
  shadow-mode report.
- **EPIC 9 — Prescriptive.** The bolus calculator: the clinical formula only, **no ML in the
  dose path**, behind Gate 2 (**INV-1**), refusing below BG 80 (**INV-4**), capping **and
  flagging** an implausible input (**INV-3**).

### Safety invariants live at this tag
INV-1…INV-9, each one named function in `core/safety.py`, raising `SafetyViolation` (never
`assert`), with positive **and** negative tests, and no fixture/mock/flag/env bypass.

### Verification
445 tests passing · ~99.7% coverage on gated packages · `ruff` clean · `mypy --strict` clean ·
all forbidden-pattern guards green · CI green (run #55).

### Known state, deliberately
- **Both gates are closed to the patient by design.** Gate 1 (patient-visible model output)
  needs ≥150 valid meals **and** the model beating baseline on hypo recall. Gate 2 is open
  (clinician-confirmed ICR 9 g/U, ISF 30, target 135 — DL-032).
- **Gate 1 currently opens automatically** once its metric conditions hold;
  `model_artifact.is_promoted` ("manual only") exists but is read nowhere, and REQ-048's
  ≥90-day shadow period is not enforced. Both are known gaps, storied as S-1006/S-1007
  (DL-034) — **not fixed at this tag.**
- No live per-meal prediction wiring; the model/prescriptive surfaces return data structures
  with no HTML render layer (deferred by design, S-804/S-805).

---

## How to roll back

```bash
# inspect the baseline
git show v1.0.0-epic9

# return a working tree to it (detached)
git checkout v1.0.0-epic9
./scripts/verify.sh          # should be green

# start a fix branch from the baseline
git checkout -b fix/from-epic9 v1.0.0-epic9

# discard EPIC 10 work on the current branch entirely (destructive — be sure)
git reset --hard v1.0.0-epic9
```

Tags are immutable markers: nothing done after `v1.0.0-epic9` can alter what that tag points
to. Verify any rollback with `./scripts/verify.sh` before trusting it.
