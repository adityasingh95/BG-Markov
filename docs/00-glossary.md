# 00 — Glossary

*Purpose: clinical and technical terminology. The domain is unfamiliar and the terms are not guessable.*
*Read before: everything.*

---

## 1. Clinical — Diabetes

| Term | Definition |
|---|---|
| **T1D** | Type 1 Diabetes. Autoimmune destruction of pancreatic beta cells. **No endogenous insulin.** All insulin is injected. Post-meal glucose is therefore fully determined by injected insulin, food, and physiology — nothing self-corrects. |
| **BG** | Blood glucose, mg/dL. Measured here by **fingerstick**, not CGM. |
| **Fingerstick** | Capillary blood sample on a glucometer strip. ISO 15197 permits ±15% error — **it is not a precise ground truth**, and near the 180 mg/dL state boundary the label itself is noisy. |
| **CGM** | Continuous Glucose Monitor. **Deliberately out of scope** (see `01-prd.md` §Non-Goals). |
| **Hypoglycaemia / hypo** | Low BG. Dangerous. Acutely so. |
| **Hyperglycaemia / hyper** | High BG. Damaging over time; DKA risk at extremes. |
| **Euglycaemia** | BG in target range. |
| **Hypoglycaemia unawareness** | Loss of the symptoms that warn of a low. After ~30 years of T1D the glucagon response is typically absent and the adrenergic response blunted. **The patient can be at 50 mg/dL and feel fine. This single fact drives the design of the entire system.** |
| **DKA** | Diabetic ketoacidosis. Life-threatening consequence of sustained insulin deficiency. |
| **Postprandial** | After a meal. |

## 2. Clinical — Insulin

| Term | Definition |
|---|---|
| **Bolus** | Fast-acting insulin taken at a meal, or to correct a high. |
| **Basal** | Long-acting background insulin. Suppresses hepatic glucose output between meals and overnight. |
| **Fiasp** | The patient's bolus insulin (faster aspart). **Peak ~55 min**, duration ~4 h. Faster than Novolog/Humalog — pre-bolus timing matters more. |
| **Tresiba** | The patient's basal insulin (degludec). **~42 h duration; steady state only after 3–4 days.** Today's dose is *not* today's effect — see `07` §3. |
| **TDD** | Total Daily Dose (basal + all boluses). Here: **~60 U**. |
| **ICR** | Insulin-to-Carb Ratio. Grams of carbohydrate covered by 1 unit. **Unconfirmed.** Expected 7–10 g/U (500-rule: 500/60 ≈ 8.3). |
| **ISF** | Insulin Sensitivity Factor / correction factor. mg/dL that 1 unit lowers BG. **Provisionally 30** (1800-rule: 1800/60 = 30). **Unconfirmed — see the warning below.** |
| **Target BG** | The BG a correction aims at. Here: **135** (midpoint of her 120–150). |
| **IOB** | Insulin on Board. Bolus insulin still active from earlier injections. **Always derived from `bolus_log`, never entered.** |
| **COB** | Carbs on Board. Not directly modelled; approximated by the 3-hour inter-meal exclusion rule. |
| **Pre-bolus** | Injecting *before* eating. Represented as a **negative** `bolus_offset_min`. |
| **Correction bolus** | Insulin to bring down a high, separate from meal coverage. Logged as a distinct field. |
| **Over-basalization** | Basal dose too high. Causes unexplained lows. Common, under-diagnosed, and **especially dangerous in hypo unawareness.** Expected basal is 40–50% of TDD (24–30 U here). Flagged for the endocrinologist. |

> ### ⚠️ Why ISF is the most dangerous constant in the system
> ISF sits in the **denominator** of the correction term: `correction = (BG − target) / ISF`.
> An ISF that is **too low causes over-dosing.**
> At BG 250, target 135: assuming ISF 30 gives 3.8 U. If her true ISF is 50, that dose drops her by 191 mg/dL — **to 59 mg/dL. A hypo.**
> This was why INV-1 hard-blocked the prescriptive module until ISF was confirmed. **INV-1 is retired** (S-1011, DL-035) — the dose path is now bounded by INV-3/INV-4 and by her review of the shown arithmetic, not by a confirmation gate.

## 3. Clinical — Nutrition & Activity

| Term | Definition |
|---|---|
| **Macronutrients** | Carbohydrate, protein, fat. All logged. |
| **Fibre** | Logged separately. `net_carbs = carbs − fibre`. |
| **IFCT 2017** | Indian Food Composition Tables (NIN Hyderabad). The macro reference for her cooking. |
| **Katori** | Standard Indian bowl. The portion unit for the dish table. |
| **Light/aerobic exercise** | Walking, cycling, yoga. Typically **lowers** BG. |
| **Intense/anaerobic exercise** | Weights, sprinting, HIIT. Can **raise** BG via adrenaline. **The effect is non-monotone in intensity** — which is why intensity is one-hot encoded, never numeric 0/1/2. |
| **Hypo rescue** | Fast carbs (glucose tablets, juice) taken to treat a low. Contaminates the meal outcome — see INV-7. |

## 4. Model & Statistics

| Term | Definition |
|---|---|
| **Glycaemic state** | The 5 discrete output bands. See `03-state-model.md`. |
| **Ordinal logistic regression** | The model. Respects state **ordering** — off-by-one is far better than off-by-three. |
| **Proportional odds** | The assumption ordinal regression makes. Tested via the **Brant test**. |
| **Multinomial logistic** | **Forbidden.** Treats the states as unordered, discarding their structure. |
| **Confounding by indication** | The central statistical hazard. Bolus is *chosen in response to* carbs and pre-meal BG, so in observational data **more insulin correlates with higher post-meal glucose.** A naive fit learns "insulin raises glucose." Inverting that into dosing advice is a hypo pathway. Hence INV-8 and the ML-free prescriptive module. |
| **Baseline model** | The clinical formula (`07` §4). The bar the ML must beat. Also the fallback when the kill switch trips. |
| **Forward-chaining CV** | Temporal cross-validation. Train on the past, test on the future. **Random splits leak** — basal is constant within a day. |
| **Calibration** | Whether a stated 20% risk occurs 20% of the time. **The whole product is a probability**, so this is the key metric. |
| **Brier score** | Proper scoring rule for probabilistic accuracy. |
| **Clarke / Parkes error grid** | Field-standard glucose-prediction evaluation. Weights errors by **clinical danger**, not magnitude. |
| **Hypo recall @ fixed FAR** | **The primary metric.** Of all the lows that actually happened, how many did the model warn about — at an acceptable false-alarm rate. |
| **Shadow mode** | The model predicts; predictions are logged and compared to actuals; **nothing is shown to the patient.** Minimum 90 days. |

## 5. System

| Term | Definition |
|---|---|
| **"Markov" (the name)** | **A codename, not a description of the model.** The project began from a Markov-chain design document (DL-038) and kept its name. The model is a **single ordinal logistic regression**; there is **no transition matrix and no memorylessness assumption** — IOB and prior meals mean the past demonstrably does not wash out. The only genuine Markov chain is MCMC *sampling* inside the optional Bayesian fit, which is a numerical technique, not a model of glucose. Revisit: OQ-8 / backlog §R-1. |
| **Gate 0 / 1 / 2** | Progressive unlocks. See `03-state-model.md` §3. **Gate 2 was retired** by S-1011 (DL-035); Gates 0 and 1 remain. |
| **Promotion** | The operator's explicit, audited action opening Gate 1 (`model_artifact.is_promoted`). **Code never promotes** — good metrics are a precondition, not permission. |
| **Shadow clock / shadow days** | Days since the first logged shadow prediction. A Gate 1 precondition (**≥ 90**, REQ-048). Computed from `prediction_log`, never a stored flag. |
| **Report card** | The operator's shadow view: each metric shown as **value + plain-language meaning + technical term together**, so a non-statistician and a clinician can both read it. |
| **Synthetic data** | Seeded, generated records for tests and demos. **Never imported by production code and never presented as her data** (REQ-056). |
| **INV-n** | Safety invariant. `core/safety.py`. See `CLAUDE.md`. |
| **`datetime` vs `logged_at`** | `datetime` = when the event **happened** (reported by her). `logged_at` = system clock at submission. **Conflating them corrupts the model.** |
| **`elapsed_min`** | Reported minutes between meal and post-meal reading. Valid window: **105–135**. |
| **`bolus_offset_min`** | Signed minutes between bolus and first bite. **Negative = pre-bolus.** |
| **Kill switch** | Automatic suppression of ML output on performance degradation. **Re-arming is manual, always.** |
| **Operator** | Her son. Developer, reviewer of shadow-mode output, and able to log on her behalf. |
