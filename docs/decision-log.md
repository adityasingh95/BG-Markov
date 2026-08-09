# Decision Log

*Owner: BA. Every deviation from spec, with rationale and who approved it.*

**Reading this log:** every entry below is either an operator ruling or a
correction the pack's own precedence forced. Entries that were applied on
recommendation and later confirmed say so. Each still names its reversal.

---

## DL-001 — ★ Research mode: this build is not for clinical use
**Type:** scope change · **Approved by:** operator, explicitly · **Affects:** everything

The operator stated that the system is being built to **verify a theory**, not to
predict for or prescribe to any person, and that nothing should wait on clinical
input. `docs/00a-research-mode.md` was written to record this and now takes
precedence on scope and gating.

**The change was applied along one specific seam.** The pack's guardrails are of
two kinds and they were **not** relaxed together:

- **Clinical-authorization gates — retired.** INV-1, INV-2, INV-5, Gate 2's
  clinical block, the 90-day shadow clock, OQ-1..OQ-7. These existed to stop an
  unvalidated system reaching a person who could be harmed by it. With no such
  person they gate nothing.
- **Validity guardrails — kept, and load-bearing.** INV-3, 4, 6, 7, 8, 9; the
  leakage suite; forward-chaining CV; ADR-6/7/8/10; the forbidden-pattern tests;
  hypo recall as primary metric.

**Rationale for the seam.** The second set has nothing to do with clinical
approval — it is what makes a result *true*. Removing INV-7 trains the model on a
world with no lows and then scores hypo recall against a dataset containing none:
an excellent-looking number that means nothing. Removing the leakage suite
produces a model that looks brilliant and is useless. **A theory verified with
those removed is not verified**, so relaxing them would defeat the stated purpose
rather than serve it.

**INV and REQ numbering is unchanged.** Retired items keep their IDs, marked
RETIRED, so cross-references resolve and the retirement stays visible instead of
vanishing under a later refactor.

**Reversal path (`00a §8`).** Restoring clinical use is not a flag. It requires
reinstating INV-1/2/5, restoring the gates and the shadow clock, and answering
OQ-1..OQ-7 with an actual endocrinologist.

## DL-002 — Build order inverted; the model is now the bottleneck
**Type:** scope change · **Follows from:** DL-001

The original order shipped EPIC 3 (logging) first because three months of a real
person's adherence stood between EPIC 1 and any result. **That clock does not
exist**, so the justification is void. EPIC 3 splits: **3a (generator +
durability)** moves onto the critical path, **3b (logging UI)** goes last and may
never be built. EPIC 10 (Results) is added — without it the build produces
artefacts and no conclusions.

## DL-003 — Data source: synthetic generator with known ground truth
**Type:** scope decision · **Follows from:** DL-001 · **Assumption — flagged**

No real subject means no real data. A **generator with declared ground-truth
parameters** was chosen over a public dataset because it makes the central
questions measurable rather than arguable: true ICR, ISF and β values are inputs,
so parameter recovery has an error bar (H-3); confounding can be dialled in
deliberately, producing exactly the dataset in which naive OLS concludes insulin
raises glucose (H-2); and lows occur at a known rate, so hypo recall has a
trustworthy denominator.

**REQ-055 is the price.** The generator must be unreachable from `core/`,
`features/`, `models/` and `prescribe/`, enforced by test (S-310). A model that
can read the answer key proves nothing, and the usual way that happens is a
shared config object, by accident.

**Open risk RQ-1:** a generator too clean to be a real test. The easy generator
to write emits well-dosed unconfounded meals and flatters the model.

## DL-004 — Gates may close, not only advance
**Type:** contradiction resolution · **Approved by:** operator · **Conflict:** `03 §3` vs. ADR-7 and `08`

`03 §3` said *"gates only ever advance"*; ADR-7 (marked irreversible) and `08`'s
"Gates are never cached" scenario said a live re-evaluation returns CLOSED when
its condition stops holding. Both could not be true.

**Resolved toward closure, with the kill-switch fallback**: gates are recomputed
live and close when falsified, but **a closing gate suppresses ML output and
leaves the clinical baseline visible** rather than blanking the surface. This
honours ADR-7, which is marked non-reversible, and reuses the fallback path §4
already requires.

**Consequence, accepted:** a result's gate label can change under it after a
refit. **S-1003 therefore stamps the gate state onto each recorded run** rather
than reading it live — a number quoted as Gate 1 must stay quotable as Gate 1.

**Reversal:** restore "gates latch open" in `03 §3` and delete the `08` scenario.
Defensible if stability of results between refits ever matters more than ADR-7.

## DL-005 — `max_bolus_u` config ceiling lowered from 25 to 15
**Type:** contradiction resolution · **Conflict:** S-103 AC vs. INV-3

INV-3, REQ-042, `07 §11`, `05 §5`, `08` and `05b §6` all specify 15 U. Only
S-103's AC permitted `max_bolus_u` up to 25 — allowing a config of 20 U, above
the invariant. **A config ceiling above a safety invariant is a defect in the
unsafe direction**, and the pack's own precedence resolves it: the ceiling is now
15. Not treated as a judgement call.

## DL-006 — `elapsed_min` stays out of the feature vector
**Type:** contradiction resolution · **Approved by:** operator · **Conflict:** `04 §5` escape hatch vs. `09 §7`

`09 §7` requires a test that `elapsed_min` never enters the feature vector;
`04 §5` said to add it as a feature if too many meals fall outside the window.

**Resolved in favour of the leakage guard, on a factual ground rather than a
preference:** predictions are made *before* the meal, when `elapsed_min` does not
yet exist. It can never be a legitimate prediction-time feature. **The widening
half of the escape hatch survives** — the ±15 window may become ±30 if the data
demands it; the add-a-feature half does not.

**Reversal:** narrow the `09 §7` leakage test to `post_bg` only, and require a
fixed assumed value (e.g. 120) at inference.

## DL-007 — Dose components are not rounded before summing
**Type:** ambiguity resolution · **Source:** `05 §5` / `05b §6` worked example

The published example shows `7.2 + 1.8 − 1.1 = 7.9`, but the exact arithmetic is
`7.229 + 1.833 − 1.1 = 7.96`, which rounds to 8.0. Rounding components then
summing, versus summing then rounding, give different answers — and S-901 demands
golden doses exact to 2 dp.

**Resolved: compute exact, round only for display.** The tests assert the exact
total.

**Not resolved, and deliberately out of scope:** insulin pens deliver in 0.5 or
1 U increments, so 7.96 U is not physically deliverable. No document in the pack
addresses dose granularity. In a research build this is harmless — the number is
never injected — **but it must be settled before any clinical use**, and rounding
a dose upward is the unsafe direction. Recorded here so it is not lost.

## DL-008 — Rescued meals must record the pre-rescue BG
**Type:** data-model gap · **Affects:** INV-7, S-309

`meal_event` carries `hypo_treatment` and `hypo_treatment_g` but **no field for
the BG that triggered the rescue and no rescue timestamp.** `post_bg` is measured
after the carbs, so it may read 120. `04 §5` requires `get_hypo_events()` to
return rescued meals "as State 1 or State 2" — but nothing in the schema says
from what value.

**As specified, INV-7 preserves the fact of a low and loses its magnitude and
timing.** S-309 adds `hypo_bg` and `hypo_treatment_time`. Without them the hypo
events are unlabelled and hypo recall has no trustworthy denominator.

## DL-009 — `β_ins == 0` raises rather than dividing
**Type:** spec gap · **Affects:** INV-8, S-503

INV-8 constrains `β_ins ≥ 0`, which permits exactly 0. `07 §7` then computes
`ICR = ISF / β_carb` with `ISF = β_ins`, giving `ICR = 0` and a division by zero
downstream in both the baseline and the calculator. `07 §6` guards
`derived_ISF ≤ 0` for the correction-event path but there is no equivalent guard
on the OLS path, where the constraint can land exactly on the boundary.

**Resolved: `β_ins == 0` raises and is reported as a distinct outcome** — it means
the data carries no insulin signal at all, which is a finding, not a number to
propagate.

## DL-010 — INV-2 / no-auth conflict dissolved, not resolved
**Type:** contradiction closed by DL-001

`05 §4` gated patient output while ADR-9 shipped no auth and `06 §7` called
`logged_by` "a toggle, not auth" — so the patient could select "operator" and see
ungated output. INV-2 rested on a client-side toggle.

**DL-001 retires INV-2 and removes the patient surface, so the conflict no longer
exists.** Recorded because it does not stay resolved: **restoring a patient
surface reinstates this defect**, and `00a §8` must be read alongside it.

## DL-011 — `correction_event.bg_after` must be nullable
**Type:** data-model defect · **Conflict:** `04 §6` vs. `05 §3`

`04 §6` declares `bg_after` and `bg_after_time` NOT NULL, but `05 §3` populates
them four hours later via `PATCH /followup`. The row cannot be inserted at
creation time as specified. **Both columns become nullable**, with
`is_valid_for_isf` false until they are filled.

## DL-012 — `macro_confidence < 50` is currently unreachable
**Type:** spec gap · **No change applied**

Only 95 (dish table) and 60 (free text) are ever assigned, so the
`low_confidence` exclusion rule at `< 50` can never fire. Either the rule is dead
or a third confidence tier is missing. **Left as specified and flagged** — in a
synthetic build the generator controls this value directly, so S-308 can emit
low-confidence rows deliberately and the rule becomes testable rather than dead.

## DL-013 — `pre_bg_time` has no specified source
**Type:** spec gap · **Affects:** ADR-8, REQ-001

`pre_bg_time` is NOT NULL and required to be reported, but appears nowhere in the
F-1 flow or the `05b §3` mock, and the ≤4-taps + 2-numbers budget has no room for
it. **This is exactly where an implementation reaches for `now()`** — the
forbidden pattern the pack cares most about.

**No resolution applied**, because it belongs to EPIC 3b which is deprioritised.
**S-308 must emit `pre_bg_time` explicitly** so the field is exercised, and the
S-105 AST test must cover it. Flagged for whenever 3b is built.
