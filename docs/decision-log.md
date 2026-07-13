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
