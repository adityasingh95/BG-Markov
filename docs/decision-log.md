# Decision Log

*Owner: BA. Every deviation from spec, with rationale and who approved it.
Assumptions made under the README "mark every assumption" rule are recorded
here and mirrored into `01-prd.md` §9 Open Questions where they need clinical
sign-off.*

---

## DL-001 — Python 3.12 via an isolated interpreter
**Story:** S-101 · **Type:** environment note (no spec deviation)
`06-tech-architecture.md` mandates Python 3.12. The session default is 3.11;
3.12.3 is available at `/usr/bin/python3.12` and is used. `requires-python`
is pinned to `>=3.12`.

## DL-002 — PyPI egress is blocked in the build session; deps declared, CI-verified
**Story:** S-101 · **Type:** environment constraint · **Approved by:** _pending operator ack_
The execution environment's egress policy returns **403 Forbidden** for
`pypi.org` (both directly and via the agent proxy), so `pip`/`uv` cannot
install packages this session.

Consequences and how each AC is still met honestly:
- **Runtime deps (fastapi, statsmodels, pandas, pydantic, hypothesis, alembic,
  …)** are pinned in `pyproject.toml` but not installed here. `ci.yml` runs
  `pip install -e ".[dev]"` on GitHub Actions (PyPI reachable there) and fails
  the build if resolution breaks.
- **Coverage gate (90% on `core/`)** — `coverage`/`pytest-cov` are not
  installable this session, so `--cov` is deliberately kept **out** of pytest
  `addopts` (it would break local runs). The gate is configured in
  `[tool.coverage]` and enforced by CI's explicit
  `pytest --cov=core --cov-fail-under=90`.
- **ruff / mypy / pytest** are available this session as `uv`-managed tools, so
  the lint/type/test ACs were verified locally and are re-verified in CI.

**Impact on later epics:** EPIC 2+ need the runtime deps *installed* to run.
Those stories cannot be executed to green in this session until egress is
opened or a mirror is provided. **Escalated to the operator.** This is not a
spec deviation — it is an environment limitation to resolve before EPIC 2.

## DL-003 — Coverage `source` scoped to `core` for now
**Story:** S-101 · **Type:** clarification
`09-test-plan.md` §2 requires ≥90% coverage on `core/features/models/prescribe`.
Only `core/` exists at S-101. `[tool.coverage.run] source` lists `core` today
and is to be widened as each package is introduced, so the gate never passes
vacuously against a not-yet-existent package.

## DL-004 — PyPI/npm egress is now OPEN; DL-002 constraint lifted
**Story:** S-102 · **Type:** environment note (supersedes DL-002's constraint)
The egress policy that returned **403** for `pypi.org` in the S-101 session
(DL-002) is **no longer in effect**. This session installed the full pinned
dependency set into a Python 3.12 venv with `pip install -e ".[dev]"` and it
resolved cleanly (fastapi, statsmodels, pandas, pydantic, alembic, hypothesis,
pytest-cov, coverage, …). Consequences:
- Runtime + dev deps are now **installable and were verified locally** this
  session, not only in CI. The coverage gate (`--cov=core --cov-fail-under=90`)
  runs locally as well as in CI.
- Egress is **host-scoped**: `pypi.org`, `files.pythonhosted.org` and
  `registry.npmjs.org` are allowed; CDN hosts (`cdn.jsdelivr.net`,
  `redirector.gvt1.com`) are **blocked**. So third-party browser assets are
  vendored from npm, not a CDN (see DL-006), and Playwright uses the
  pre-installed Chromium rather than downloading one.
- DL-002 remains in the log as the historical record; its *blocking* impact on
  EPIC 2+ is **resolved**.

## DL-005 — Browser-driven accessibility tests (Playwright + axe-core)
**Story:** S-102 · **Type:** test-infrastructure decision
`05b §2` and the S-102 backlog make axe + 200 %-zoom testing **"not optional."**
Asserting accessibility from template source text would be theatre — contrast,
computed font size, target geometry and reflow only exist in a real browser.
Decision: `tests/a11y/` drives **real Chromium via Playwright** against a live
FastAPI server (uvicorn on a background thread), with `axe-playwright-python`
providing axe-core. Pinned dev deps: `playwright==1.53.0`,
`axe-playwright-python==0.1.4`, `httpx==0.28.1`. This session uses the
pre-installed browser at `$PLAYWRIGHT_BROWSERS_PATH/chromium`; CI installs it
via `playwright install --with-deps chromium`. The a11y suite runs in the same
`pytest` invocation as the unit tests and is registered under the `a11y` marker.

## DL-006 — Pico.css vendored from npm, not a CDN
**Story:** S-102 · **Type:** clarification
`06 §3` mandates Pico.css with **no build step**. CDN hosts are blocked by the
egress policy (DL-004) and, per `06 §4`, this app runs on `127.0.0.1` and must
not depend on external hosts at request time anyway. Decision:
`@picocss/pico@2.0.6` is fetched **once** from the npm registry and committed to
`api/static/pico.min.css`; the app serves it locally. Pinned by the committed
file's contents (the exact 2.0.6 minified build).

## DL-007 — `max_bolus_u` config ceiling (25 U) is distinct from INV-3's cap (15 U)
**Story:** S-103 · **Type:** clarification (a note for S-901, not a deviation)
Two different bolus numbers exist and must not be conflated:
- **INV-3 recommendation cap = 15 U.** A constant in `core/safety.py` (S-104)
  and the final authority in the dose path (`07 §11`, REQ-042). A cap event is
  *flagged as implausible input*, never silently clipped.
- **`config.max_bolus_u` ceiling = 25 U** (`MAX_BOLUS_U_CEILING`). A config-field
  sanity bound so a misconfiguration/typo cannot load an absurd per-dose cap.
  The AC (`10-backlog.md` S-103) requires `max_bolus_u > 25` to raise.

`config.max_bolus_u` defaults to 15 (= INV-3's cap) and can be set anywhere in
`(0, 25]`. It can **never raise** the effective recommendation cap above INV-3's
15 U, because the dose path (S-901) is gated by `core/safety.py`. **Directive for
S-901:** clamp to `min(config.max_bolus_u, MAX_BOLUS_U)` and let INV-3 have the
last word. Flagged here so S-901 does not wire `config.max_bolus_u` straight into
the recommendation and thereby weaken INV-3.

## DL-008 — S-103 config carries the full 07 §1 constant set
**Story:** S-103 · **Type:** clarification (scope)
The S-103 AC names only `icr`, `isf`, `max_bolus_u`. The delivered
`ClinicalConfig` also carries `target_bg`, `iob_tp`, `iob_td`,
`basal_halflife_h` — the remaining `07 §1` constants — each with a validator
(`iob_td>iob_tp`, all curve constants `> 0`). Rationale: this is the clinical
config; the IOB engine (S-401), effective basal (S-402), baseline (S-501) and
prescriptive module (S-901) all read these, and validating them at load (not at
first use) keeps the "reject malformed clinical input at load" contract whole.
`patient_profile` versioning (REQ-054) remains the DB table's job (S-201); this
is the process config, not the versioned record.

## DL-009 — Bolus timing is inputtable, not preset-only (operator request)
**Story:** S-102 shell (refinement) · **Type:** UX clarification · **Approved by:** operator (this session)
`05b §3` sketches bolus timing as four quick-pick chips
(`15 before / 10 before / just before / with food`). `bolus_offset_min` is,
however, a **signed continuous** value (REQ-003 / glossary), and the presets
cannot express every offset. On operator request the S-102 shell now shows the
presets **plus** a numeric offset field (`name="bolus_offset_min"`,
`inputmode="numeric"`, "minutes before eating"). A11y test
`test_bolus_timing_is_inputtable_not_only_presets` guards it (RED-first).
**Update (same session):** the sign/direction UX was pulled forward into the
shell on operator request. The custom entry is now a **magnitude field
(`minutes`) + an explicit `before eating` / `after eating` direction** (buttons
carry `data-dir`), so both signs are expressible (negative = pre-bolus, positive
= after eating) and **neither direction is pre-selected** (REQ-003
never-silently-defaulted). Guarded by
`test_bolus_timing_supports_signed_before_and_after`.
**Still S-302's scope:** the authoritative capture — server-side validation,
sign computation from magnitude+direction, and hard enforcement of the
**cannot-be-skipped** rule on submit — remains **S-302** (EPIC 3). The shell
provides the accessible primitive; it does not yet enforce the rule on submit.

## DL-010 — `data/` is outside the 90 % coverage gate
**Story:** S-201 · **Type:** clarification
`09-test-plan.md §2` scopes the ≥90 % coverage gate to
`core/features/models/prescribe`. `data/` (repositories, ORM) is **not** in that
set, so `[tool.coverage.run] source` stays `core` (DL-003 pattern). `data/` is
still tested thoroughly by `tests/integration/test_schema.py` (round-trips +
Alembic migration); the metric gate simply does not apply to it. mypy `--strict`
**does** now cover `data` (CI), so typing is enforced even though coverage is not.

## DL-011 — `net_carbs_g` is a DB-computed column, not Python-floored
**Story:** S-201 · **Type:** design choice
`net_carbs_g = max(carbs_g - fiber_g, 0)` is a SQLAlchemy `Computed(...,
persisted=True)` column (SQLite STORED generated column), not a value written by
application code. Rationale: the `carbs=30, fiber=40 ⇒ −10` bug the TDD guards
becomes **structurally impossible** — there is no write path that can persist a
negative net-carb value, and no Python flooring to forget on a future refactor.

## DL-012 — `patient_profile` immutability is a data-layer guard, not a core INV
**Story:** S-201 · **Type:** clarification (invariant boundary)
REQ-054 ("constants versioned, never overwritten") is enforced by a SQLAlchemy
`before_update` event on `PatientProfile` that raises `ProfileImmutableError`
(defined in `data/tables.py`). This is deliberately **not** a `core/safety.py`
invariant: it defines no `inv<n>` function and no `SafetyViolation` subclass, so
the S-104/S-105 hygiene guards (single-definition, no re-implementation) stay
green. It is a structural data guarantee, adjacent to but distinct from INV-1..9.

## DL-013 — Alembic DB URL is never committed
**Story:** S-201 · **Type:** security/config note
`alembic.ini` ships an **empty** `sqlalchemy.url`. The real URL is supplied at
run time — programmatically (tests) or via the `BGAPP_DB_URL` env var
(`alembic/env.py`) — so a real patient DB path never lives in the repo. Consistent
with `06 §5` (`app.db` lives outside any synced folder) and `.gitignore`
excluding `*.db` / `app.db`.

## DL-014 — The lint/type gate runs fresh (no cache) so local == CI
**Story:** cross-cutting (surfaced after S-201) · **Type:** test-infra correctness
**Symptom:** CI runs #2–#7 failed at the `ruff` step on `I001` (import ordering)
in a few test files, while local `ruff check .` reported clean. No logic was
broken — the lint step just halts CI before the (passing) tests. **Root cause:**
a warm local `.ruff_cache` plus environment-dependent isort first-party
detection let a locally-clean commit still fail CI's fresh checkout — a
determinism gap that defeats the purpose of the gate.
**Fix:**
1. `[tool.ruff.lint.isort] known-first-party` is declared explicitly, so import
   grouping is deterministic in every environment (no auto-detection drift).
2. The S-101 toolchain gate test now runs `ruff check --no-cache` and
   `mypy --strict --no-incremental`, so a stale cache can never mask a real
   failure. A gate a cache can defeat is not a gate.
Confirmed by a green CI run (#9, commit `9cd8710`). Verified locally with a wiped
cache. No further action; recorded so the reasoning survives.

## DL-015 — Dish seed is representative, pending the operator's IFCT-2017 data
**Story:** S-204 · **Type:** deferred data · **Approved by:** _pending operator_
S-204 delivers the **ingest path** and the portion/free-text logic; the shipped
`IFCT_SEED` (roti, dal, rice, rajma, sabzi, idli) carries **placeholder** macro
values, not verified IFCT-2017 figures. The operator loads the real IFCT-2017
(NIN Hyderabad) values for her repertoire via `ingest_dishes(...)` before Gate 0
data collection, and resolves queued free-text dishes (`needs_review=True`).
Open item mirrored to `01-prd.md` §9. This is a data gap, not a code gap — the
2×roti-doubles and free-text-⇒-60 guarantees hold regardless of the numbers.

## DL-016 — S-301 meal form: three UI decisions
**Story:** S-301 · **Type:** design choices / clarifications
1. **Favourite *meals* are seeded, not a table (yet).** `05b §3`'s favourites are
   combos ("Dal + 2 roti + sabzi"); the schema (`04 §7`) has favourite *dishes*,
   not favourite meals. S-301 serves a seeded `FAVOURITES` list from the app and
   the tap-to-populate flow (the adherence mechanism). Persisting favourite-meal
   combos as a table is a later refinement; the ≤4-tap guarantee is what S-301
   delivers and tests.
2. **Risk-cue example moved to `/components`.** S-102 put a risk-readout example
   on the index page to test the colour-not-sole-signal pattern. The real
   meal-log form (`/`) must show **no** model output before Gate 1 (INV-2), so
   the primitives gallery (incl. the risk cue) now lives at `/components`. The
   S-102 a11y guarantees run against the real form; the colour-cue test against
   `/components`.
3. **The time field is a pre-filled, editable client default — this is not an
   ADR-8 violation.** `app.js` pre-fills the mealtime with the current local time
   and the client sends it as the reported `datetime`. ADR-8 forbids the
   *server* substituting `now()`; a visible, editable field she can correct is
   exactly the sanctioned behaviour (`05b §3`). `pre_bg_time` currently defaults
   to the same reported mealtime (a separate reading time is refined in S-303).

## DL-017 — RED-first / test-ownership deviations (audit 2026-07-15-01, H1)
**Story:** cross-cutting (S-103, S-201, S-202) · **Type:** process deviation ·
**Raised by:** independent-auditor (`audits/AUDIT-2026-07-15-01.md`, branch
`claude/independent-auditor-agent-nk5b6u`) · **Owner:** BA
The auditor correctly found three GREEN/implementation commits that created or
edited files under `tests/`, which the SDET/Dev split and the RED-first rule
(`CLAUDE.md`) exist to prevent. Recorded here with an explicit decision each; the
end state of every test is correct and passing, but the git history did not show
them RED-first and BA had not flagged it. **None weakens a safety invariant.**

- **`9eff0ec` feat(S-201) GREEN (Dev)** — edited `tests/a11y/conftest.py`,
  `tests/integration/test_schema.py`, `tests/safety/test_config_frozen.py`,
  `tests/safety/test_safety_invariants.py`. **Decision: accept-with-reason.** The
  change was purely `ruff --fix` isort re-ordering (no semantic change), triggered
  when the `data/` package shifted first-party import grouping. **It is still Dev
  editing `tests/`, incl. a safety test — a real deviation.** Prevention is
  already in place (DL-014 pins `known-first-party` so this churn does not recur);
  **added rule: Dev does not run `ruff --fix` over `tests/`; SDET owns test
  formatting.**
- **`b4e4cbf` feat(S-103) GREEN (Dev+SDET)** — added `test_icr_non_positive_raises`
  and `test_non_positive_curve_constants_raise` in the same commit as the
  validators they exercise. **Decision: accept-with-reason.** These *were* seen
  RED first in-session (validators temporarily stripped → tests failed → restored;
  noted in the commit body), so this is a *commit-granularity* miss (no separate
  RED commit), not green-before-red. Not re-authored: the RED observation is
  genuine and documented.
- **`790e385` feat(S-202) GREEN (Dev)** — created `tests/unit/test_clock.py` inside
  the implementation commit. **Decision: accept-with-reason.** `SystemClock`
  already existed when the test was written, so it was green-on-arrival
  (a true RED-first miss). It is a trivial coverage-completeness test for the one
  sanctioned wall-clock read (asserts `now()` returns a `datetime` within
  `[before, after]`); it guards a real property but caught no defect. Kept rather
  than deleted-and-rewritten because re-authoring a trivially-true assertion adds
  no catch-power; recorded honestly instead of relabelled.

**Prose correction (same H1):** the unqualified "RED-first throughout" claims in
`docs/traceability.md` are amended to cite this DL-017 caveat. Going forward, each
story's RED tests get their own `test(S-nnn): RED` commit *before* any impl, and
Dev never touches `tests/`.

## DL-018 — S-302 provenance correction (audit H2)
**Story:** S-302 · **Type:** provenance correction · **Owner:** BA
The server-side rejection of an absent/null `bolus_offset_min` (422) was **already
delivered by S-301's `MealCreate` schema** (`api/schemas.py`, commit `f59c32c`),
*before* the S-302 RED commit. Only the **client-side** e2e blocking (GREEN
`f10cccc`) was net-new under S-302. The end state (two-layer enforcement) is
correct; the traceability row is amended so the S-302 "RED" label is not read as
covering the already-green server assertion. The S-302 commit bodies did note
this ("server side is already enforced by S-301"); the traceability row now says
so too.

## DL-019 — INV-7 wiring cannot see a DB-level row deletion (audit H4) → S-305
**Story:** S-203 (raised) → **S-305 (fix)** · **Type:** coverage gap · **Owner:** SDET/Dev
In `data/repositories.py`, `get_rescued_meals` and `get_hypo_events` both derive
"rescued" from the **same** `hypo_treatment` flag, so a rescued meal is in the
hypo set *by construction*; the `rescued − hypo` drop-branch of
`inv7_rescued_excluded_and_retained` cannot fire via this call site. INV-7 itself
is sound (unit + 100/20 regression guard pass). But the **catastrophic** case
INV-7 names — a low disappearing from the data entirely — is a **DB-level row
deletion**, which this wiring cannot detect (it removes the row from both lists at
once). **Decision (per auditor):** fix in **S-305 (hypo-rescue capture)**, which
introduces an independent record of rescued events to reconcile rescued *rows*
against — so a count mismatch is caught without both lists sharing the
`hypo_treatment` derivation. Tracked as an S-305 acceptance item.

**✅ RESOLVED in S-305 (2026-07-15).** `hypo_rescue_log` — an append-only ledger
deliberately decoupled from `meal_event` (`meal_id` is a plain reference, **not** a
cascading FK) — now records every rescue. `get_recorded_rescue_meal_ids` returns
the **union** of currently-flagged meals and ledger entries, and `get_training_set`
feeds that union into the unchanged `inv7_rescued_excluded_and_retained`. The two
silent-loss vectors are now loud: a hard-deleted rescued meal row trips
`rescued − hypo` (drop), and a cleared `hypo_treatment` flag trips
`rescued & training` (leak). Both are covered by load-bearing tests in
`tests/integration/test_hypo_rescue.py` (row-deletion + flag-clear). The invariant
was **not** re-implemented — only the source of `rescued_meal_ids` was made truer.

## DL-020 — `iob_at_start` deferred to S-401; correction_event columns made nullable
**Story:** S-306 · **Type:** build-order deferral + schema deviation · **Approved by:** operator (2026-07-15)
S-306 captures correction-only events (REQ-013), but `iob_at_start` requires the
IOB engine — `iob_at()` over `bolus_log`, the Fiasp curve — which is **S-401
(EPIC 4, post-ship)** and does not exist yet. CLAUDE.md forbids hand-entered IOB
(must be derived) and forbids working around a missing piece. **Decision
(operator-approved):** *defer* — capture the event now with `iob_at_start = NULL`,
to be backfilled by S-401. The `07` §6 clean-signal filter already requires
`iob_at_start < 0.5`, so a NULL is **not yet clean** and is excluded from ISF
derivation by construction — loud, never a silent inclusion (guarded by
`test_clean_events_exclude_food_in_window_and_unknown_iob`). **Schema deviation
from S-201:** `correction_event.{iob_at_start, bg_after, bg_after_time}` become
**nullable** — `iob_at_start` for the deferral, `bg_after`/`bg_after_time` for the
two-phase (+4 h) capture that mirrors the meal → post-bg pattern. Migration
`b2c3d4e5f6a7`. **Out of scope, tracked:** `iob_at_start` computation → S-401; the
ISF regression + `implied_isf`/`clean_events_count` response (`05` §3) → S-501
(`cli derive-isf`).

**✅ DISCHARGED in S-306b (2026-07-16), once S-401's IOB engine landed.**
`correction_event.iob_at_start` is now **computed** — at capture from prior
`bolus_log` injections (`iob_at_start_at → features.iob.iob_at`), excluding the
correction bolus itself (strictly-before boundary); `backfill_correction_iob`
fills any events captured while it was deferred (none in production — pre-ship).
The `07` §6 clean-ISF filter now runs on a real value (high prior IOB ⇒ excluded,
low ⇒ kept). IOB stays derived, never entered — `detect_manual_iob` clean (the
reported time is bound to a local `at`, so the value derives from the log, not
from the request). ISF derivation itself remains S-502.

## DL-021 — Audit 2026-07-16-01 remediation (N1–N4); H1–H5 confirmed resolved
**Source:** `audits/HANDOFF-2026-07-16-01.md` (auditor, outside the loop) · **Audited commit:** `41d0b0e` · **Verdict:** PASS-WITH-CONCERNS (0 blocker, 1 major, 3 minor). The prior cycle's H1–H5 are all **confirmed genuinely resolved**; nothing carried forward.
- **N1 (major, SDET) — armed the now()→clinical-timestamp guard for `bg_after_time`.**
  S-306 added a new `# REPORTED` timestamp but did not register it, so the most
  important forbidden-pattern guard was blind to `bg_after_time = datetime.now()`.
  Fixed RED-first: added it to `_CLINICAL_TS`, positive assertions (assignment +
  keyword), and a **new meta-guard** — every `# REPORTED` column in
  `data/tables.py` must be in `_CLINICAL_TS`, so no future reported timestamp can
  be added without arming the guard.
- **N2 (BA) — reconciled S-306 story with what was built.** The TDD-strategy line
  claimed it would *extend* `tests/safety/test_reported_timestamps.py`; it did not.
  Corrected the story to point at the covering integration tests, and recorded the
  decision to route the now()-guard coverage through N1's schema-wide meta-guard
  (stronger, non-forgettable) rather than per-field safety cases.
- **N3 (minor, SDET) — smoke test for `python -m cli`.** The operator command
  surface (`cli/__main__.py`) had 0% coverage; added a dispatch test for
  backup/export/restore-drill + the non-sqlite-URL rejection. Now 95%.
- **N4 (minor, BA) — captured drill transcript.** Re-ran the durability drill for
  real (2026-07-16, post-S-305 10-table schema) and appended the **captured
  transcript** to `docs/durability-drills.md`; set the going-forward policy that
  future drills attach logs, not prose.
- **Explicitly NOT changed** (auditor "do not fix"): `core/safety.py` INV-7 (kept
  the flag∪ledger sourcing), `hypo_rescue_log.meal_id` plain column (no FK),
  deferred gates, `iob_at_start = NULL`, the H3 tripwire skip, and no premature
  EPIC 4+ dirs.

## DL-022 — scikit-learn pinned as a dependency (S-404)
**Story:** S-404 · **Type:** dependency addition · **Approved by:** implied by 07 §5 (spec-mandated)
The feature pipeline standardises continuous features with `StandardScaler` inside
a `Pipeline` (07 §5), which is `scikit-learn` — not previously a dependency. Added
**pinned** `scikit-learn==1.9.0` (per S-101's pinned-deps AC) plus a `mypy`
`ignore_missing_imports` override for `sklearn.*` (incomplete stubs, like
`pandas`/`statsmodels`). **Version note:** 1.9.0 is ≥1.7, where
`LogisticRegression(multi_class=…)` is removed — irrelevant here (the model is
`statsmodels` `OrderedModel`; the forbidden-pattern guard already bans
`multi_class`, so a future accidental use fails the build regardless). The scaler
is used only via `make_scaler()` and must be fit on train folds only — the leakage
tests enforce this.

## DL-023 — `iob_at` clock-skew handling deviates from the 07 §2 reference (accepted)
**Story:** S-401 / S-306b · **Type:** deliberate deviation from spec reference · **Decision:** accept as-is (audit A2)
The `07` §2 reference for insulin-on-board filters `0 < age < td` — a bolus dated
**at or after** the query time `at` contributes **0**. The shipped
`features/iob.py::iob_at` instead relies on `iob_fraction(t ≤ 0) = 1.0` and counts a
future-dated / same-instant bolus as **full** IOB. This is **deliberate** and pinned
by `tests/unit/test_iob.py` (the `f(-5)=1` clock-skew case) — the single-bolus curve
must not return NaN or >1 when a reported bolus time is slightly ahead of `at` due to
clock skew.

**Why it is safe and why we keep it:**
1. **Safe direction.** Over-estimating IOB can only *reduce* a downstream correction
   dose and can only *exclude* a correction event from the clean-ISF set (a higher
   `iob_at_start` fails the `< 0.5` filter). It never inflates a dose or admits a
   confounded event — the error, if any, is toward caution for a patient who cannot
   feel a low.
2. **Unreachable in the live path.** `iob_at_start` is computed via
   `data.repositories.boluses_before(session, at)`, which selects injections
   **strictly before** `at`. No at-or-after bolus ever reaches `iob_at` in production;
   the clamp only governs a directly-constructed call (e.g. clock-skew robustness).
3. **Precedence.** `07` wins on clinical/model matters (CLAUDE.md). Recording this
   keeps a later reader from "correcting" `iob_at` back to the §2 `0 < age < td`
   filter without realising a test pins the clock-skew behaviour — which would change
   IOB in a dosing path. **Resolution: accept as-is;** if a future story needs strict
   §2 semantics inside a summation, add the filter there and update the pinning test
   in the same change.

## DL-024 — scipy pinned as a dependency (S-503)
**Story:** S-503 · **Type:** dependency addition · **Approved by:** implied by 07 §7 (spec-mandated)
The sign-constrained OLS (`β_carb ≥ 0`, `β_ins ≥ 0`) uses
`scipy.optimize.lsq_linear`. `scipy` was already present transitively (a hard dep of
`statsmodels`/`scikit-learn`), but S-503 imports it **directly**, so it is now a
**pinned** direct dependency (`scipy==1.18.0`, per S-101's pinned-deps AC) with a
`mypy` `ignore_missing_imports` override for `scipy.*` (like `pandas`/`statsmodels`/
`sklearn`). No behaviour change — this makes an existing transitive dependency
explicit and version-locked.

## DL-025 — `method="lbfgs"` → `method="bfgs"`; absent-class handling (S-601)
**Story:** S-601 · **Type:** deliberate deviation from spec reference + flagged
data-limitation · **Approved by:** forced by the pinned toolchain (mechanical);
absent-class refusal escalated to the gate stories

**1. Optimiser.** 07 §8 writes
`OrderedModel(y_state, X, distr="logit").fit(method="lbfgs", maxiter=2000)`. Under the
pinned `statsmodels==0.14.4` + `scipy==1.18.0` that raises
`TypeError: fmin_l_bfgs_b() got an unexpected keyword argument 'disp'` — a
statsmodels/scipy interface incompatibility, **not** a modelling decision.
`models/ordinal.py::fit_ordinal` uses `method="bfgs"` instead: the **same**
maximum-likelihood objective (identical log-likelihood, identical proportional-odds
parameterisation) reached by a different quasi-Newton step. Verified empirically —
probabilities sum to 1, and `P(state ≥ 4)` is monotone in `pre_bg`. Recorded so a
later reader does not "restore" the spec's `lbfgs` and silently re-break the build.
The L2 ridge is applied inside a thin `OrderedModel` subclass (weighted `loglikeobs`;
`loglike = Σ wᵢ·llᵢ − l2_alpha·‖β_features‖²`, penalising the **feature** coefficients
only, never the thresholds) — `statsmodels` has no `fit_regularized` on `OrderedModel`.

**2. Absent-class hazard (flagged, deferred — NOT silently handled).** On a tiny
single-patient training fold a state can be **entirely unobserved**. Declaring all five
categories then leaves the missing threshold unidentifiable — the fit diverges and the
per-row probabilities stop summing to 1. `fit_ordinal` therefore models the
**observed** ordered states and reports them via `OrdinalFit.states`; it does **not**
fabricate a zero-probability column for an unseen state. Assigning `P = 0` to an unseen
**hypo** state would silently assert "this low cannot happen" — the exact silent
failure this system exists to make loud. The full 5-vector mapping, and the **refusal**
that must fire when a hypo class is missing at prediction time, are deferred to the gate
and risk-readout stories (**S-703 / S-804**), where they belong with INV-1/INV-2. This
is escalated, not resolved here.

## DL-026 — `statsmodels.api` unusable under scipy 1.18; partial-PO fitter deferred (S-602)
**Story:** S-602 · **Type:** toolchain constraint + deliberate scope deferral ·
**Approved by:** toolchain (mechanical); partial-PO deferral escalated per CLAUDE.md

**1. `statsmodels.api` is unusable under the pinned toolchain.** `import
statsmodels.api` (and thus the discrete `Logit`) fails at import time under
`statsmodels==0.14.4` + `scipy==1.18.0`: `ImportError: cannot import name
'_lazywhere' from 'scipy._lib._util'` (scipy removed `_lazywhere`). Only the direct
`statsmodels.miscmodels.ordinal_model.OrderedModel` path (used in S-601) is reachable.
The Brant test's per-threshold binary logits are therefore fit with a small,
deterministic Newton–Raphson (`models/brant.py::_fit_binary_logit`) rather than
`sm.Logit`. No behaviour compromise — the Newton fit is the exact binary-logit MLE, and
the Brant covariance is the Brant (1990) sandwich built from the fitted probabilities.
Recorded so a later reader does not "simplify" the binary fits back onto the broken
`statsmodels.api` import.

**2. Partial-proportional-odds *fitter* deferred.** 07 §8 step 2 names partial
proportional odds as the response to a Brant rejection. S-602 ships the **detection and
the typed escalation** (`ProportionalOddsViolation`, carrying the `BrantResult` whose
`violators` name exactly which slopes a partial-PO fit would free) but **not** the
partial-PO fitter itself, because: (a) the model epics are gated behind live data —
there is nothing real to reject on yet; (b) choosing to free specific slopes is a
modelling decision that CLAUDE.md says must be surfaced and made deliberately, not
defaulted by Dev; and (c) building an untested partial-PO fitter now would be
speculation. The escalation is the honest handoff: when a Brant rejection occurs on real
data, the violation object already carries which predictors to free. This is consistent
with the project's gate discipline (INV-1/INV-2) — surface the decision, do not
pre-empt it.

## DL-027 — PyMC/Bambi added; numpy repinned 2.4.6 (S-603)
**Story:** S-603 · **Type:** dependency addition (spec-mandated tool) ·
**Approved by:** user (explicit choice, 2026-07-17) over a self-contained sampler

07 §8 names **PyMC/Bambi** for the Bayesian ordinal at n ≥ 200. Neither was installed,
and the toolchain is already fragile under `scipy 1.18` (`statsmodels.api` is dead,
DL-026), so the choice between (a) a self-contained numpy/scipy sampler, (b) adding
PyMC as spec-literal, and (c) deferring S-603 (it is gated behind n ≥ 200) was put to
the user. **Decision: (b) — add PyMC.**

**What changed:**
- `pymc==6.1.0` and `arviz==1.2.0` pinned as direct dependencies. PyMC pulls a heavy
  transitive stack (`pytensor`, `numba`, `llvmlite`, `xarray`); sampling compiles a
  `pytensor` C graph, so a C++ compiler (`g++`, present on the CI runner) is now a
  build requirement. First compile dominates wall-time and is disk-cached.
- **`numpy` repinned `==2.4.6`.** `numba 0.65.1` (a PyMC transitive dep) constrains
  `numpy` to the 2.4.x line, so the previously-transitive `numpy 2.5.1` is downgraded.
  `numpy` is therefore now an **explicit pin** (it had been transitive). All prior code
  and the full suite pass under 2.4.6; one latent `mypy` `no-any-return` in
  `models/ordinal.py::loglikeobs` surfaced under the 2.4.6 stubs and was fixed
  (explicit `np.asarray` on the return) — no behaviour change.
- `mypy` `ignore_missing_imports` extended to `pymc.*`, `arviz.*` (untyped).

**INV-8 in this model.** The insulin coefficient has a `HalfNormal` prior (support
≥ 0) and enters the linear predictor with a **negative** sign, so every posterior draw
is ≥ 0 by construction — the sign constraint is the prior's support, not a post-hoc
clamp, and holds for arbitrarily confounded data. `inv8_beta_insulin_non_negative` is
still asserted on the sampled minimum so the guard bites if the prior is ever swapped
for an unconstrained one. The estimator fits at any identifiable n (to demonstrate that
credible intervals widen as n shrinks); the **n ≥ 200** rule (`MIN_BAYESIAN_N`,
`bayesian_gate_open`) governs production use, per 07 §8.

## DL-028 — RED-first / test-ownership deviations, EPIC 6 (audit 2026-07-17-01, F1) — RECURRENCE of DL-017
**Story:** cross-cutting (S-601, S-602, S-603) · **Type:** process deviation ·
**Raised by:** independent-auditor (`audits/AUDIT-2026-07-17-01.md`, branch
`claude/independent-auditor-agent-nk5b6u`) · **Owner:** BA

This is an explicit **recurrence of DL-017**: three GREEN/implementation commits again
created or edited files under `tests/`, which the SDET/Dev split and the RED-first rule
(`CLAUDE.md`) exist to prevent. The audit verdict was **PASS** and **no safety invariant
was weakened**, but one assertion was *loosened* by the implementer and the git history
looks more disciplined than the process was — the "looks done" gap the audits exist to
close. Recorded here with a per-commit decision.

- **`e746290` feat(S-601) GREEN (Dev)** — in the GREEN commit, edited
  `tests/unit/test_ordinal.py`: removed an unused `pytest` import, **weakened**
  `assert HYPO_STATES == frozenset({1, 2})` to membership checks (`1 in …`, `2 in …`,
  `3 not in …`), and added `test_prob_at_least_above_top_state_is_zero`. **Decision:
  re-authored (not merely accepted).** The weakening is the material one: a
  membership-only check would not catch a future refactor that silently adds state 4 or
  5 to the up-weighted hypo set — and those up-weighted states *are* the lows she cannot
  feel. **SDET has restored the exact assertion** `frozenset({1, 2}) == HYPO_STATES`
  (ruff-clean operand order) and adopted the added edge test as SDET-owned.
- **`bc4f462` feat(S-602) GREEN (Dev)** — added `test_too_few_states_raises` to
  `tests/unit/test_brant.py` in the GREEN commit. **Decision: accept-with-reason,
  SDET-adopted.** A legitimate edge test (the `< 3 states` guard) that adds catch-power;
  it is now marked SDET-owned. Still Dev editing `tests/` — a real commit-granularity
  deviation, not green-before-red (the guard existed and the test exercises it).
- **`305f967` feat(S-603) GREEN (Dev)** — added `test_insulin_col_out_of_range_raises`
  and `test_too_few_states_raises` to `tests/unit/test_bayesian_ordinal.py` in the GREEN
  commit. **Decision: accept-with-reason, SDET-adopted.** Both pin real pre-sampling
  guards; marked SDET-owned.

**Re-affirmed rule (unchanged from DL-017):** *Dev never touches `tests/`.* Each story's
RED tests land in their own `test(S-nnn): RED` commit, seen to fail, **before** any
implementation; coverage-completeness edge tests that emerge during GREEN are the SDET's
to author or adopt in a separate commit, never folded into the Dev GREEN commit. The
recurrence indicates the rule needs active guarding, not just restating — future GREEN
commits touching `tests/` should be treated as a process failure at commit time.

**Prose correction:** the EPIC 6 traceability lines for S-601/S-602/S-603 are qualified
to cite this DL-028 caveat; "RED-first" for those three stories is **commit-granularity
qualified** (the RED tests were real and seen to fail, but edge tests / one loosened
assertion landed in the GREEN commits), not unqualified.

## DL-029 — Commit-attribution hygiene for doc changes (audit 2026-07-17-02, M1)
**Story:** cross-cutting (F1 remediation) · **Type:** process note · **Raised by:**
independent-auditor (`audits/AUDIT-2026-07-17-02.md`) · **Owner:** BA

The audit verdict was **PASS**; the single minor is attribution hygiene. The F1
remediation commit **`eec1e7f`** is labeled `test(F1): SDET re-pin exact HYPO_STATES
frozenset + adopt EPIC 6 edge tests`, but it also edited **BA-owned docs** —
`docs/decision-log.md` (+43, the DL-028 body) and `docs/traceability.md` (+7). Folding
BA doc changes into a `test(...)`-labeled commit is itself the one-commit cross-owner
blur that DL-028 says to treat as a commit-time process failure — and doing it *inside*
the DL-028 fix quietly weakens the who-did-what signal the audits reconstruct from commit
attribution.

**Decision — accept `eec1e7f` as-is + going-forward rule (no history rewrite).** The
substance of DL-028 and the traceability edits is correct and stays; rewriting pushed
history is neither needed nor wanted. Going forward: **BA-owned changes (`docs/**`, the
decision log, the traceability matrix) land in a `docs(...)` BA commit, distinct from
`test(...)` (SDET) and `feat(...)` (Dev) commits** — the same commit-per-owner rule that
already governs `tests/` and `core|features|models|...`. This DL entry is itself an
instance of the rule (a lone `docs(...)` commit). Attribution is a safety signal: a fix
that blurs ownership is not a fix.

## DL-030 — Story-doc commit attribution (audit 2026-07-17-03, H3)
**Story:** cross-cutting (process) · **Type:** process decision · **Raised by:**
independent-auditor (`audits/AUDIT-2026-07-17-03.md`) · **Owner:** BA

DL-029 says BA-owned `docs/**` changes land in a `docs(...)` BA commit, yet every EPIC 8
**story doc** (`docs/stories/S-80x.md`) was created inside the SDET `test(...)` RED commit.
The decision-log and traceability halves of DL-029 are followed correctly; this settles
only `docs/stories/`.

**Decision — option (b): the story doc lands in its own `docs(...)` BA commit BEFORE the
RED test.** This matches the CLAUDE.md TDD loop step 1 ("BA restates the story… writes
`docs/stories/S-nnn.md` **before** work begins") and step 2 (SDET writes the RED test).
Bundling the story restatement into the `test(...)` commit blurred the BA/SDET boundary;
going forward the sequence is: `docs(S-nnn): story` (BA) → `test(S-nnn): RED` (SDET) →
`feat(S-nnn): GREEN` (Dev) → `docs(S-nnn): traceability` (BA). Applied from **S-901**
onward. The EPIC 8 story docs are not re-committed (no history rewrite; DL-029 principle);
their statuses were corrected to Done in a `docs(...)` BA commit (H1).

## DL-031 — mypy gate scope (audit 2026-07-17-03, H4)
**Story:** cross-cutting (infra note) · **Type:** documentary · **Owner:** BA
`mypy --strict` is enforced over the **source packages only** —
`core api data cli features models prescribe` (the CI "Types" step and
`pyproject.toml [tool.mypy]`). It does **not** cover `tests/` or `alembic/versions/`;
`mypy --strict .` reports errors there (e.g. a couple in `tests/safety/test_readout.py`)
which are **outside the gate by design** (tests use fixtures/`type: ignore` pragmatically;
migrations are generated). "mypy clean" in this project means the source packages type-check
under `--strict`, unambiguously — not the whole tree.

## DL-032 — OQ-1/OQ-2 resolved: ICR/ISF clinically confirmed — Gate 2 human gate cleared (S-901)
**Story:** S-901 (EPIC 9) · **Type:** clinical constant confirmation (human gate) ·
**Confirmed by:** operator relaying the endocrinologist's sign-off, 2026-07-17 · **Owner:** BA

The prescriptive module (EPIC 9) was blocked on **two gates**: the code gate (S-703, green
since 2026-07-17) **and** the human gate — an endocrinologist confirming ICR (OQ-1) and ISF
(OQ-2). The code gate being open (`gate2_status(icr=…)`) is **not** sufficient; a fabricated
or unilaterally-chosen ICR would be a top-severity safety defect. This entry records the
human gate being cleared.

**Confirmed values (2026-07-17):**
- **ICR = 9 g/U** (OQ-1). Within the expected 7–10 g/U band; not the 500/60 ≈ 8.3 heuristic —
  the clinician's figure.
- **ISF = 30 mg/dL/U** (OQ-2). Confirms the population heuristic for this patient.
- **Correction target = 135 mg/dL** (OQ-6) — unchanged, still valid.

**How the values live (updatable later, by design):** ICR/ISF/target are stored in the
**versioned, append-only `patient_profile`** (REQ-054), not hardcoded anywhere. The
bolus calculator reads them from the profile as parameters; there is no `icr = 9` literal in
`prescribe/`. To update them later, the operator appends a **new `patient_profile` version**
(the old one is retained for audit) — no code change. `01-prd §9` OQ-1/OQ-2 marked RESOLVED,
OQ-6 CONFIRMED.

**This unblocks S-901.** The calculator uses the clinical formula only (07 §11 — no ML in the
dose path) behind `recommend_bolus`'s live Gate-2 check, with INV-1/INV-3/INV-4 enforced.

## DL-033 — EPIC 10 added: Integration, UI & End-to-End Validation (approved scope addition)
**Story:** EPIC 10 (S-1001..S-1005) · **Type:** approved scope addition · **Requested by:**
operator, 2026-07-17 · **Owner:** BA

After the build reached BUILD COMPLETE (EPICs 1–9), the operator asked for (a) a UI over the
model/prescriptive surfaces so the system can be seen and validated, and (b) an end-to-end
test over synthetically generated data proving the full cycle works. This is a **sanctioned**
scope addition (requested by the operator), recorded here rather than back-filled — BA's job
is to make the addition visible, not silent.

**Why these surfaces had no UI (not an oversight).** EPICs 5–9 delivered the shadow report,
patient readout, and bolus calculator as tested Python returning data structures; the HTML
render layer was **deferred by design** (S-804/S-805 presentation notes) on the same gate
discipline as S-703 — *there is nothing patient-visible to render before Gate 1.* EPIC 10
builds those render layers now, explicitly.

**The load-bearing guarantee: building a UI does not open a gate.** S-1002 (patient readout)
calls `require_gate1` first (INV-2); S-1003 (bolus) calls `require_gate2` first (INV-1).
Before those gates the screens render the refusal / baseline state — never a blank, never a
dose. The invariants stay in `core/safety.py`; the UI composes them, it does not re-implement
or weaken them. The bolus screen shows the full arithmetic, frames the number as *a
suggestion for review*, and **does not autofill the dose into any action**.

**Synthetic-data guardrail (S-1004).** The generator is for tests/demos only. It honours
reported-timestamp discipline (ADR-8) and is **never importable into `core`/`models`/
`prescribe`/`api` and never presented as real patient data** — a forbidden-import guard
enforces this, so synthetic rows can never be mistaken for hers or fed to a production fit.

**New requirements:** REQ-055 (rendered shadow dashboard), REQ-056 (seeded synthetic-data
generator), REQ-057 (end-to-end cycle test). Patient-readout and bolus rendering trace to the
existing REQ-040 and REQ-041–043; EPIC 10 adds their render layer without changing the gates.

**Not started.** EPIC 10 is backlog only at this entry — no code yet. Each story still runs
the full TDD loop (SDET RED first); the three `[SAFETY]` stories (S-1002/S-1003/S-1005)
require a written invariant argument in their PR.

## DL-034 — EPIC 10 review: operational-spine gaps added (S-1006..S-1010, S-1004 reclassified)
**Story:** EPIC 10 · **Type:** backlog review / gap remediation · **Date:** 2026-07-18 ·
**Requested by:** operator ("review the newly added items") · **Owner:** BA

The first-cut EPIC 10 (S-1001–S-1005) was reviewed against the full end-to-end **usage
sequence**. It scoped the UI render layer, the synthetic generator, and the E2E test, but
**assumed the sequence's operational spine rather than storying it.** Five gaps were found;
stories added. **No implementation started — backlog/spec only.**

**The load-bearing finding (G1).** The sequence pivots on the operator *manually promoting*
the model at Gate 1. In code, `gate1_status()` opens automatically on
`valid_meals ≥ 150 ∧ model beats baseline`. The schema has `ModelArtifact.is_promoted`
(commented *"manual only"*) but **nothing reads it** (only the migration references it). So the
manual-promotion gate exists on paper and in the data model but was never wired. This also
corrects an overstatement made to the operator in conversation ("promotion is never
automatic") — today it is. → **S-1006**.

**These are conformance fixes, not new gate decisions.** `07 §Retraining` (the clinical spec,
which wins on clinical matters) already states *"Monthly refit, trailing 6 months, older data
down-weighted. Promotion is manual, on hypo recall."* REQ-048 already requires *"Shadow mode
≥ 90 days."* The team is **not choosing** any threshold here — 90 days, monthly, manual-on-
hypo-recall all trace to existing spec/requirements. The stories bring the code up to the
spec; they **tighten** Gate 1 (add a precondition), never relax it, so this is remediation,
not a gate relaxation requiring escalation.

**Gaps and stories:**
- **G1 → S-1006 [SAFETY]** — wire `is_promoted` into `gate1_status`; open only with an
  explicit audited manual promotion. REQ-058 (new).
- **G2 → S-1007 [SAFETY]** — enforce the ≥ 90-day shadow clock as a Gate-1 precondition;
  gives REQ-048 its first covering story (previously enforced nowhere).
- **G3 → S-1008** — the live per-meal prediction wiring (features → model → guardrails →
  persist INV-9 → serve); the runtime loop was unit-built but never orchestrated on a real
  meal. REQ-059 (new).
- **G4 → S-1009** — the monthly refit cadence from `07 §Retraining`, writing a new unpromoted
  artifact. REQ-060 (new).
- **G5 → S-1010** — an operator surface to append a new `patient_profile` version (the
  "updatable ICR/ISF later" ask); constants versioned per REQ-054 but no append action
  existed. REQ-061 (new).
- **Q1 → S-1004 reclassified `[SAFETY]`** — its "fake data never reaches a production fit / is
  never mistaken for hers" guard is a safety property; moved into `tests/forbidden/` with a
  written argument.
- **Q2** — an explicit EPIC 10 build order added (S-1002/S-1003 depend on S-1008; S-1005 on
  all).

**Why now / traceability.** Recorded the day of the review (2026-07-18) so the code-vs-spec
divergence is visible rather than silently carried. Each new story runs the full TDD loop,
RED first; the `[SAFETY]` ones (S-1006/S-1007) need a written invariant argument in their PR.
The exact promotion mechanics and the shadow-clock start definition remain for the operator to
confirm at build time, but the direction is spec-mandated.

## DL-035 — Gate 2 / INV-1 (ICR gate) to be retired — de-gated to a plain profile value
**Story:** S-1011 (EPIC 10) · **Type:** safety-invariant removal (planned) · **Date:**
2026-07-18 · **Requested by:** operator · **Owner:** BA · **Status:** PLANNED — not executed.

The operator has decided the clinician-confirmed-ICR **gate** (Gate 2, **INV-1**) is not
wanted. This entry records the decision and its rationale; **no code, test, or invariant is
changed at this entry.** Execution (S-1011) is gated on an explicit operator "go".

**Decision.** Retire Gate 2 / INV-1 **as a gate**. ICR / ISF / target become ordinary
versioned `patient_profile` parameters the bolus calculator reads directly — no
confirmation ceremony, no hard-disable of the prescriptive module. This is a de-gating, not a
change to the ICR value (still 9 g/U per DL-032, which stands).

**Chosen fallback (operator, 2026-07-18): keep a basic input check.** `recommend_bolus` will
raise an ordinary **`ValueError`** — explicitly **not** a `SafetyViolation`/`GateNotPassed` —
if the ICR is missing or `≤ 0`, so the formula can never divide by null or a nonsensical
ratio. The confirmation ceremony is removed; the arithmetic-safety check is not.

**Kept:** INV-3 (never negative; cap-and-flag a typo), INV-4 (no bolus below BG 80), the
no-ML-in-the-dose-path property, and Gate 1 / INV-2 (patient-visible output — a separate
mechanism). `GateNotPassed` stays (Gate 1 uses it). **INV-1 is marked retired; INV-2…9 are
not renumbered** (renumbering across the repo would be error-prone).

**Honest safety note.** This permanently lowers a safety floor the project deliberately built:
CLAUDE.md named the prescriptive gate "the most dangerous code in the system … the gate *is*
the feature." After removal, the calculator will compute a dose from whatever ICR sits in the
profile, with **no clinician-confirmation checkpoint** — only the present/positive `ValueError`
and the retained INV-3/INV-4. Recorded here as a deliberate, operator-authorised decision so
the change is loud, not silent. Residual mitigations: the ICR lives in the **versioned,
append-only, auditable** profile, and the basic input check remains.

**Supersedes.** The *gate* portion of DL-032 (which cleared Gate 2 by confirming the ICR). The
confirmed ICR **value** from DL-032 is unaffected — only its status as a gate is removed.

**Traceability.** REQ-041 (INV-1) is slated for retirement by S-1011; the removal is not yet
reflected in the invariant tables (CLAUDE.md, `07 §11`, `traceability.md`) — those edits are
part of S-1011's execution, deliberately deferred until the operator's go.

## DL-036 — Version gate: `v1.0.0-epic9` tagged as the pre-EPIC-10 rollback baseline
**Story:** release engineering (EPIC 10 prerequisite) · **Type:** process / release ·
**Date:** 2026-07-18 · **Requested by:** operator · **Owner:** BA

EPIC 10 changes surfaces that currently work, and **S-1011 removes a safety invariant**.
Before any of that lands, the operator asked for a version gate so there is an unambiguous,
verifiable rollback path. This entry records it.

**What was tagged.** `v1.0.0-epic9` — an annotated tag on the complete EPICs 1–9 build:
445 tests, ~99.7% coverage, `ruff` + `mypy --strict` clean, CI green. Product code at the tag
is **identical to `4bf5289`** (the S-901 traceability commit that closed EPIC 9); the commits
in between are documentation and the demo script only — verified with
`git diff 4bf5289..HEAD -- core prescribe models features data api cli tests` returning empty.

**Versioning scheme adopted.**
- A released gate carries a plain version (`1.0.0` in `pyproject.toml` **and**
  `core/__version__`, kept in sync).
- The working branch carries a `.dev` version (`1.1.0.dev0`) whenever it is ahead of the last
  gate, so the running code self-reports whether it is a released baseline or in-progress work.
- `CHANGELOG.md` (new) records what each gate contains, **including its known gaps**, and the
  rollback commands. README gains a Versioning & rollback section.

**Known gaps recorded at the baseline, deliberately.** The changelog states plainly that at
`v1.0.0-epic9` Gate 1 opens *automatically* on its metric conditions, `is_promoted` is read
nowhere, and REQ-048's ≥90-day shadow period is unenforced (S-1006/S-1007 fix these). A
rollback target must be documented honestly, including what is wrong with it — rolling back to
a baseline whose weaknesses are undocumented is not a safety net.

**Rollback contract.** `git checkout v1.0.0-epic9 && ./scripts/verify.sh`. Tags are immutable;
nothing done in EPIC 10 can alter what this tag points to. Any rollback is verified by the
CI-equivalent script before being trusted.
