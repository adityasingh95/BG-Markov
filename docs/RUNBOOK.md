# RUNBOOK — running BG-Markov locally and checking it by hand

*Audience: the operator, at the laptop.*
*Everything here binds to `127.0.0.1` only (`06 §7`). The app never leaves localhost in v1.*

---

## 1. First run

```bash
./scripts/dev.sh setup      # venv + pinned deps + schema, via Alembic
./scripts/dev.sh demo       # seed SYNTHETIC data, then serve it
# open http://127.0.0.1:8000
```

Needs **Python 3.12**. `setup` is idempotent; run it again after a `git pull`.

### The two databases, and why they are separate files

| | `bgapp-dev.db` | `bgapp-demo.db` |
|---|---|---|
| Created by | `dev.sh setup` / `serve` | `dev.sh demo` |
| Contents | **empty** — real capture goes here | 240 days of synthetic data |
| On screen | nothing unusual | **a red DEMO DATA banner on every page** |

★ **The banner comes from the database, not from how you started the app** (S-1024,
DL-062). An environment variable can be forgotten or left over from the previous run, and
the mistake is silent in both directions. Move the file, reopen it in a month, hand it to
someone else — it still says what it is.

`./scripts/dev.sh status` tells you which is which without opening either.

> **Why this matters more than it looks.** On screen, 658 synthetic meals render exactly
> like 658 real ones. The adherence dashboard says *413 / 150 valid meals*; the calculator
> subtracts a real-looking IOB. The failure that enables is not a crash — it is **believing
> a number**.

---

## 2. Commands

| Command | What it does |
|---|---|
| `./scripts/dev.sh setup` | venv, pinned deps, schema via Alembic |
| `./scripts/dev.sh serve` | serve the **empty** database — this is the real-capture path |
| `./scripts/dev.sh demo` | seed (once) and serve the **synthetic** database |
| `./scripts/dev.sh status` | which databases exist, what they hold, and which is marked |
| `./scripts/dev.sh reset` | delete the local databases — asks you to type `DELETE` |
| `./scripts/dev.sh check` | the CI gates: ruff, `mypy --strict`, pytest, 90 % coverage |

`BGAPP_PORT=8123 ./scripts/dev.sh demo` if 8000 is taken.

---

## 3. Manual verification checklist

Work through this on the **demo** database. Each line says what should happen; where a
number matters it is given, so "looks about right" is not the test.

### The patient screens

| # | Do | Expect |
|---|---|---|
| 1 | Open `/` | A red **DEMO DATA** banner. Three favourite chips, **none ticked**. |
| 2 | Tap a favourite | **That one** gets a ✓ and a heavier border; the other two do not. |
| 3 | Tap a different favourite | The ✓ **moves**. Never two. |
| 4 | Fill BG + bolus, tap a timing chip, **Log meal** | A `✓ Logged. Set a phone alarm for … to test.` toast, and the button greys out for the moment it is saving. |
| 5 | **Tap Log meal twice, fast** | Still **one** meal. Check with `dev.sh status` — the meal count goes up by 1, not 2 (S-1019). |
| 6 | Reload, fill a *different* meal, log it | Two meals total. The key must rotate for a genuinely new entry. |
| 7 | Open `/meals/<id>/post-bg` | The reading time is **pre-filled with mealtime + 120** and is editable. |
| 8 | Enter a reading, Save | `✓ Saved — 120 min after your meal.` — **not** "Could not save" (S-1018). |
| 9 | Enter a reading 3½ h after the meal | `✓ Saved — a bit outside the 2-hour window, that's fine.` Never a scold. |
| 10 | Open `/meals/<id>/readout` | *"Nothing to tell you yet."* No number, no percentage, no dose. Gate 1 is shut (INV-2). |
| 11 | `/corrections` — log one with no food | Saves, and offers a +4 h follow-up. |

### The calculator — `/bolus`

| # | Do | Expect |
|---|---|---|
| 12 | 60 g, BG 165 | A dose, with **the working shown**, and IOB above it labelled *"derived from your logged injections — never typed in"*. |
| 13 | 60 g, **BG 72** | **No dose. No IOB. No number at all.** *"Treat the low first."* (INV-4) |
| 14 | **900 g**, BG 300 | Capped at **15.00 U**, flagged *"That input looks wrong"*, and the working ends `(CAPPED — input looks implausible, please re-check)` (INV-3). |

### The operator screens

| # | Do | Expect |
|---|---|---|
| 15 | `/operator` | Adherence: 413 / 150 valid meals, exclusions by reason, `rescued 29 ← retained as hypo events (INV-7)`. |
| 16 | `/operator/shadow` | Gate 1 **CLOSED**, five conditions listed, and *"Good numbers are not permission."* |
| 17 | `/operator/profile` | ICR 9.0, ISF 30.0, target 135, with history. |
| 18 | Change ICR to **45**, save | Saves **and shows a flag** — out-of-range is accepted and surfaced, never silently refused (DL-048). |
| 19 | `/basal` — record a dose | Saves in place. **You stay on `/basal`** — no navigation to a JSON page (S-1020). |
| 20 | Record the **same date** again with different units | **One** row, corrected. Not two (S-1013). |

### Accessibility — worth doing once

| # | Do | Expect |
|---|---|---|
| 21 | Shrink the window to phone width | No sideways scrolling on any screen. |
| 22 | Browser zoom to 200 % | Still no sideways scrolling. Text stays ≥ 18 px. |
| 23 | Switch your OS to dark mode, reload | The whole app follows. Text stays readable (S-1022). |
| 24 | Tab through the meal form | A visible focus ring on every control. |

---

## 4. Known **not** working — do not spend time on these

These are recorded, not forgotten. Each links to where it is written up.

| What | Status |
|---|---|
| **Gate 1 can never open.** Promotion requires 90 shadow days; shadow days require prediction rows; prediction rows require a promoted model. Measured, circular. | **Escalated, awaiting a decision** on what the 90-day shadow period measures — the system, or a specific model version. |
| **There is no promote control in the UI.** The *"Turn it on for her"* button is `disabled` in every state. `POST /api/operator/promote` exists and nothing reaches it. | S-1020 outcome — a safety-design decision, deliberately not taken as a wiring fix. |
| **The β_insulin confounding alarm is dark.** A refit does not record `unconstrained_beta_insulin`, so the INV-8 alarm reads "no alarm" because nothing measured it. | **S-1017, not started.** A dark alarm looks identical to a quiet one. |
| `/operator/shadow` says *"No model has been fitted yet"* when one is fitted and promoted. The real reason the panel is empty is fewer than 10 scored predictions. | Backlog, EPIC 11 still-open. |
| The profile page does not refresh after a save, so the old *"In force now"* sits beside the ✓. | S-1020 outcome. |
| The readout has no distribution bars (`05b §5.1` shows Low / In range / High). | S-1022 outcome — changes what `PatientReadout` carries, so INV-2 scope, so a story. |

---

## 5. If you want it recorded

```bash
python -m scripts.demo_ui --record ./demo-ui-recording --slow-mo 220
playwright show-trace ./demo-ui-recording/trace/demo-walkthrough.zip
```

Nine steps, captioned, in a real browser, asserting against the database as it goes (S-1023).

---

## 6. If something is wrong

```bash
./scripts/dev.sh check        # ruff + mypy --strict + pytest + coverage — the CI gates
./scripts/dev.sh status       # what the databases actually contain
BGAPP_BROWSER_ARTIFACTS=./browser-artifacts .venv/bin/pytest tests/e2e   # record the failure
```

**A guardrail refusing you is the guardrail working.** Before treating a refusal as a bug,
read what it says: `CLAUDE.md` lists the invariants and why each exists.
