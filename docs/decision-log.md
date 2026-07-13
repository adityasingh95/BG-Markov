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
