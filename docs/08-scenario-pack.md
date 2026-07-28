# 08 — Scenario Pack

*Purpose: Gherkin scenarios. The safety scenarios are the point of this document.*
*Read before: writing tests.*

---

## Feature: Meal Logging

```gherkin
Scenario: A repeat meal is logged in four taps and two numbers
  Given "Dal + 2 roti + sabzi" is a favourite for lunch
  When she taps "Log Meal"
  And taps the favourite
  And enters BG 142
  And enters bolus 6.0
  And taps "10 min before"
  And taps "Log Meal"
  Then the meal is saved with all macros populated
  And the interaction required no more than 4 taps and 2 numbers    # REQ-001

Scenario: Bolus timing cannot be skipped
  Given she is logging a meal
  When she submits without choosing a bolus timing
  Then submission is rejected                                        # REQ-003

Scenario: A pre-bolus is stored as a negative offset
  When she taps "15 min before"
  Then bolus_offset_min is -15                                       # REQ-003
```

## Feature: Reported Timestamps ★ (ADR-8)

```gherkin
Scenario: The log time is not the meal time
  Given she ate breakfast at 08:00
  When she logs it at 09:40 and reports the mealtime as 08:00
  Then meal.datetime is 08:00
  And meal.logged_at is 09:40
  And the two values differ                                          # REQ-004, REQ-005

Scenario: elapsed_min is computed from reported times, not log times
  Given a meal reported at 08:00
  And a post-meal reading reported as taken at 10:05
  When she enters that reading at 11:30
  Then elapsed_min is 125, not 210
  And the record is VALID                                            # REQ-004

Scenario: The test-time prompt uses the reported mealtime
  Given she logs a meal at 09:40, reporting the mealtime as 08:00
  Then the prompt reads "Set an alarm for 10:00 AM"
  And not "11:40 AM"                                                 # REQ-014

Scenario: The system never fabricates a timestamp
  When she logs a meal retrospectively
  Then the system asks when she ate
  And does not default the value to now()                            # REQ-011
```

## Feature: Validity

```gherkin
Scenario Outline: The post-meal window
  Given a post-meal reading at <elapsed> minutes
  Then the record is <validity>

  Examples:
    | elapsed | validity |
    | 104     | invalid  |
    | 105     | valid    |
    | 120     | valid    |
    | 135     | valid    |
    | 136     | invalid  |

Scenario: Invalid records are kept, not discarded
  Given a reading taken at 150 minutes
  Then the record is marked invalid with reason "outside_window"
  And elapsed_min = 150 is still stored
  And the record appears in the adherence dashboard                  # REQ-022

Scenario: All applicable exclusion reasons are recorded
  Given a meal that is both rescued and outside the window
  Then exclusion_reasons contains both, not just the first
```

## Feature: ★ INV-7 — Hypo Rescue Retention [SAFETY]

> **The single most important scenario in this pack.** The natural refactor —
> *"invalid rows get dropped from training"* — would silently delete every low she
> actually experienced. The model would then be trained on a world where she never
> goes low. It would look fine. It would be calibrated on nothing.

```gherkin
Scenario: A rescued meal is excluded from outcome regression
  Given a meal where she treated a low during the window
  When the training set is assembled
  Then that meal is NOT in the training set                          # INV-7

Scenario: A rescued meal IS retained as a hypo event
  Given the same meal
  When hypo events are assembled
  Then that meal IS present, as State 1 or State 2                   # INV-7

Scenario: Regression guard — lows are never silently erased
  Given 100 meals, of which 20 were rescued
  When the training set and hypo events are assembled
  Then the training set excludes all 20
  And get_hypo_events() returns exactly 20
  # This test exists to catch a future refactor. DO NOT DELETE IT.
```

## Feature: IOB

```gherkin
Scenario: IOB decays monotonically
  Given a 6 U Fiasp bolus
  Then iob_fraction is 1.0 at t=0
  And 0.0 at t=240
  And strictly decreasing in between                                 # REQ-020

Scenario: IOB is never entered by hand
  Then no code path accepts a manually supplied IOB value            # REQ-020

Scenario: Simultaneous boluses sum
  Given two 5 U boluses at the same instant
  Then IOB equals that of a single 10 U bolus
```

## Feature: Effective Basal (Tresiba)

```gherkin
Scenario: A basal change takes days to take effect
  Given a steady 24 U daily dose
  When it changes to 30 U
  Then effective_basal one day later is strictly between 24 and 30
  And five days later is within 0.5 of 30                            # REQ-021

Scenario: Titration lockout
  Given basal changed today
  Then the next 3 days are flagged basal_titration_lockout
  And day 4 is not
  And lockout days are flagged but NOT excluded from training
```

## Feature: ★ INV-8 — Confounding by Indication [SAFETY]

```gherkin
Scenario: The model cannot learn that insulin raises glucose
  Given a dataset where bolus positively correlates with post-meal BG
  # This is realistic — she doses MORE for bigger meals and higher pre-BG
  When the constrained model is fitted
  Then β_insulin >= 0
  And a warning naming "confounding by indication" was logged        # INV-8
  # This is the single most important test in the model epic.

Scenario: Correction events beat the OLS estimate
  Given the OLS-derived ISF materially disagrees with the correction-event ISF
  Then the correction-event value is preferred
  And a flag is raised                                               # REQ-033
  # Correction events are unconfounded. The OLS fit is not.
```

## Feature: ★ Gates [SAFETY]

```gherkin
Scenario: No patient output before Gate 1
  Given 149 valid meals
  When the patient requests a prediction
  Then GATE_NOT_PASSED is returned                                   # INV-2

Scenario: Volume alone does not open Gate 1
  Given 200 valid meals
  But hypo recall is below the clinical baseline
  Then Gate 1 remains CLOSED
  # The model must EARN patient visibility. It is not granted by row count.

Scenario: The bolus calculator is blocked without a confirmed ICR
  Given icr is null
  When a bolus recommendation is requested
  Then a 422 INVALID_PROFILE error is returned                       # S-1011: not a gate

Scenario: No bypass exists
  Given icr is null
  Then no fixture, mock, config flag, or environment variable
       can produce a bolus recommendation without a usable ICR       # S-1011

Scenario: Gates are never cached
  Given a gate was evaluated as passed a moment ago
  When the underlying data no longer satisfies it
  Then the next evaluation returns CLOSED                            # ADR-7
```

## Feature: ★ Prescriptive Safety [SAFETY]

```gherkin
Scenario: Refuse to dose a low
  Given current BG is 74
  When a bolus recommendation is requested
  Then BG_TOO_LOW_FOR_BOLUS is returned
  And the message advises treating the low first                     # INV-4

Scenario: BG 80 is the boundary
  Given current BG is 80
  Then a dose is computed                                            # INV-4

Scenario: A typo cannot produce a lethal dose
  Given carbs_g is entered as 900   # she meant 90
  Then the dose is capped at 15 U
  And it is FLAGGED as implausible input
  And it is NOT silently clipped                                     # INV-3

Scenario: Never a negative dose
  Given IOB exceeds the computed requirement
  Then the recommendation is 0.0, never negative                     # INV-3

Scenario: The arithmetic is shown
  Then the response includes the carb dose, correction, and IOB deduction
  # She has done this maths by hand for 30 years. Let her check the machine.
```

## Feature: ★ Guardrails [SAFETY]

```gherkin
Scenario: Refuse when uncertain
  Given no predicted state exceeds 40% probability
  Then the system refuses: "Not confident enough to predict this one"
  And returns NO number
  # Never fill the silence with a guess.

Scenario: Refuse out of distribution
  Given a meal with more carbs than any in training
  Then the system refuses

Scenario: Baseline conflict shows both
  Given the baseline predicts State 3
  And the model predicts State 5
  Then BOTH are shown
  And the conflict is flagged
  And the system does NOT pick a winner                              # REQ-046

Scenario: Absurd prediction is a hard error
  Given the model predicts 620 mg/dL
  Then a SafetyViolation is raised                                   # INV-6
```

## Feature: ★ INV-9 — Prediction Log [SAFETY]

```gherkin
Scenario: A prediction is persisted before it is shown
  Given the persistence layer will fail
  When a prediction is requested
  Then NO prediction is returned to the caller                       # INV-9
  # Write-then-display ordering must be enforced, not incidental.
```

## Feature: Kill Switch

```gherkin
Scenario: Drift trips the switch
  Given rolling prospective performance falls below the clinical baseline
  Then ML output is suppressed
  And the baseline is shown instead
  And the operator is alerted                                        # REQ-047

Scenario: It never re-arms itself
  Given the kill switch has tripped
  When a subsequent prediction happens to be good
  Then ML output remains suppressed
  And only a manual operator action re-arms it                       # REQ-047
```

## Feature: ★ Durability

```gherkin
Scenario: The restore drill
  Given a database with test data
  When a snapshot is taken and restored into a scratch environment
  Then the restored database is byte-identical
  # ★ RUN THIS FOR REAL, IN MONTH ONE, BEFORE THERE IS DATA TO LOSE.
  # S-304 is not done until the drill has been executed.            # REQ-051

Scenario: The live DB is never in a synced folder
  Then app.db is not located inside a cloud-synced directory
  # Sync mid-write corrupts SQLite.                                  # REQ-050
```
