# 05b — UI/UX Specification

*Purpose: accessibility, logging ergonomics, risk-readout language.*
*Read before: building `api/templates/`.*

Jinja2 + HTMX + Pico.css. No build step. No React.

---

## 1. The Two Users

| | Patient | Operator |
|---|---|---|
| Age / context | 59, on a phone browser, sometimes at BG 55 | Developer, at the laptop |
| Priority | **Speed and forgiveness** | Density and diagnostics |
| Sees model output | **Only after Gate 1** | Always, labelled shadow mode |

---

## 2. Accessibility — Non-Negotiable

She may be logging **while cognitively impaired by a low.** Design for that case, not the good case.

| Requirement | Value |
|---|---|
| Base font | **≥ 18px** |
| Touch targets | **≥ 48 × 48 px** |
| Contrast | WCAG AA minimum |
| Numeric fields | `inputmode="numeric"` — **every BG and dose field** |
| Colour | **Never the sole signal.** A hypo warning must be legible without colour vision. |
| Dish selection | **No dropdowns.** Search + recents. |
| Destructive actions | Confirmable. Nothing irreversible in one tap. |
| Zoom | Usable at 200% |

**Test at 200% zoom and with a screen reader.** Not optional (S-102).

---

## 3. The Logging Flow — REQ-001

> **A repeat meal: ≤4 taps + 2 numbers. This is a *tested* requirement (S-301), not an aspiration.**

She eats from a repertoire of 30–60 dishes. **Most meals are repeats.** The favourites row is not polish — **it is the adherence mechanism.** If logging takes 90 seconds she stops in three weeks and the project ends with 40 records.

```
┌──────────────────────────────────────┐
│ [Breakfast][Lunch][Dinner][Snack]    │  ← meal type; snack is first-class
│  Lunch                    1:15 PM ✎  │  ← auto from clock, editable
├──────────────────────────────────────┤
│  ⭐ SAME AS USUAL                     │  ← tap 1. Populates all macros.
│  ⭐ Dal + 2 roti + sabzi              │
│  ⭐ Rice + rajma                      │
│  🔍 Search…                           │
├──────────────────────────────────────┤
│  BG before        [   142  ]         │  ← number 1
│  Bolus            [   6.0  ] U       │  ← number 2
│  Timing   [15 before][10 before]     │  ← tap 2 — CANNOT BE SKIPPED
│           [just before][with food]   │
├──────────────────────────────────────┤
│  ▸ Exercise, notes  (optional)       │  ← collapsed. Never blocks.
├──────────────────────────────────────┤
│           [    LOG MEAL    ]         │  ← tap 3
└──────────────────────────────────────┘
```

**Rules:**
- Optional fields are **collapsed** and never block submission.
- Draft auto-saves to `localStorage` on every change. **A failed submit never loses input.**
- **Time is editable and never silently accepted.** If she logs at 13:50 for a 13:15 meal, she must be able to say so — and the field must be visible enough that she notices when it's wrong.
- **Meal type includes `snack`** (already a valid `MealType`). A snack is logged the same way as any meal — it raises glucose the same way.

### 3.2 Dish selection, quantities & macros — REQ-009

The favourites row handles the common case; this is the rest. Tapping a dish **adds a line item**;
macros total live. Nothing here is typed by hand unless the dish is genuinely unknown.

```
┌──────────────────────────────────────────────────┐
│  🫓 Roti 15g/roti   🥣 Dal 20g/katori   🍚 Rice…  │  ← tap to add
│  [ Something not listed?…            ] [ Add ]   │
├──────────────────────────────────────────────────┤
│  Rice     2 × katori    [−] 2 [+]      90 g   ×  │
│  Dal      1 × katori    [−] 1 [+]      20 g   ×  │
├──────────────────────────────────────────────────┤
│  Carbs 110 g │ Net 106 g │ Fibre 4 g │ P·F 22·9  │
│  ✓ All from the food table — 95% macro confidence │
└──────────────────────────────────────────────────┘
```

**Rules:**
- **Portion scaling is exact** — `2 × roti` is exactly double `1 × roti` (S-204, tested).
- **Net carbs = carbs − fibre**, floored at 0. Shown next to carbs, because fibre is why a
  high-carb meal sometimes behaves like a smaller one.
- **Macro confidence is visible, never hidden.** A table hit is **95%**; free text is **60%** and
  is **queued for operator review** — the badge must say so. Confidence feeds `sample_weight`,
  so a silently-wrong confidence quietly corrupts the model's weighting.
- **Search is required, not optional polish.** Her repertoire is 30–60 dishes; the seed table is
  a starting point, not the repertoire. A dish she cannot find in two taps is a dish she stops
  logging (see the adherence argument above).

### 3.1 Confirmation — REQ-014

```
┌──────────────────────────────────────┐
│  ✓ Logged.                           │
│                                      │
│     Set a phone alarm for            │
│         ┌──────────┐                 │
│         │  3:15 PM │                 │
│         └──────────┘                 │
│         to test your BG              │
└──────────────────────────────────────┘
```

**`3:15 PM` = reported mealtime + 120 min. Never `logged_at + 120`.**

This replaces the deferred reminder system. Her phone's alarm does the work.

---

## 4. Post-Meal Reading — REQ-010

**Target: <15 seconds.** One number, one time, done.

```
┌──────────────────────────────────────┐
│  Lunch — 1:15 PM                     │
│                                      │
│  BG now           [   168  ]         │
│  Taken at         [ 3:20 PM ] ✎      │  ← REPORTED. Editable. Never assumed.
│                                      │
│  ▸ Did you treat a low?  (optional)  │
│                                      │
│           [     SAVE     ]           │
└──────────────────────────────────────┘
```

Feedback is **non-judgemental**:
- In window → `✓ Logged`
- Outside window → `✓ Logged — a bit late, that's fine`

**Never** "this record is invalid" or anything that reads as a scolding. She is doing you a favour by logging at all. Records outside the window are still stored and still useful for diagnostics.

---

## 5. Risk Readout (post Gate 1) — F-4

### 5.1 Hypo risk is the headline

She cannot feel a low. **The low is the point.** Do not bury it under a "time in range" number.

```
┌──────────────────────────────────────┐
│  In 2 hours                          │
│                                      │
│  ⚠  About a 1 in 7 chance            │
│      of going LOW                    │
│                                      │
│  ─────────────────────────────────   │
│  Low        ██░░░░░░░░░░░░░  14%     │
│  In range   ████████████░░░  71%     │
│  High       ██░░░░░░░░░░░░░  15%     │
│                                      │
│  This is an estimate, not advice.    │
│  Test your blood sugar as usual.     │
└──────────────────────────────────────┘
```

### 5.2 Language rules

| Do | Don't |
|---|---|
| "About a 1 in 7 chance of going low" | `P(State 2) = 0.14` |
| "This is an estimate" | "You will be at 130" |
| "Test your blood sugar as usual" | Anything implying she can test less **(INV-5)** |
| "Not confident enough to predict this one" | A fabricated number to fill the space |
| Show the risk | Give advice |

### 5.3 Refusal is a valid output

When a guardrail fires (`07` §9):

```
┌──────────────────────────────────────┐
│  🤷  Not confident enough to          │
│      predict this one.                │
│                                       │
│  This meal is unlike anything in      │
│  your history so far.                 │
│                                       │
│  Test as usual.                       │
└──────────────────────────────────────┘
```

**Never fill the silence with a number.** A refusal is more useful than a guess, and infinitely safer.

### 5.4 Baseline conflict

```
┌──────────────────────────────────────┐
│  ⚠  The two methods disagree.         │
│                                       │
│  Standard calculation says: in range  │
│  The learned model says:    high      │
│                                       │
│  Showing both. Test as usual.         │
└──────────────────────────────────────┘
```

**The system does not pick a winner.**

---

## 6. Bolus Calculator — F-5

> **Gate status: ungated (S-1011, DL-035).** This screen was specified as *post Gate 2*; that
> gate is **retired**. The ICR is an ordinary profile value, and a missing/`<= 0` one shows a
> plain *"profile incomplete — set the ICR"* message, not a gate refusal.
> **INV-3 and INV-4 still bound this screen**, and IOB is still displayed-never-typed.

**Show the arithmetic.** She has done this maths by hand for 30 years. She should be able to check the machine.

### 6.0 Insulin on board is **displayed, never typed** — REQ-020 **[SAFETY]**

```
│  Insulin on board      2.1 U  (derived)  │
│  from your 6.0 U bolus at 1:15 PM        │   ← read-only, with its provenance
```

**There is no IOB input field on this screen, or anywhere else.** IOB is always computed by
`iob_at()` from `bolus_log`; a typed IOB is a **forbidden pattern** with a standing AST guard
(`detect_manual_iob`, S-105) that fails the build. A hand-entered IOB would silently corrupt
the single most safety-relevant subtraction in the formula — the one that stops her stacking
insulin. Show the number and where it came from; never let anyone edit it.

```
┌──────────────────────────────────────┐
│  Suggested dose                      │
│                                      │
│         7.9 units                    │
│                                      │
│  ─────────────────────────────────   │
│  Carbs       60 ÷ 8.3      =  7.2    │
│  Correction  (190−135) ÷ 30 =  1.8   │
│  Insulin on board           = −1.1   │
│  ─────────────────────────────────   │
│                               7.9    │
│                                      │
│  A suggestion for your review —      │
│  not an instruction.                 │
└──────────────────────────────────────┘
```

**Below BG 80 (INV-4):**
```
┌──────────────────────────────────────┐
│  ⚠  Your blood sugar is 74.           │
│                                       │
│      Treat the low first.              │
│      No dose suggested.                │
└──────────────────────────────────────┘
```

**Cap event (INV-3):** flagged loudly, never silently clipped.
```
│  ⚠  That would need more than 15 U.   │
│      Please check the carb entry.      │
```

---

## 7. Operator Dashboard

### 7.1 Adherence — the one he lives in

```
VALID MEALS          47 / 150 to Gate 1
IN-WINDOW RATE       68%   ⚠ below 70%
DAYS SINCE LAST LOG  1     ✓

EXCLUSIONS
  outside_window        14   ← the big one
  missing_outcome        6
  rescued                4   ← retained as hypo events (INV-7)
  iob_cob_contamination  2

TRANSCRIPTION LAG
  median(logged_at − datetime)   34 min   ⚠ rising
```

**The two numbers that matter most:**
- **Days since last log** — the abandonment early-warning.
- **`median(logged_at − datetime)`** — the recall-bias metric. If it climbs, the data is degrading and you need to know **before** the model does.

### 7.2 Shadow mode — the report card

Calibration curve, hypo recall, Clarke grid, predictions vs actuals, gate status, drift,
`β_insulin < 0` warnings.

**Every metric is shown three ways, together — not one instead of another.** The operator may
be a family member, not a statistician; a bare "Brier 0.13" tells them nothing, and hiding the
number tells a clinician nothing. So each row carries **(1) a value, (2) a plain-language
interpretation, and (3) the technical term**:

```
┌────────┬─────────────────────────────────────────────────────┐
│  71%   │ Catches her lows                            [Good]  │
│  Good  │ Out of every 10 real lows it warns about 7 in        │
│        │ advance. The simple method warns about 6.            │
│        │ ▸ Hypo recall @ FAR ≤ 10% = 0.71 (baseline 0.58)     │
└────────┴─────────────────────────────────────────────────────┘
```

Applies to: hypo recall, false-alarm rate, Brier ("are its percentages truthful?"), MAE
("typical miss on a glucose number"), off-by-one / severe ("how wrong when it's wrong?"),
Clarke ("dangerous mistakes?"), `β_insulin` ("does it make medical sense?").

**Rules:**
- **Plain accuracy is never shown** (07 §9) — meaningless on an imbalanced 5-class problem.
- **The `β_insulin < 0` alarm is on this screen**, not buried in a log.
- The full charts (calibration curve, Clarke grid, confusion matrix) sit behind a
  **"detailed charts"** disclosure — available, not the first thing.
- **No dose ever appears on an operator screen.**

### 7.3 The promotion control — **[SAFETY]**

The only place Gate 1 can be opened. Shows the four conditions as a live checklist:

```
✓ Enough meals logged             168 of 150
✓ Better than the simple method   catches 71% vs 58%
⏳ Watched quietly for 90 days     day 61 of 90 — 29 to go
✕ You've turned it on, on purpose  not done yet

        [ Turn on for her ]   ← DISABLED, with the reason shown
```

**Rules:**
- The button is **disabled while any condition is unmet, and the reason is always visible** —
  never a dead control with no explanation.
- Promotion is an **explicit, audited action** that sets `model_artifact.is_promoted`. Code
  never sets it from a metric threshold (`07 §Retraining`; S-1006).
- **Good numbers are not permission.** The copy must say so — the operator is deciding to put a
  person who cannot feel a low in front of a model, and the UI should feel like that decision.
- Revocation is available at any time and takes effect on the next call (gates are live, ADR-7).

---

## 8. What This Should Feel Like

She has managed this disease for 30 years without you. **The system is not smarter than her — it is more consistent than her at 7am.**

- **Never scold.** Not for a late reading, not for a missed meal, not for a high.
- **Never nag.** One prompt. Never a second.
- **Never pretend to certainty** it does not have.
- **Never suggest she test less.**

If it feels like a machine grading her, she will stop using it, and it will have done nothing but make her feel watched.
