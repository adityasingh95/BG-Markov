# 02 — Functional Specification

*Purpose: flow-level behaviour. The logging flow is the critical path.*
*Read before: `05-api-contract.md`, `05b-ui-ux-spec.md`.*

---

## 0. The Governing Requirement

> **A repeat meal must be loggable in ≤4 taps + 2 numbers. A post-meal reading in <15 seconds.**

Gate 1 needs 150 valid meals ≈ 3 months at realistic adherence. **Every second added to the logging flow pushes that out and raises the chance she abandons it.**

If any requirement below conflicts with this one, **this one wins.** A system with complete data fields and 40 records is a failed system.

---

## 1. Log a Meal (F-1) — REQ-001..009

She logs **before** eating.

**Flow:**
1. Tap **Log Meal**.
2. `meal_type` is **pre-selected from the clock**. Overridable.
3. **Favourites row first:** "Same as usual" / recent meals for this meal type. One tap populates all macros.
4. Enter pre-meal BG (numeric keypad).
5. Enter meal bolus + `bolus_offset_min`.
6. If pre-BG is above target, prompt for a **correction bolus** (separate field).
7. Submit.

**Rules:**
- Exercise, notes, and confidence are **optional and collapsed**. They never block submission.
- Draft auto-saves to `localStorage` on every field change. A failed submit never loses input.
- `logged_by` = `patient` | `operator`.
- **REQ-004: every time is reported.** "When did you eat?" — sensible default, always editable, **never silently accepted from `now()`.**
- **REQ-005:** `logged_at` = system clock, stored separately.

### F-1.1 Dish selection — REQ-009
- Search-as-you-type. **No dropdowns.**
- Recents and favourites shown without searching.
- Portion via a multiplier stepper (`1 katori`, `2 rotis`) — not free-text grams.
- Macros (carbs/protein/fat/fibre) auto-populate; `macro_confidence` = 95.
- Unknown dish → free text, `macro_confidence` = 60, queued for the operator to add properly.

### F-1.2 Bolus timing — REQ-003 **[critical]**
Fiasp peaks at ~55 min. Pre-bolusing 10 minutes versus injecting at the first bite materially changes the 2-hour value. **This field carries more signal than almost any other. It cannot be skipped.**

- Stored as a **signed integer**: negative = pre-bolus.
- Presented as a choice, not a number field: `15 min before` / `10 min before` / `just before` / `with food` / `after`.
- Defaults to her habitual value (learned from her own history), but is **always displayed** — never silently assumed.

## 2. Post-Meal Reading (F-2) — REQ-010, 011, 014

**Flow:** open the meal → enter BG → enter the time it was taken → submit.

- **REQ-004:** `post_bg_time` is **reported.** If she's entering it 30 minutes later, the system asks when she actually tested. It does not assume `now()`.
- `elapsed_min` is computed from **reported** times, never from `logged_at`.
- Stored **even when outside the valid window** — the data is needed to diagnose adherence.
- Feedback is non-judgemental: "logged ✓" / "logged — a bit late, that's fine."

### F-2.1 Test-time prompt — REQ-014
On meal submission: **"Logged. Set a phone alarm for 3:15 PM to test."**
Computed as **reported mealtime + 120 min** — *not* `logged_at + 120`.

### F-2.2 Late / retrospective entry — REQ-011
- She can add a post-meal reading late, entering the real time.
- She can log an entire meal retrospectively.
- **The system never fabricates a timestamp.** It asks.

## 3. Hypo & Correction Events (F-3)

### F-3.1 Hypo rescue — REQ-012, INV-7 **[SAFETY]**
- On the post-meal form: "Did you need to treat a low?" → grams of rescue carbs.
- Sets `hypo_treatment = true`.
- **The meal is excluded from outcome regression but RETAINED as a hypo event.** Invisible to her; critical internally. Silently dropping these rows erases exactly the lows the system exists to predict.

### F-3.2 Correction-only event — REQ-013
**The most valuable data the system collects** — the only causally clean read on ISF, because there is no food to confound it.

- When a correction bolus is logged with **no meal**, ask: "Will you be eating in the next 4 hours?"
- If no → prompt for a **+4 h follow-up BG** (and display the time to set an alarm for).
- Captures `bg_before`, `units`, `bg_after`, `food_in_window`, computed `iob_at_start`.
- She should be actively encouraged to log these.

## 4. Risk Readout (F-4) — REQ-040, INV-2

### F-4.1 Gating **[SAFETY]**
- **Below Gate 1 she sees nothing.** No preview, no "beta" number, no greyed-out placeholder with a real value behind it.
- Below Gate 1, output is **operator-only** and labelled shadow mode.

### F-4.2 The readout (post Gate 1)
Given a planned meal + bolus, she sees the 2-hour risk.

- **Hypo risk is the headline.** Not a footnote below "target range" — the headline. This is why the system exists.
- Plain language: *"About a 1 in 7 chance of going low"*, not `P(State 2) = 0.14`.
- **Uncertainty is shown, not hidden.** If a guardrail fires (`07` §9), it says *"not confident enough to predict this"* — **a refusal is a valid output.**
- **Never phrased as advice.** "Here is the risk," never "you should."

### F-4.3 Baseline conflict — REQ-046
If the clinical baseline and the ordinal model differ by more than one state, **both are shown** and the conflict is flagged. **The system does not pick a winner.**

## 5. Bolus Calculator (F-5) — REQ-041..043, INV-1/3/4

### F-5.1 Gating **[SAFETY]**
**Hard-disabled until Gate 2** (ICR confirmed AND ISF confirmed or derived). No preview. No silent background computation.

### F-5.2 The calculator (post Gate 2)
- Inputs: carbs, current BG. **IOB is computed, never entered.**
- Output shows the **full arithmetic**, so she can check it by hand:

```
Carbs:       60 g ÷ 8.3      =  7.2 U
Correction:  (190 − 135) ÷ 30 =  1.8 U
IOB:                          − 1.1 U
──────────────────────────────────────
Suggested:                      7.9 U
```

- **Refuses below BG 80** (INV-4): "Treat the low first."
- **Capped at 15 U** (INV-3). A cap event is **flagged as implausible input**, not silently clipped.
- Never negative.
- Always framed as **a suggestion for review**. Never an instruction.

## 6. History & Review (F-6)

### F-6.1 Patient view
- Recent meals, readings, simple 7/30-day time-in-range.
- **No model output below Gate 1.**
- Editable within 24 h (she will mistype a BG). Edits are audit-logged.

### F-6.2 Operator view — REQ-053
**Adherence dashboard — the one he will actually live in:**
- % of meals with an in-window post-reading
- % invalid, **by exclusion reason**
- **`median(logged_at − datetime)`** — the transcription-lag / recall-bias metric. If it climbs, the data is degrading.
- **Days since last log** — the abandonment early-warning.

**Shadow-mode dashboard:**
- Predictions vs. actuals, calibration curve, hypo recall, Clarke grid.
- Gate status: valid-meal count, what is blocking each gate.
- Any `β_insulin < 0` warnings from the unconstrained fit — **a signal about the data, not a nuisance.**

## 7. Operator Functions (F-7)

- Log on her behalf (attributed to `operator`).
- Manage the dish table; resolve queued free-text dishes.
- Update clinical constants — **versioned, never overwritten** (REQ-054).
- `cli refit`; promote or reject a candidate model.
- Review and **manually re-arm** the kill switch.
- `cli export` — full CSV.
- `cli restore-drill`.
