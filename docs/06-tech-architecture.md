# 06 — Technical Architecture

*Purpose: stack, topology, ADRs, durability.*
*Read before: any implementation.*

**v1: a single laptop. Frontend, backend, database, model — all local.**

---

## 1. Architectural Drivers

| # | Driver | Consequence |
|---|---|---|
| 1 | **Adherence is the bottleneck** | Gate 1 needs 150 valid meals. Fast logging or the project ends with 40 records. |
| 2 | **Data loss is unrecoverable** | ~3 months of her life. Backup is not hardening — it is whether the project exists. |
| 3 | **Timestamps are reported, not observed** | She logs at the laptop, not at the table. See §4. |
| 4 | **One user, one machine, forever (v1)** | No TLS, no VPS, no PWA, no scheduler, no auth. **Exploit this ruthlessly.** |
| 5 | **Safety-critical output** | Gates, guardrails, and the shadow log are architectural. **They do not get simplified away with the infrastructure.** |

**Anti-driver:** there will never be a second user. **Any choice justified by "what if we scale" is wrong.**

---

## 2. Component View

```
┌────────────────────────────────────────────────────────┐
│  LAPTOP — localhost:8000                               │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  BROWSER — Jinja + HTMX + Pico.css               │  │
│  │  Log Meal · Post-BG · History · Risk · Operator  │  │
│  │  localStorage draft-save                         │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │ HTTP (127.0.0.1)               │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │  UVICORN + FASTAPI  (Python 3.12)                │  │
│  │                                                  │  │
│  │  api/           routes, templates                │  │
│  │  ─────────────────────────────────────────────   │  │
│  │  core/safety.py     INV-1..9  ← ZERO INTERNAL    │  │
│  │  core/gates.py      Gate 0/1/2   DEPENDENCIES    │  │
│  │  core/guardrails.py                              │  │
│  │  ─────────────────────────────────────────────   │  │
│  │  features/      IOB · basal EWMA · exercise      │  │
│  │  models/        baseline · ordinal · ICR/ISF     │  │
│  │  prescribe/     bolus calc  (Gate 2, NO ML)      │  │
│  │  data/          repositories                     │  │
│  │  cli/           refit · export · backup · drill  │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │                                │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │  SQLite   ~/bgapp/app.db   (WAL)                 │  │
│  │  ⚠ NEVER inside a cloud-synced folder            │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │ sqlite3 .backup (hourly, cron) │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │  ~/Dropbox/bgapp-backup/                         │  │
│  │    snap.db                  hourly snapshot      │  │
│  │    export-YYYY-MM-DD.csv    nightly, git-tracked │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 3. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | **Python 3.12** | Forced — statsmodels/PyMC *are* the model. Splitting languages for a single-user app is unjustifiable. |
| Server | **uvicorn** on `127.0.0.1` | No Caddy, no TLS, no systemd in v1. |
| API | **FastAPI** | Typed; pydantic models shared with the data layer. |
| UI | **Jinja2 + HTMX + Pico.css** | A forms app for one person. A React build pipeline would consume effort that belongs in the model. |
| DB | **SQLite**, WAL | Single user, single writer. **One file — which is what makes backup solvable.** |
| Migrations | **Alembic** | Her data must survive schema changes. |
| Model | **statsmodels `OrderedModel`**; PyMC at n≥200 | 150 rows × ~22 features. Trains in milliseconds. |
| Jobs | **`cli/` + OS cron** | With reminders deferred there is nothing to schedule in-process. |
| Backup | **`sqlite3 .backup` → synced folder** | §5. |

### Explicitly rejected

| Rejected | Why |
|---|---|
| React / Next.js | Build pipeline, hydration, state management. All cost, no benefit. |
| PostgreSQL | Ops overhead, no payoff at n=1. **SQLite's single-file property is a feature, not a compromise.** |
| Docker / K8s | One process, one user, one laptop. |
| Celery / Redis | Four cron-like jobs. |
| A training service | 150 rows. It would be theatre. |
| Any cloud ML API | Her health data does not leave infrastructure the operator controls. |
| APScheduler | Nothing to schedule once reminders are deferred. |

---

## 4. ★ The Defining Risk — Reported Timestamps

**She logs at the laptop, not at the table. The moment she logs is not the moment she ate.**

If any form defaults a clinical time to `now()`, two fields become fiction:

| Field | Corrupted by | Why it matters |
|---|---|---|
| `bolus_offset_min` | Assuming bolus time = log time | Fiasp peaks at 55 min. **Pre-bolus timing is one of the largest determinants of the 2 h value.** |
| `elapsed_min` | Assuming post-BG time = log time | Drives the 105–135 min validity window. Fabricating it means **training on meals that never happened at the times recorded.** |

**There would be no error. No warning. No way to detect it afterwards.** The model would simply be wrong, confidently, forever.

### Mandatory rules

1. **Every clinical time is reported, never assumed.** Sensible default, always editable, never silently accepted.
2. **`logged_at` is a separate column.** System clock. Never used for `datetime`.
3. The operator dashboard surfaces **`median(logged_at − datetime)`** as a first-class data-quality metric.
4. **`datetime.now()` populating a clinical timestamp is a forbidden pattern with a grep test** (S-105).

---

## 5. Data Durability — Non-Negotiable

**The one thing not simplified away with the rest of the infrastructure.** A laptop is *more* fragile than a VPS — it gets dropped, stolen, and spilled on.

| # | Mechanism | Cadence |
|---|---|---|
| 1 | `sqlite3 app.db ".backup ~/Dropbox/bgapp-backup/snap.db"` | Hourly (cron) |
| 2 | CSV export of every table → same folder, git-committed | Nightly |
| 3 | Manual copy to an external drive | Monthly |

**Rules:**

- **`app.db` NEVER lives inside a cloud-synced folder.** Sync mid-write corrupts SQLite. This is a well-known footgun. **Only the `.backup` snapshot goes there** — it is a consistent point-in-time copy.
- **★ Run one full restore drill in month one, before real data exists.** An untested backup is not a backup. **S-304 is not done until the drill has been executed and BA has logged the date.**
- The CSV export is format-rot insurance: **her data outlives the code, and outlives the operator's memory of how the code works.**

---

## 6. Model Lifecycle

- `python -m cli refit` — manual, monthly.
- Every artifact carries a manifest: data hash, row count, feature list, fit date, metrics, gate state.
- Every `prediction_log` row records its **model version** (INV-9). Without it, shadow-mode analysis is uninterpretable.
- **Promotion is manual.** A candidate ships only if it beats the incumbent on **hypo recall** on a held-out temporal fold.
- Kill switch: `cli drift-check` (weekly). Trips → ML suppressed, **falls back to the clinical baseline**. **Re-arming is manual, always.**

---

## 7. Security (v1)

**Honest position: the laptop's full-disk encryption and login password ARE the security boundary.** The app binds to `127.0.0.1` and ships no auth.

Acceptable **only** if:
- [ ] FDE is on (FileVault / BitLocker / LUKS)
- [ ] The laptop locks on sleep with a password
- [ ] The app is **never** bound to `0.0.0.0`

**Add `logged_by` anyway** — a plain toggle, not auth. Attribution cannot be retrofitted into historic data.

**The moment this leaves localhost, auth becomes mandatory.**

---

## 8. ADRs

| # | Decision | Rationale | Reversible? |
|---|---|---|---|
| ADR-1 | SQLite over Postgres | Single writer; single-file backup is the point | Yes, painfully |
| ADR-2 | HTMX over React | Forms app for one user; effort belongs in the model | Yes |
| ADR-3 | Reminders deferred; phone-alarm prompt instead | Zero infrastructure; her phone already does this | Yes — restore if adherence fails |
| ADR-4 | **Backup retained despite v1 simplification** | Data loss is the top failure mode | **No. Do not cut.** |
| ADR-5 | Train in-process; CLI, not scheduler | 150 rows | Yes |
| ADR-6 | **`core/safety.py` has zero internal dependencies** | Prevents circular weakening under refactor | **No** |
| ADR-7 | **Gates evaluated per-request, never cached** | A cached "gate passed" is a silent safety failure | **No** |
| ADR-8 | **`logged_at` distinct from `datetime`** | See §4 | **No — retrofitting is impossible** |
| ADR-9 | No auth in v1; FDE is the boundary | Localhost, single user | Yes — mandatory before any non-localhost bind |
| ADR-10 | **No ML in the dose calculation** | The clinical formula is causal; the model is not | **No** |
