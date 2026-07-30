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
2026-07-18 · **Requested by:** operator · **Owner:** BA · **Status:** ✅ **EXECUTED 2026-07-18** (S-1011).

The operator has decided the clinician-confirmed-ICR **gate** (Gate 2, **INV-1**) is not
wanted. This entry records the decision and its rationale; **no code, test, or invariant is
changed at this entry.** Execution (S-1011) was gated on an explicit operator "go", which was given the same day; see the execution note at the end of this entry.

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

**What was gated.** The complete EPICs 1–9 build: 445 tests, ~99.7% coverage, `ruff` +
`mypy --strict` clean, CI green — re-verified locally immediately before the gate commit, not
assumed from the earlier CI run. **Behavioural code at the gate is unchanged from `4bf5289`**
(the S-901 traceability commit that closed EPIC 9); the only delta across the product packages
is the one-line `__version__` bump in `core/__init__.py`, everything else in between being
documentation and the demo script (verified with `git diff 4bf5289 7a7c3bf -- core prescribe
models features data api cli tests`).

**Rollback drill executed (2026-07-18).** Cloned the branch fresh, checked out `7a7c3bf`,
confirmed the tree and version resolve correctly. The rollback path is tested, not asserted —
the same discipline as the S-304 restore drill.

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

**Rollback contract.** `git checkout 7a7c3bf && ./scripts/verify.sh`. Any rollback is verified
by the CI-equivalent script before being trusted — an unverified rollback is an assumption,
not a safety net.

**Constraint hit: the tag could not be pushed.** The annotated tag `v1.0.0-epic9` was created
locally, but this session's git proxy returns **HTTP 403 for tag refs** (branch refs only);
four attempts failed. Since the build container is ephemeral, a local-only tag would be lost.
**The authoritative marker is therefore the commit SHA `7a7c3bf`**
(`7a7c3bf9003d2ac2c39d018eea409bfd3967bf2e`), which *is* pushed on the branch and is equally
immutable. CHANGELOG and README lead with the SHA and give the one-liner to publish the tag
from a normal clone. Recorded rather than worked around: the environment restriction is real
and the rollback path does not depend on the tag existing.

## DL-037 — EPIC 10 spec updates landed (the behaviour docs, not just the plan)
**Story:** EPIC 10 (prerequisite to building S-1001…S-1010) · **Type:** specification ·
**Date:** 2026-07-18 · **Requested by:** operator · **Owner:** BA

DL-033/034 added EPIC 10 to the **planning** docs (backlog, PRD register, traceability), but
the nine **behaviour** specs were untouched since the initial commit. A developer picking up
S-1002 would have found a backlog entry and nothing else — no screen spec, no API contract, no
state-machine rule. This entry records closing that gap **before** any EPIC 10 code.

**Updated:** `03-state-model` (Gate 1 gains manual promotion + the 90-day shadow clock;
Gate 2 marked retiring), `05b-ui-ux-spec` (dish picker/quantities/macros + snack; **IOB shown,
never typed**; the report card's three-layer metric presentation; the promotion control),
`02-functional-spec` (F-1.1 composition + snack; **F-4.4 the five rendered readout states**;
F-5.1 retirement note; F-6.2 dual presentation; **F-7.1 promotion**), `05-api-contract`
(`POST /api/operator/promote` with `409 PRECONDITIONS_NOT_MET`; bolus retirement note),
`09-test-plan` (**§2.1 end-to-end/chain-level layer**, §2.2 synthetic-data rules),
`04-data-model` (`is_promoted` as a **gate input**; the shadow clock derived from
`prediction_log`), `06-tech-architecture` (**§6.1 the live prediction path**; refit never
promotes), `00-glossary` (promotion, shadow clock, report card, synthetic data).

**Two findings worth recording.**
1. **The specs were already ahead of the code.** `03 §3` has *always* listed
   `shadow_mode_days ≥ 90` and acceptable calibration as Gate 1 conditions; `02 F-5.2` has
   always said *"IOB is computed, never entered."* So S-1007 and the derived-IOB requirement
   are **conformance work, not new scope** — the code under-implements a spec that was right.
   Each affected section now carries an explicit code-vs-spec status note rather than leaving
   the divergence silent.
2. **The prototype diverged from a standing safety rule.** Its bolus screen let IOB be *typed*;
   `05b §6.0` now states the rule the build must follow — IOB is displayed read-only with its
   provenance, and a typed IOB is a forbidden pattern with an AST guard (S-105).

**Gate 2 handled without pre-empting S-1011.** Every Gate-2 section is annotated *"retiring
under S-1011"* rather than expanded or deleted. Expanding would be wasted work; deleting would
execute a safety-invariant removal the operator has explicitly held (DL-035, "prepare only").

**Story docs remain just-in-time.** Per the CLAUDE.md loop, BA writes `docs/stories/S-nnn.md`
at the start of each story. Writing all eleven now would be speculative and would rot.

### DL-035 execution note (2026-07-18)
**Operator go given; S-1011 executed the same day.** Delivered exactly as planned, TDD-first:
BA story + written safety argument → SDET RED (11 failures seen) → Dev GREEN → BA docs sweep.

- **Removed:** `inv1_prescriptive_requires_gate2`, `Gate2Status`, `gate2_status`,
  `require_gate2`, and the gate call in `prescribe/bolus.py`. Removed, **not left dormant** —
  tests assert the symbols are absent, because a leftover gate function invites re-wiring.
- **Added:** a plain `ValueError` in `recommend_bolus` for a missing/`<= 0` ICR, raised before
  any arithmetic. A **discrimination test** asserts it is neither a `SafetyViolation` nor a
  `GateNotPassed` — pinning the *kind*, so a future refactor cannot quietly reinstate a gate.
- **Renamed:** `ClinicalConfig.prescriptive_enabled` → `icr_present` (an "enabled" flag that
  enables nothing is a misreading hazard in a safety system).
- **Unchanged, deliberately:** INV-3 (cap-and-flag, never negative), INV-4 (BG-80 refusal),
  the 5 golden doses, carbs/IOB monotonicity, the no-`models`-import AST guard, and
  **Gate 1 / INV-2** in full. `GateNotPassed` remains — INV-2 uses it.
- **INV-1 is marked retired everywhere and the number is NOT reused.** INV-2..INV-9 keep theirs.

**Verified:** 442 tests pass, 99.73% coverage, `ruff` clean, `mypy --strict` clean.
**Rollback:** `git checkout 7a7c3bf` (`v1.0.0-epic9`), the pre-EPIC-10 baseline (DL-036).
## DL-038 — Provenance: this project began as a Markov-chain design; why each mechanism was replaced
**Story:** origin record (retrospective) · **Type:** provenance + design rationale ·
**Date:** 2026-07-18 · **Raised by:** operator ("check for deviation from the original") ·
**Owner:** BA · **★ REVISIT MARKER: see `01-prd.md` OQ-8 and `10-backlog.md` §REVISIT.**

The source document — *"Blood sugar prediction using markov chain"* (operator-supplied, read in
full, 2026-07-18) — is where this project and its name come from. Until now **no document
recorded that origin**, so the rationale for departing from it lived only in CLAUDE.md's
forbidden-pattern table, which never names the design it is rejecting. This entry closes that
gap. **It changes no code.**

**The goal is preserved exactly.** The source asks: *"Given my current pre-meal blood sugar and
what I am about to eat/inject, what is the probability distribution of my blood sugar in 2
hours?"* That is what the system answers, with the same 5-state output vector. Every requested
feature survived: carbs, protein, fat, bolus, basal, meal-type one-hot (breakfast as the
reference level, as specified), exercise duration and intensity. Fingersticks-not-CGM — the
operator's own constraint — is honoured.

**The mechanism was deliberately replaced. Six deviations, each with its reason:**

| # | Source design | Built | Reason |
|---|---|---|---|
| 1 | `for state in range(1,6): fit(...)` — one model per pre-meal state | **One pooled model**, `pre_bg` continuous | ★ **The safety-critical one.** The source's own code falls back to `None` when a state has < 10–15 rows. At 150 meals with its own assumed 65 %-State-3 distribution, States 1 and 2 get ~7 and ~15 rows — so it would answer *"insufficient historical data"* **for exactly the hypo states the system exists to predict.** It would work from target range and go silent when she is already low. |
| 2 | `multi_class='multinomial'` | **Ordinal** (`OrderedModel`) | Multinomial treats State 1 and State 5 as equally distant from State 3; the ordering is load-bearing. Also `multi_class` was removed in sklearn ≥ 1.7 — the source code no longer runs. |
| 3 | Pre-meal **state** (binned) as the conditioning input | Pre-meal BG **continuous** | Binning discards resolution precisely where it matters: 79 and 55 are both "State 2" and are not the same risk. |
| 4 | `exercise_intensity` as numeric **0/1/2** | **One-hot + duration interactions** | The source states intense exercise "can cause a temporary rise", then encodes 2 > 1 > 0 — which mathematically forbids the effect it just described. An internal contradiction in the source. |
| 5 | **Raw daily basal dose** as a feature | **EWMA, 25 h half-life** | Tresiba acts ~42 h and reaches steady state in 3–4 days; today's dose is not today's effect. |
| 6 | `classification_report` / accuracy; `train_test_split(random_state=42)` | **Hypo recall @ fixed FAR, Brier, calibration, Clarke grid; forward-chaining temporal CV** | On the source's own 65 %-State-3 distribution, always predicting State 3 scores ~65 % accuracy and catches **zero** lows. And because basal is constant within a day, a random split puts same-day meals in train and test — the model looks brilliant and is useless. |

**Not in the source, added here:** reported-vs-logged timestamps (ADR-8), derived IOB, INV-7
hypo-rescue retention, pre-bolus timing, fibre/net carbs, correction events, the gates,
guardrails, kill switch, prediction log, backup + restore drill, and the bolus calculator.

**One refusal worth recording.** The source closes by offering to *"expand this model to give
optimal insulin dose recommendations instead of just predicting risks."* This build declines
permanently: **no ML in the dose path** (AST-enforced). Given deviation #6 — a leakage-prone,
accuracy-scored model that would look excellent — inverting it into dosing advice would have
been the most dangerous thing the project could do. INV-8 (`β_insulin ≥ 0`) exists for the same
reason: in observational data bolus is *chosen in response to* carbs and BG, so a naive fit
learns that insulin raises glucose. The source does not mention confounding by indication.

**Is it still a Markov chain?** In the sense the source meant — a transition model
`P(post-state | pre-state, inputs)` with regression-parameterised probabilities — **yes, and the
built model is a generalisation of it**: it conditions on pre-BG continuously and pools the rows
into one ordinal fit. Bin the pre-BG and a transition matrix is recoverable. Strictly, there is
**no transition matrix and no memorylessness assumption**, and the latter would be wrong here:
IOB and prior meals mean the past demonstrably does not wash out.

**Open deviation requiring clinical sign-off:** State 2's upper bound was moved **70 → 79 mg/dL**
(State 3 starts at 80). Deliberate — it buys a warning band for someone who cannot feel a low —
but it is a **clinical constant and remains unconfirmed**. Tracked as **OQ-5**, unchanged.

**Naming.** "BG-Markov" comes from this source document. The name is retained as a codename; the
glossary now states plainly that the model is an ordinal logistic regression and that no Markov
process is modelled, so no future reader infers transition modelling that is not there.

## DL-039 — S-1004: the synthetic generator lives in a top-level `synthetic/`, not `tests/`
**Story:** S-1004 (EPIC 10) · **Type:** placement deviation from the story text · **Date:**
2026-07-18 · **Owner:** BA

`10-backlog.md` S-1004 says the generator *"lives under `tests/` / `scripts/` fixtures."* It will
instead live in a new top-level package **`synthetic/`**. Recorded because it is a deviation from
a written AC, not because it is contentious.

**Reasons, both process-level:**
1. **Role separation.** `tests/` is SDET's absolutely (CLAUDE.md). A generator under `tests/`
   would be authored *and* tested by SDET — self-marking homework, exactly what the RED-first
   loop prevents. As a top-level package it is **Dev-owned, SDET-tested**, and the loop holds.
2. **`scripts/` must not import from `tests/`.** `scripts/demo_end_to_end.py` will consume the
   generator; a script importing a test package normalises putting `tests/` on the production
   path — the opposite of this story's intent.

**The safety property is unchanged and still structural.** The `tests/forbidden/` guard
(`detect_synthetic_import`, S-105 lineage) asserts no production package — `core`, `features`,
`models`, `prescribe`, `data`, `api`, `cli` — imports `synthetic`. Moving the code did not weaken
the guard; it changed what the guard names.

**Toolchain:** `synthetic/` joins the `mypy --strict` scope. It is **not** added to the coverage
gate — it is fixture code, covered by its own tests, and adding it would dilute a gate that
exists to protect `core`/`features`/`models`/`prescribe`.

## DL-040 — S-1007: the shadow clock is a derived count with an injected `now`
**Story:** S-1007 [SAFETY] (EPIC 10) · **Type:** design record + one process note · **Date:**
2026-07-18 · **Owner:** BA

REQ-048 (*"shadow mode ≥ 90 days before patient-visible output"*) has existed since the PRD and
was **enforced nowhere** — no code read it, no test covered it. That is a visible gap by this
project's own rule, and it is now closed. Recorded because the *shape* of the fix is the safety
property, not the number 90.

**Derived, never stored.** `data/repositories.py::shadow_days` computes whole days from the
earliest `prediction_log.created_at` to `now`. The obvious alternative — a `shadow_complete`
boolean on `model_artifact` — would be written once, by whoever ran the migration or the
backfill, and would then be true forever regardless of what the data said. Nothing in a green
build would reveal it. This is the same principle as **ADR-7** ("gates are evaluated live, never
cached"), applied to a column instead of a cache. `tests/integration/test_shadow_clock.py`
asserts **no table carries a `shadow*` column at all**, so the temptation is closed structurally
rather than by convention.

**`now` is injected.** Two reasons, both load-bearing: `core/clock.py` is the single sanctioned
wall-clock reader (**ADR-8**), and an injected `now` makes the day-89/day-90 boundary testable
without waiting a quarter. A signature test pins `now` as keyword-only with no default — a
default would be a wall-clock read wearing a parameter's clothes.

**Fails closed, clamped at zero.** Clock skew, a restored backup, or a future-dated row can put
`now` behind the earliest prediction. The answer is `0` — *not yet* — never a negative number a
later `>=` might mishandle.

**`SHADOW_MIN_DAYS = 90` is named and traced to REQ-048.** `90` as a literal inside a condition
invites a future reader to tune it. Named and commented, changing it is visibly *changing a
requirement* — an escalation, not a code change.

**Time is never evidence.** The shadow clock **joins** volume, beats-baseline and manual
promotion; it substitutes for none of them. Tests assert 500 shadow days with 149 meals, or with
recall ≤ baseline, or unpromoted, all stay **closed**. `Gate1Status` now reports `shadow_days`
and `meets_shadow_period` so the operator dashboard (S-1001) can render *"day 61 of 90 — 29 to
go"*; a gate whose remaining distance is invisible invites someone to go looking for a bypass.

**`prescribe/gates.py` stays DB-free.** It still imports only `core.safety`. The gate is a pure
function of live inputs the caller reads fresh — which is what makes "never cached" structurally
true rather than a convention. The DB read lives in `data/repositories.py`.

**Process note (recorded, not glossed).** The S-1007 RED commit updated `tests/safety/test_gates.py`
but missed `tests/safety/test_readout.py`, which builds `Gate1Status` fixtures directly. Dev does
not edit `tests/` (CLAUDE.md; DL-017/DL-028 lineage), so the call-site fix was made in a **second
SDET commit** rather than folded into the GREEN commit — and it was used to add a real case:
everything earned except the shadow period (day 89) must still raise `GateNotPassed`. The RED for
that commit was seen with the product change stashed.

**Guards seen to fire (adversarial verification, then reverted).** Removing the `max(0, …)` clamp
failed the backwards-clock and future-row tests; adding a `shadow_complete` column failed the
stored-flag test; giving `shadow_days` a default failed the required-argument test. A guard nobody
has watched fire is not a guard.

**Scope.** This does not make Gate 1 open. Ninety days is a precondition, and all four conditions
must hold.

## DL-041 — Correction: Gate 1 has **five** spec conditions, not four; calibration is unenforced
**Story:** found during S-1001 scoping · **Type:** ★ **correction of a prior claim** +
escalation · **Date:** 2026-07-18 · **Owner:** BA

**The correction.** The S-1007 closing note (DL-040, and the `03 §3` code-vs-spec box) stated
that the gate diagram and `gate1_status()` *"now agree"* and that S-1007 closed *"the last
code-vs-spec divergence in `03 §3`"*. **That was wrong.** `03 §3` lists **five** Gate-1
conditions and `04 §9` repeats them:

```
n_valid_meals ≥ 150  ∧  hypo_recall > baseline  ∧  calibration acceptable (held-out)
                     ∧  shadow_mode_days ≥ 90   ∧  is_promoted
```

`gate1_status()` implements **four**. `calibration acceptable (held-out)` is enforced nowhere.
The claim is corrected in `03 §3`, `04 §9`, the traceability matrix and `docs/stories/S-1007.md`
rather than quietly dropped — a wrong "we're done" note is worse than the gap it hides, because
the next reader stops looking.

**Why it is an escalation, not a story to just build.** *"Acceptable"* has **no defined
threshold anywhere in the spec** — not in `03`, not in `04`, not in `07`. Choosing one is a
clinical acceptance decision (CLAUDE.md: *"a clinical constant needs choosing or changing"* →
escalate). The evidence already exists: `models/metrics.py::reliability_curve` produces the
held-out reliability curve. What is missing is the **rule** over it: max or mean absolute gap
between predicted probability and observed frequency, across which bins, with what minimum bin
count. **No number was invented to unblock this.** Raised as **OQ-9**; story **S-1012** is
written and explicitly **BLOCKED**.

**Why this does not weaken Gate 1 today.** The gate is a *conjunction*. A missing condition can
only ever make it **more permissive** than the spec, never less — and the four enforced
conditions hold it shut today (Gate 1 is closed; nothing is promoted). So the exposure is real
but bounded, and it is now visible rather than silent.

**How S-1001 handles it.** The operator dashboard renders the checklist with **all five**
conditions, the fifth marked *"not yet enforced — awaiting OQ-9"*, linked to this entry. The
alternative — showing four and calling it the list — would put a *complete-looking* checklist
on the exact screen where a human decides to put someone who cannot feel a low in front of a
model. A visible gap on that screen is the point.

**Process note.** This was found by reading the spec diagram line-by-line against the function
signature while scoping the next story, not by a failing test. Nothing in the suite could have
caught it: a condition that was never written cannot fail. That is the standing weakness of
requirement-level coverage, and the traceability matrix is the only instrument that addresses
it — which is why an uncovered REQ is treated as a visible gap by this project's own rule.

## DL-042 — OQ-9 resolved: the Gate-1 calibration rule (operator-approved)
**Story:** S-1012 [SAFETY] · **Type:** clinical acceptance threshold — **escalated and
answered**, not decided by the team · **Date:** 2026-07-18 · **Approved by:** the operator,
explicitly, in response to a written proposal · **Supersedes the blocked state in DL-041**

**Standing direction from the operator (2026-07-18):** *"don't depend on an endocrinologist for
anything."* Clinical constants are therefore escalated **to the operator**, who decides. This
does not change CLAUDE.md's rule — a clinical constant is still never chosen by Dev or SDET —
only who the escalation goes to. The BA's job becomes putting a concrete, plainly-worded
proposal in front of the operator rather than parking the question. **OQ-1/2/6 were already
resolved this way (DL-032).** The `01-prd.md §9` list is retitled accordingly.

### The question
`03 §3` and `04 §9` both list `calibration acceptable (held-out)` as a Gate-1 condition. No
document defined *"acceptable"*, so it was enforced nowhere (DL-041). **What is the rule?**

### The answer (approved as proposed)

1. **The hypo probability only** — `P(state ≤ 2)`. That is the number a warning is made of and
   the number she would act on. Calibrating all five class probabilities would dilute the one
   that matters into four that do not.
2. **Three buckets:** `< 0.20`, `0.20–0.50`, `> 0.50`. **Not ten.**
3. **A bucket is judged only at `≥ 20` predictions.** Below that, the observed rate is noise.
4. **Asymmetric tolerance on `|claimed − observed|`:**
   - **≤ 0.10 when the model UNDERSTATES the risk** — said 20%, happened 35%. It told her she
     was probably fine and she was not. **This is the dangerous direction.**
   - **≤ 0.20 when it overstates** — said 50%, happened 32%. A warning that did not pan out
     costs her a fingerstick. That is not a harm.
5. **Fails closed:** if no bucket reaches 20 predictions, calibration is **not acceptable**.
   *Cannot judge* means *do not open*.

### Why coarse — the reasoning that drove the shape

At the point Gate 1 could open there are ~150 valid meals, of which perhaps 15–20 are lows. The
conventional ten-bin reliability curve would spread those across ten buckets, three or four
events each, and return a confident-looking verdict built on almost nothing. **Coarse is not a
compromise here; it is the honest resolution of the evidence available.** A rule that cannot be
satisfied except by luck is not a safety check — it is a coin toss with a serious face on it.

### Why asymmetric

This is the same asymmetry the rest of the system already carries and it is the reason the
system exists: hypo-weighted training (S-601), rescued lows retained rather than dropped
(INV-7), the warning band widened from 70 to 80 (`03 §1`), the refusal-over-a-guess rule
(S-801). **She cannot feel a low.** Overstating risk spends a fingerstick. Understating it
spends the only warning she gets. A symmetric rule would price those the same, and they are not
the same.

### What this does NOT do

It does not open Gate 1, and it does not make the model good. It is the **fifth** of five
conditions, joining volume, beats-baseline, the 90-day shadow clock and manual promotion. All
five must hold. It is also **not a model-quality score** — it answers only *"are its percentages
honest?"*, which is a different question from *"is it useful?"* (that is hypo recall vs baseline).

### Revisiting

Deliberately reviewable, not permanent. The natural trigger is the same as **OQ-8 / R-1**: once
≥ 150 real meals exist, the bucket counts and observed gaps can be inspected against reality
rather than against an estimate of what the data will look like. If real data shows the ≥ 20
floor is never met, the rule is **not** to lower the floor — it is to conclude there is not yet
enough evidence to judge calibration, which is the honest answer and keeps the gate shut.

### Second decision, same session — dashboard verdict badges

The operator also approved: **verdict badges are relative to the clinical baseline, never to an
invented absolute standard.** Every metric on the shadow dashboard is scored *Better / About the
same / Worse* against the simple arithmetic method she would use with no model at all. Rationale:
`05b §7.2` asks for a `[Good]` badge on every row, but only three metrics have a bar defined
anywhere (hypo recall vs baseline — the Gate-1 rule; false-alarm rate vs the `target_far = 0.10`
already in `models/metrics.py`; and `β_insulin < 0`, which is INV-8 and a yes/no alarm). Printing
`[Good]` on the rest would require inventing a threshold, and **an invented `[Good]` on the
promotion screen is worse than no badge** — that screen is where a human decides to put someone
who cannot feel a low in front of a model, and a green label reads as authority it has not
earned, indistinguishable from the three that are real.
**One sanctioned exception:** the Clarke grid's D/E zones are dangerous **by the measure's own
construction**, not by a cut-off anyone here picks, so those are flagged directly.

## DL-043 — OQ-5 resolved: the low/in-range line stays at 80 mg/dL
**Story:** state model (`03 §1`), open since S-501 · **Type:** clinical constant — **escalated
and answered** · **Date:** 2026-07-18 · **Approved by:** the operator, on a written proposal
(escalation path per DL-042)

**The question.** State 2's upper edge sits at **80**; the standard clinical line is **70**. A
reading of 75 is therefore labelled *a low* by this system and *in range* by convention.

**The answer: keep 80.**

**Why.**
- **Warning time.** She cannot feel a low coming. A 75 that is still falling is a 55 twenty
  minutes later. Starting the warning at 80 buys roughly 10 mg/dL — which is time to eat
  something, and time is the only thing a warning can actually give her.
- **One number, one meaning.** `core.safety.BOLUS_BG_FLOOR = 80` (INV-4) already refuses to
  suggest insulin below 80, written separately and for a different reason. Aligning the warning
  edge means *below 80 is caution territory* reads the same way everywhere. Two adjacent
  thresholds doing similar jobs at different numbers is how a future reader gets confused about
  which one governs.

**Accepted costs — recorded, not glossed.**
- **More false alarms** in the 70–79 band: readings that would have levelled out on their own now
  get flagged. This has a real ceiling. A system that cries wolf gets ignored, and an ignored
  system is worse than no system. **If the shadow-mode dashboard shows a large share of flagged
  lows are 70–79 readings that resolved unaided, that is the signal to revisit** — it belongs
  next to the `outside_window` escape hatch in `04 §5` as a *decide-from-data* item.
- **Not comparable to published literature.** Hypo recall measured against an 80 line cannot be
  read against studies anchored at 70. Acceptable for a system built for exactly one person, but
  it must never be reported as if it were comparable.

**Why it was settled now rather than later.** Every stored meal is categorised through this line.
Changing it in eight months silently re-labels the entire training set, redefines "a low" for the
model, and makes last month's recall figures mean something different from this month's — with
no error and no warning. Cheap to decide before there is history; expensive after.

**Code impact: none.** `models/state.py::STATE_BOUNDARIES` was already `(54, 80, 181, 251)` and
`tests/unit/test_state.py` already pins it exactly, including the 79/80 edge. **What closed is
the caveat, not the value** — the boundary had been carrying an "unconfirmed" marker since S-501
and the docs asserted something the project had not actually decided.

## DL-044 — S-1001 split into S-1001a (report card) and S-1001b (promotion control)
**Story:** S-1001 (EPIC 10) · **Type:** scope split · **Date:** 2026-07-18 · **Owner:** BA

`10-backlog.md` S-1001 is one story covering the whole operator dashboard, and the EPIC 10
build order additionally folds in *"the promotion control"*. That is two different kinds of
screen sharing a URL:

- **S-1001a — the shadow report card.** Read-only. Renders evidence. Nothing it does can
  change system state.
- **S-1001b [SAFETY] — the promotion control.** The **only place Gate 1 can be opened**, plus
  `POST /api/operator/promote` / `/revoke`. Every click has a consequence for a person who
  cannot feel a low.

**Why split.** A `[SAFETY]` story owes a written invariant argument and an adversarial test
pass. Folding it into a rendering story dilutes both — the safety work ends up as a section in
a UI story's test file rather than a suite anyone will defend in a year. The split is also the
honest read of the TDD loop: a large story produces a large RED, and a large RED is easy to
write vaguely.

**Two AC corrections while splitting** (recorded, not silently fixed):
1. S-1001's AC says *"Live Gate 1 / Gate 2 status shown."* **Gate 2 was retired** (S-1011,
   DL-035). The dashboard shows Gate 1 only. Showing a retired gate would imply a dose control
   exists that does not.
2. It says the dashboard renders *"a reliability/calibration diagram"*. Since S-1012 there is
   also a **calibration verdict** (`hypo_calibration`, DL-042) — a pass/fail on an
   operator-approved rule, not just a curve. The verdict is a first-class row; the curve stays
   behind the detailed-charts disclosure (`05b §7.2`).

**Ordering:** S-1001a first. S-1001b renders the five-condition checklist, so it wants the
report card's presentation layer to exist. Neither is blocked by the other's absence in the
sense that matters — Gate 1 is closed regardless.

## DL-045 — S-1002: what the patient page shows BEFORE Gate 1 (documented tension)
**Story:** S-1002 [SAFETY] · **Type:** ⚠️ **apparent doc conflict — resolved conservatively
and escalated, not decided quietly** · **Date:** 2026-07-18 · **Owner:** BA

**The tension.** Two documents point different ways about the patient readout pre-Gate-1:

- **`03 §3`** — CLOSED: *"Logging only. **No model. No output.**"*; Gate 0: *"Metrics
  computed. OPERATOR-VISIBLE ONLY. **Patient sees nothing.**"*
- **`10-backlog.md` S-1002 AC** — *"before Gate 1 it renders the refusal / **baseline
  state** as a rendered answer, never a blank, never an error page."*

Read one way, the AC asks for a **baseline blood-glucose projection displayed to her today**.

**The reading taken.** Before Gate 1 the page renders an honest *"nothing to tell you yet —
keep logging"* state. No number, no risk claim, no projection.

**Why this reading.**
1. It satisfies what the AC is actually guarding against — *"a rendered answer, never a
   blank, never an error page"*. A plain explanation is a rendered answer.
2. It honours `03 §3`, which is the **state machine that governs gates** and says *no
   output* in as many words. `03` is a safety document; the backlog is a planning one.
3. **`BASELINE_FALLBACK` was built by S-804 for the kill switch**, which is a materially
   different situation: she *has* been seeing output, it has been withdrawn, and the
   baseline is what remains. Pre-Gate-1 she has never been told anything, so there is no
   withdrawal to soften.
4. The failure this project exists to prevent is *a number that gets trusted and is quietly
   wrong*. A pre-Gate-1 baseline projection is a number she has every reason to trust — the
   app put it in front of her — about which no evidence has been gathered for her
   specifically. Shadow mode exists precisely because that evidence does not exist yet.

**What would change if the operator disagrees.** If the intent really is to show her a
baseline estimate during shadow mode, that is **a change of scope on the patient surface**,
not an interpretation of an AC. It would need: a decision recorded here, a note on how it
interacts with `03 §3`, and its own tests. It is a one-line template change and a
deliberately large paperwork change — which is the right ratio for adding a clinical number
to her screen.

**Not blocked on the answer.** The conservative reading is safe under either intent: it
shows her less, never more. If it is wrong, nothing has to be undone — only added.

## DL-046 — REQ-007 has no capture surface; `basal_log` is unwritable (correction + new story)
**Found:** while planning S-1009 · **Type:** ⚠️ **correction of a traceability claim** ·
**Date:** 2026-07-18 · **Owner:** BA

**The finding.** `basal_log` exists as a table, `features/basal.py` computes `effective_basal`
(EWMA, halflife 25 h, S-402) and is tested — and **nothing in the system can write a basal
dose.** No form, no endpoint, no recording function, no CLI, no import. A grep for `BasalLog`
across the tree returns exactly one hit: its own definition.

**The traceability claim was wrong.** The REQ-007 row read *"✅ Schema done (form:
S-302/EPIC 3)"*. S-302 delivered the **bolus-timing** block, and EPIC 3 closed without a basal
form. The requirement was recorded as covered by a story that did not cover it — the same
class of error as DL-041, and found the same way: by reading a claim against the code while
planning the next piece of work.

**Why it matters now.** `effective_basal` is a model feature (REQ-021). Without a way to
record the daily Tresiba, **the model cannot be fitted on real data at all** — S-1009 would
have hit this halfway through, with the assembler already written. It is a hard blocker, not
a nice-to-have.

**Why it went unnoticed.** Everything that needed `effective_basal` so far either tested the
EWMA in isolation (S-402, pure) or fabricated the value in memory (`scripts/demo_end_to_end.py`,
the E2E cycle). Nothing had yet asked the database for it. **A feature nobody has sourced
end-to-end is a feature nobody has checked exists.**

**Action.** New story **S-1013 — basal capture** (REQ-007), a hard prerequisite for S-1009.
The REQ-007 traceability row is corrected to ⚠️ **Schema only — no capture surface** rather
than being quietly upgraded when the story lands.

## DL-047 — S-1009: older meals are down-weighted with a 90-day half-life
**Story:** S-1009 · **Type:** modelling constant — **escalated and answered** · **Date:**
2026-07-18 · **Approved by:** the operator, on a written proposal (path per DL-042)

`07 §Retraining` says *"Monthly refit, trailing 6 months, older data down-weighted"* and gives
**no rate**. Choosing one is a modelling decision with clinical consequences, so it was put to
the operator rather than picked.

**Answer: exponential decay, half-life 90 days**, applied over the trailing 6-month window. A
meal from three months ago counts half as much as one from this week; the oldest in the window
counts about a quarter.

**Reasoning.** Insulin resistance is present (TDD 60 U) so sensitivity drifts, which is why the
spec asks for down-weighting at all. But the binding constraint here is **data scarcity**: at
~150 meals, weighting too sharply shrinks the effective sample and makes the model jumpy month
to month. Ninety days adapts to a real physiological shift within a couple of refits while
still letting six-month-old meals carry real information.

**It multiplies into the existing weights, it does not replace them.** `hypo_confidence_weights`
(S-601) already up-weights hypo states ×4 and scales by macro confidence. Recency is a third
factor. **A rescued low from five months ago is still a low** — recency reduces its weight; it
must never zero it (INV-7 in spirit).

**Reviewable, like DL-042.** Trigger: the same ≥150-real-meals point as OQ-8/R-1. If refits
turn out to swing month to month, the half-life is too short; if the model lags a known change
in her management, it is too long. Both are observable on the shadow dashboard.

## DL-048 — S-1010: the profile screen refuses nonsense and flags the unusual
**Story:** S-1010 · **Type:** input-validation policy with clinical flavour — **escalated and
answered** · **Date:** 2026-07-18 · **Approved by:** the operator

**Refuse** `icr <= 0` outright: the calculator divides by it, so there is no meaningful
behaviour to fall back on. Same for `isf <= 0`.

**Flag, do not block, values outside the expected range** (`04 §1`: ICR expected 7–10). The
screen shows the previous value alongside the new one and says plainly that the entry is
unusual.

**Why not hard limits.** A genuine clinical change outside the usual range must remain
enterable. If the screen refuses it, the workaround is editing the database by hand — which is
audited nowhere and versioned by nobody, so the safer-looking option produces the less safe
outcome.

**Why not silent acceptance.** A mistyped ICR of `90` instead of `9` would be accepted and
would under-dose every meal afterwards, with nothing on screen to notice.

**Precedent.** This is the same shape as INV-3 on the calculator: **cap-and-flag, never
silently accept and never silently refuse.** The consistency is deliberate — one rule for
implausible input across the system is one rule to remember.

### Extended at implementation (2026-07-29) — `target_bg` and *where* the refusal lives
Two clarifications recorded at close, neither a change of policy:

1. **`target_bg <= 0` is refused too.** The rule above named the two divisors. `target_bg` is
   not divided by, but every correction is measured *from* it —
   `(current_bg - target_bg) / isf` — so at a target of `0` every correction is sized as
   though her whole blood glucose were excess. INV-3 caps the result at 15 U and flags it, so
   this was bounded; a capped wrong dose is still a wrong dose. Same argument, third number.
   **No range is checked or flagged beyond positivity:** `04 §1` documents an expected band
   for ICR only, and inventing one for the target would be an unsanctioned clinical choice.
2. **The refusal lives in `data.profile`, not only in the request schema.** It was originally
   in `ProfileVersionCreate` alone, which shut the HTTP door and left open the one every
   other caller uses — a CLI, a migration, a fixture, the next screen. Validation that lives
   only in the request schema **guards the transport, not the operation**: it looks complete
   from the endpoint and is absent everywhere else. Both layers now hold it, and the function
   is the authoritative one.

**Every change is appended and audited** (REQ-054, `audit_log`), like promotion.

---

## DL-049 — `prediction_log.actual_state` is never backfilled; Gate 1 cannot open without it
**Story:** found while scoping S-1009 · **Type:** gap found, fixed in the story that found it
· **Date:** 2026-07-29 · **Raised by:** BA

**The gap.** `prediction_log.actual_state` has existed since S-201, is commented
`# backfilled`, and **nothing backfills it.** A grep across the tree returns its schema
definition and its Alembic migration — no writer.

**Why it matters more than it looks.** `actual_state` is the outcome half of every
shadow-mode comparison. Without it there is no hypo recall, no Brier score and no calibration
curve — so `load_shadow_evidence` can never return a report, the operator dashboard can never
show evidence, and **Gate 1 can never open.** The model would be fitted, correct, and
permanently unreviewable. That failure mode is silent: every test passes, the dashboard
renders its (honest) empty state, and nothing anywhere says *this can never fill in.*

**Why it went unnoticed — the third instance of one pattern.** Every shadow-mode test to date
passes `pred_states` and `actual_states` **as arrays, directly**, and
`scripts/demo_end_to_end.py` builds both in memory. Nothing had asked the database for an
outcome. The same shape as DL-046 (`basal_log` had no writer, and every consumer either tested
the EWMA in isolation or fabricated the value) and DL-046's own predecessor.

> **The rule this keeps re-teaching: a column nobody has sourced end-to-end is a column nobody
> has checked is written.** Testing a pure function over a hand-built list proves the function;
> it proves nothing about whether anything fills its input.

**Decision.** Fixed inside S-1009 rather than deferred, because S-1009's stated scope already
includes wiring `load_shadow_evidence`, and that wiring is not possible without it. The
backfill derives `actual_state = bg_to_state(post_bg)` for predictions whose meal has since
been read — **derivation, not entry**, the same rule as IOB — and is idempotent, the same
shape as `backfill_correction_iob` (S-306b, DL-020).

**Not decided here.** Whether the backfill should also run automatically when a `post_bg` is
recorded, rather than only on demand. Raised for the operator; the on-demand path is
sufficient for the refit and the dashboard, and adding a write to the post-BG path is a change
to a capture surface she uses daily.

---

## DL-050 — A refit must survive a rank-deficient design matrix
**Story:** S-1009 · **Type:** implementation constraint, found in GREEN · **Date:** 2026-07-30

**The problem.** `statsmodels`' `OrderedModel` refuses a design matrix whose **column span
contains a constant** — *"There should not be a constant in the model"* — because the model
supplies its own thresholds. A real six-month window trips this two ways, neither exotic:

1. **A constant column.** If she does no intense exercise in the window, `ex_intense`,
   `ex_intense_x_duration` and `pre_ex_intense` are zero throughout.
2. **A constant *combination*.** `net_carbs_g` is `carbs_g − fiber_g`; across any stretch
   where fibre does not move, those two columns differ by a fixed amount and their span
   contains a constant even though neither column is constant on its own.

A naive "is this column constant?" check catches only the first. Left unhandled, the monthly
refit would die with a statsmodels error that says nothing about her data — **on the day it
was first run against a real six months**, which is precisely when nobody is expecting a
library exception.

**Decision.** A **rank-based** filter: keep a column iff it raises the rank of
`[1 | kept-so-far]` — iff it explains something the intercept and the already-kept columns do
not. Both cases fall out of the one rule. Re-applied **per CV fold**, because a column can
carry rank across the whole window and be redundant inside an early expanding-window fold.

**Not silent.** The dropped names are recorded on the artifact as
`dropped_constant_features`, and `feature_list` records **what was actually fitted**. The
manifest exists so an operator months later can answer *"what did this model see?"*, and
*"it saw all 23"* would be false whenever a column carried no rank. **"This model never saw
an intense-exercise meal"** is exactly what someone needs to know before trusting it about
one.

**Why this is not information loss.** A column that adds no rank cannot explain anything that
varies. Dropping it changes no fitted relationship; keeping it only prevents the fit.

**Related, decided the same way.** `hypo_recall` is recorded as **`null`, never `0.0`**, when
the window contains no lows (or no non-lows). A recall of zero reads as *"it missed every
low"*. A window with no lows means **the model has never seen the event it exists to
predict**, and Gate 1's beats-baseline condition has nothing to compare. Two opposite
statements must not share a number. `data.scoring` fails closed on the same condition, so the
dashboard shows its empty state rather than a headline metric with a denominator of zero.

---

## DL-051 — Two defects the first demo run found, that 700 tests did not
**Story:** found while building the demo harness (post-S-1009) · **Type:** defects fixed ·
**Date:** 2026-07-30

Running the finished system against a seeded 240-day database — for the first time, end to
end — surfaced two defects in under an hour. Both are recorded because of *how* they were
found, not only *what* they were.

### 1. ★ Hypo recall was leaking, and read 1.0 for every model
`models.refit` ranked `is_hypo` — **the truth** — against itself, so
`hypo_recall_at_far` returned `1.0` regardless of what the model predicted. The defect was
introduced while handling the undefined-recall case (no lows in the window) and it survived
28 tests, because every test asserted on *the null-vs-zero distinction* and none asserted
that a **bad model scores badly**.

**Why this one matters more than its size.** Hypo recall is the metric Gate 1's
beats-baseline condition turns on. A permanent 1.0 means every model beats every baseline,
and Gate 1's most important condition becomes a formality. It is precisely the failure the
project charter names: *"a model that looks good on retrospective data, gets trusted, and is
quietly wrong about a low."*

It was caught by **reading a number that looked too good** — the escalation rule *"the model
performs suspiciously well. Almost always leakage. Investigate."* applied to our own output.

Fixed by extracting `score_predictions(pred, truth)` as a public, array-level function, so
"predicts no lows ⇒ recall 0.0" is testable without fitting anything. Four tests added:
zero, one, **strictly between** (the case a boundary-hardcoded implementation cannot fake),
and null.

**On the seeded data the honest figure is `hypo_recall = 0.0` with 18 lows observed** — the
model misses every low. Gate 1 correctly refuses to open.

### 2. The a11y suite shared a persistent database with every previous run
`tests/a11y/conftest.py::live_server` started the app with no `BGAPP_DB_URL`, so it used
`api.deps`' default `./bgapp-dev.db` — a real file in the repo root that each run appended
to. Found when the calculator's implausible-input test failed against **34 accumulated
profile rows** and passed immediately against a clean file, having tested nothing about the
code either time.

A test whose verdict depends on what ran before it is not a test. Fixed with a per-session
temp database and a reset of the module-level `_engine` cache; the suite now runs twice
consecutively with identical results and creates no file in the repo.

> **The lesson, stated once:** the unit and integration suites were green throughout. Both
> defects needed the system **run as a system, on data that looks like hers**. That is a
> different activity from testing, and it is not optional.
