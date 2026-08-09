# 05b — UI/UX Specification

*Purpose: accessibility, logging ergonomics, risk-readout language.*
*Read before: building `api/templates/`.*

Jinja2 + HTMX + Pico.css. No build step. No React.

---

## 1. Users

> **Research mode (`00a`).** There is one user — the researcher — and §3's logging
> flow moves to EPIC 3b. **§2 (accessibility) and §5 (language) stay in force**
> for every screen this build does produce: they are how a probability gets
> presented honestly, which does not depend on who is reading it.

| | Researcher | Patient *(not built)* |
|---|---|---|
| Context | At the laptop, reading metrics and generated data | Would be 59, on a phone, sometimes at BG 55 |
| Priority | Density and diagnostics | Speed and forgiveness |
| Sees model output | Always, labelled with gate state and model version | — no patient surface exists |

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

> **Not built in this build** (EPIC 3b). Retained because the repertoire is real: **the generator draws from the same 30–60 dish table**, which is what makes its carbohydrate distribution realistic rather than uniform noise.

```
┌──────────────────────────────────────┐
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
| "Test your blood sugar as usual" | Anything implying testing less — **copy rule, `00a §6`.** INV-5 is retired as an invariant; the rule costs nothing and stays. |
| "Not confident enough to predict this one" | A fabricated number to fill the space |
| Show the risk | Give advice |

### 5.3 Refusal is a valid output

When a guardrail fires (`07` §10):

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

## 6. Bolus Calculator (post Gate 2) — F-5

**Show the arithmetic.** She has done this maths by hand for 30 years. She should be able to check the machine.

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

### 7.2 Shadow mode
Calibration curve, hypo recall, Clarke grid, predictions vs actuals, gate status, drift, `β_insulin < 0` warnings.

---

## 8. What This Should Feel Like

She has managed this disease for 30 years without you. **The system is not smarter than her — it is more consistent than her at 7am.**

- **Never scold.** Not for a late reading, not for a missed meal, not for a high.
- **Never nag.** One prompt. Never a second.
- **Never pretend to certainty** it does not have.
- **Never suggest she test less.**

If it feels like a machine grading her, she will stop using it, and it will have done nothing but make her feel watched.
