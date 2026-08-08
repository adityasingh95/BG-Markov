# 07 — Clinical & Model Specification

*Purpose: the domain core. IOB, basal, features, baseline, ICR/ISF derivation, the model, validation, guardrails.*
*Read before: `models/`, `features/`, `prescribe/`.*

> **⚠ This document takes precedence over every other doc on clinical and model matters.** If another document appears to contradict it, stop and escalate.
>
> **Research mode (`00a`).** `00a` decides what *blocks*; this document still
> decides what is *true* about the clinical model. Nothing in §2–§12 is relaxed.
> The only change is §1: the constants are **declared** rather than pending
> clinical confirmation.

---

## 1. Clinical Constants

**Declared research parameters** (`00a §4`). Chosen to be internally consistent
and clinically plausible, with stated provenance. **Declared is not confirmed** —
these are inputs to an experiment, and no result produced with them is a
statement about any real person's insulin requirements.

| Constant | Value | Source | Status |
|---|---|---|---|
| `ISF` | **30** mg/dL/U | 1800-rule: 1800/60 = 30 | **Declared** (`isf_source = declared`). Was OQ-2. |
| `ICR` | **8.3** g/U | 500-rule: 500/60 ≈ 8.3 | **Declared.** Was OQ-1, was blocking Gate 2. |
| `target_bg` | **135** | Midpoint of 120–150 | Declared |
| `TDD` | ~60 U | Subject definition | Declared |
| `iob_tp` | **55** min | Fiasp peak | Confirmed (pharmacology) |
| `iob_td` | **240** min | Operator decision | Confirmed |
| `basal_halflife` | **25** h | Degludec EWMA | Confirmed (pharmacology) |
| `MAX_BOLUS_U` | **15** U | INV-3 ceiling | Confirmed. **The config ceiling equals this value** — a config permitted to exceed the invariant is a defect. |

`iob_tp`, `iob_td` and `basal_halflife` are pharmacological properties of Fiasp
and degludec, not properties of the subject. They were never open questions and
are unaffected.

> **§6 (ISF from correction events) is now a result, not a gate.** It used to be
> a route to unblocking Gate 2. It is now a direct test of the method: **does the
> derivation recover the ISF the generator was configured with?** That is more
> informative than the gate it replaced. Keep the ≥5-event threshold, the
> `iob_at_start < 0.5` filter, the `food_in_window` filter, and the
> raise-on-non-positive rule — all of them are what is being evaluated.

### ⚠ Why ISF is the most dangerous number in the system

ISF sits in the **denominator** of the correction term:

```
correction_units = (current_bg − target_bg) / ISF
```

**An ISF that is too low causes OVER-dosing.** At BG 250, target 135:

| Assumed ISF | Dose | Actual drop if true ISF = 50 | Result |
|---|---|---|---|
| **30** (ours) | 3.8 U | 191 mg/dL | **59 mg/dL — HYPO** |
| 50 (true) | 2.3 U | 115 mg/dL | 135 — correct |

An ISF that is *too high* merely under-corrects, which is recoverable. **The error is asymmetric, and our default sits on the dangerous side if wrong.**

ISF 30 is internally consistent with a 60 U TDD, so the catastrophic case is unlikely — **but the 1800-rule is a population heuristic and individual ISF varies widely around it.** This is why INV-1 hard-blocked the prescriptive module. **INV-1 is retired in research mode** (`00a §3.1`), but correction events (§6) remain the highest-priority data the system collects — they are now the direct test of H-3 rather than a route to unblocking a gate.

---

## 2. Insulin on Board — Fiasp

**Always derived from `bolus_log`. Never entered. There is no code path that accepts a manual IOB.**

```python
import math

def iob_fraction(t_min: float, tp: float = 55.0, td: float = 240.0) -> float:
    """Fraction of a bolus still active t minutes after injection."""
    if t_min <= 0:
        return 1.0
    if t_min >= td:
        return 0.0
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * math.exp(-td / tau))
    return 1 - S * (1 - a) * (
        (t_min**2 / (tau * td * (1 - a)) - t_min / tau - 1) * math.exp(-t_min / tau) + 1
    )

def iob_at(ts, bolus_log, tp=55.0, td=240.0) -> float:
    return sum(
        b.units * iob_fraction((ts - b.datetime).total_seconds() / 60.0, tp, td)
        for b in bolus_log
        if 0 < (ts - b.datetime).total_seconds() / 60.0 < td
    )
```

**Core property: `iob_fraction` is monotonically decreasing on (0, td).** This is the property-based test (S-401).

Linear decay (`units × max(0, 1 − t/td)`) is kept behind a config flag for comparison only.

**Fiasp is faster than Novolog** (tp 55 vs 75). Consequence: **pre-bolus timing matters more, not less.** `bolus_offset_min` is doing heavy lifting.

---

## 3. Effective Basal — Tresiba

**Degludec has ~42 h duration and reaches steady state only after 3–4 days. Today's dose is NOT today's effect.**

```python
effective_basal = basal_series.ewm(halflife="25h", times=timestamps).mean()
```

**Titration lockout:** after any basal dose change, the basal coefficient is uninterpretable for 3 days. Flag those days. **Suppress any basal-related guidance during the lockout.**

Upside: Tresiba is flat and peakless, so within a 2-hour post-meal window it contributes an essentially constant background. It does not confound meal transitions the way NPH would.

---

## 4. The Baseline Model — BUILD THIS FIRST

```
predicted_post_bg = pre_bg
                  + (carbs_g / ICR) × ISF
                  − meal_bolus_units × ISF
                  − correction_bolus_units × ISF
                  − iob_at_meal × ISF
```

Bin into the 5 states. Score with the **full §8 metric suite**.

**This is the bar the ML must beat.** It is also:
- the **fallback** when the kill switch trips,
- the **conflict check** in guardrail 4,
- the **ICR/ISF estimator** (§7).

**If the ordinal model cannot beat it, that is a real and useful finding** — carbs and insulin explain nearly everything, the extra features aren't earning their keep, and the baseline ships alone. That is a success, not a failure.

**Build it before writing a line of ML. It takes an afternoon.**

---

## 5. Features

```
pre_bg                      ← CONTINUOUS. Never binned as an input.
carbs_g, net_carbs_g, protein_g, fat_g, fiber_g
meal_bolus_units, correction_bolus_units
bolus_offset_min            ← SIGNED
iob_at_meal                 ← derived
effective_basal             ← EWMA
minutes_since_last_bolus
meal_type_lunch, meal_type_dinner        (breakfast = baseline)
ex_light, ex_intense, ex_duration_min, ex_offset_min
ex_light_x_duration, ex_intense_x_duration
pre_ex_light, pre_ex_intense, pre_ex_duration_min
```

- Continuous features standardised via `StandardScaler` **inside a `Pipeline`** (fit on training folds only — no leakage into scaler statistics).
- `macro_confidence / 100` passed as **`sample_weight`**.

### Exercise encoding — why one-hot is mandatory

Light exercise **lowers** BG. Intense exercise can **raise** it (adrenaline). **The effect is non-monotone in intensity.**

A numeric `0/1/2` column in a linear model **mathematically forbids** a non-monotone effect. One-hot + duration interactions permits it. This is not a style preference; a numeric encoding cannot represent the physiology.

---

## 6. ISF from Correction Events — the clean signal

Standalone corrections with **no food** are the only causally unconfounded data the system collects.

```
derived_ISF = mean( (bg_before − bg_after) / units )
              over events with iob_at_start < 0.5 AND food_in_window == False
```

- **Requires ≥ 5 valid events** before it may override the default.
- **Never silently swaps.** Report both the current and derived value to the operator.
- Derived ISF ≤ 0 → **raise**, do not apply.

---

## 7. ★ Confounding by Indication — the central hazard

**Bolus is CHOSEN IN RESPONSE TO carbs and pre-meal BG.** Bigger meals and higher pre-BG get bigger boluses.

So in observational data, **higher insulin correlates with higher post-meal glucose.** A naive fit learns a **positive** coefficient on bolus — that insulin *raises* glucose.

**The correlation is real. The data is not lying. And inverting it into dosing advice is a hypo pathway.**

### Three defences

**1. INV-8 — sign constraint.** `β_insulin ≥ 0` in every fit.

```
post_bg = pre_bg + β_carb · carbs_g − β_ins · total_bolus + intercept
subject to β_carb ≥ 0, β_ins ≥ 0
```
- `ISF = β_ins`, `ICR = ISF / β_carb`
- **If the UNCONSTRAINED fit wants `β_ins < 0`, log a prominent warning naming confounding-by-indication, then apply the constraint.** Do not accept the negative coefficient.
- Cross-check against correction-event ISF (§6). **On material disagreement, trust the correction events** — they are unconfounded — and raise a flag.

**2. ADR-10 — no ML in the dose calculation.** The prescriptive module is the clinical formula, which is **causal by construction**. The ML never touches a dose.

**3. Bayesian priors** (§9, at n≥200) encode the sign constraint natively.

> **A future enhancement** is to replace raw bolus with the **residual** — `bolus − expected_bolus(carbs, pre_bg)` — which has a causal interpretation. Deferred by operator decision; the three defences above stand in for it.

---

## 8. The Model

**Ordinal logistic regression, proportional odds. ONE model. `pre_bg` continuous.**

```python
from statsmodels.miscmodels.ordinal_model import OrderedModel
res = OrderedModel(y_state, X, distr="logit").fit(method="lbfgs", maxiter=2000)
```

**Ordinal, because the states are ordered.** Off-by-one is a minor error; off-by-three is catastrophic. **Multinomial logistic cannot tell those apart.**

### Escalation path
1. **Brant test** for proportional odds after every fit.
2. If it fails — plausible, since exercise may act non-monotonically across thresholds — **partial proportional odds.**
3. **At n ≥ 200: Bayesian ordinal** (PyMC/Bambi), weakly informative priors. At single-patient sample sizes this is the honest choice: credible intervals instead of false precision, and priors **encode INV-8 natively as a sign constraint.**

### Class imbalance
States 1, 2, 5 are rare **and are the ones that matter.** Up-weight the hypo states. Combine multiplicatively with `macro_confidence` weights.

### Forbidden
`LogisticRegression(multi_class='multinomial')` — removed in sklearn ≥1.7, and the wrong model class regardless. Per-state sub-models. Binning `pre_bg` as an input.

---

## 9. Validation

### Splitting
**Forward-chaining temporal CV. NEVER random.** Basal is constant within a day and days are autocorrelated — **a random split leaks day-level information into test.** No `date` may appear in both train and test in any fold.

### Metrics

| Metric | Role |
|---|---|
| **Hypo recall @ fixed FAR** | **PRIMARY.** She cannot feel a low. This is why the system exists. |
| **Calibration (reliability diagram)** | The entire product is a probability. If it says 20%, it must happen 20% of the time. |
| Brier score | Probabilistic accuracy |
| MAE (mg/dL) | On the continuous baseline |
| **Clarke / Parkes error grid** | Field standard. **Weights errors by clinical danger**, not magnitude. |
| Off-by-one-state rate | Ordinal-aware accuracy |

**Plain accuracy is NOT a reported metric.** On an imbalanced 5-class problem it is close to meaningless — predicting "State 3" every time would score ~65%.

### Retraining
Insulin resistance is present (TDD 60 U), so sensitivity drifts. **Monthly refit**, trailing 6 months, older data down-weighted. Promotion is manual, on hypo recall.

---

## 10. Output Guardrails

**Refuse to predict if ANY fire. A refusal is a valid, correct output.**

| # | Condition | Response |
|---|---|---|
| 1 | **Out of distribution** — carbs/bolus/pre_bg outside training range | Refuse |
| 2 | **Sparse region** — < ~10 training meals nearby | Refuse |
| 3 | **Diffuse posterior** — no state exceeds 40% | "Not confident enough to predict this" |
| 4 | **Baseline conflict** — baseline and model > 1 state apart | **Show BOTH. Flag it. Do NOT pick a winner.** |
| 5 | **Physiologically absurd** — predicted BG outside [20, 600] | **Hard error** (INV-6) |

**Never fill the silence with a number.** A guess is worse than a refusal, and infinitely more dangerous to someone who cannot feel a low.

---

## 11. Prescriptive Module — NO ML

```python
def recommend_bolus(carbs_g, current_bg, icr, isf, target_bg, iob):
    carb_dose  = carbs_g / icr
    correction = (current_bg - target_bg) / isf
    raw        = carb_dose + correction - iob
    capped     = min(raw, MAX_BOLUS_U)          # INV-3 — 15 U
    return max(0.0, capped), raw > MAX_BOLUS_U  # (dose, capped_flag)
```

**This is the standard clinical formula. It is causal by construction. No model
output enters this path.** The cap is shown in the code because it is an
invariant, not a presentation detail — a reference implementation that omits it
ships INV-3 half-built.

> **The output is a number in a study, not a dose.** Research mode retires the
> gate in front of this function; it does not turn the function into a dosing
> tool. Every surface rendering its output carries the non-clinical-use banner
> (REQ-058).

| Guardrail | |
|---|---|
| ~~**INV-1**~~ | **RETIRED** (`00a §3.1`) — ICR is declared, so there is no clinical gate. INV-3 and INV-4 below are **unchanged and under test**. |
| **INV-4** | Refuse below BG 80 → "Treat the low first." |
| **INV-3** | Cap at 15 U. **A cap event is FLAGGED as implausible input, never silently clipped.** A typo must not produce a lethal dose. |
| **INV-3** | Never negative. |
| — | **Show the full arithmetic.** She has done this maths by hand for 30 years. |
| — | Framed as a **suggestion for review**, never an instruction. |

---

## 12. Known Limitations — State These, Do Not Hide Them

| Limitation | Consequence |
|---|---|
| **The 2-hour endpoint misses late lows.** Fiasp acts for ~4 h; a perfect 2 h reading can precede a hypo at 3.5 h. | **The model does not predict late lows and must never be trusted to.** |
| **High-fat/protein meals peak at 4–6 h** — outside the window entirely. | Fat and protein coefficients are weakly identified. |
| **Self-reported carbs carry 20–50% error.** | This **caps achievable accuracy** regardless of model. `macro_confidence` measures it; nothing fixes it. |
| **Fingersticks carry ±15% error**, and the state boundaries sit inside that noise. | The labels themselves are uncertain near 180. |
| **No CGM** → no pre-meal trend, no 3–5 h tail. | Accepted (`01-prd.md` §7). |
| **Laptop-only** → restaurant meals lost or recalled. | **A known bias in the training distribution.** |
| **n ≈ 150.** | Probabilities are estimates with real uncertainty. **Show it. Never hide it.** |
