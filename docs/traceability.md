# Traceability Matrix

*Owner: BA. REQ-nnn → story → test → status. Any REQ without a covering test is
a visible gap. INV-n coverage is tracked in the second table.*

## REQ → story → test

| REQ | Story | Test(s) | Status |
|-----|-------|---------|--------|
| _(none — infra)_ | S-101 | `tests/unit/test_toolchain.py`, `tests/unit/test_version.py` | ✅ Done |
| **`05b §2`** (Accessibility NFR; no `REQ-nnn`) | S-102 | `tests/a11y/test_base_layout.py` (axe, inputmode, 18px, 48px, no-dish-`select`, 200 %-zoom reflow, colour-not-sole-signal) | ✅ Done |

> No `REQ-nnn` is claimed by S-101; it is an infrastructure story.
> **S-102** also maps to no numbered REQ — the backlog cites its requirement
> source directly as `05b §2` (Accessibility — Non-Negotiable). It is recorded
> above against that source so the accessibility floor is not an untraced gap.
> The numbered REQ register (`01-prd.md` §5) begins to be consumed at EPIC 2.

## INV → story → test

| INV | First enforced by | Test(s) | Status |
|-----|-------------------|---------|--------|
| INV-1..9 | S-104 (module), S-105 (patterns) | — | ⏳ Not yet started |

S-101 introduces no invariant logic. It provides the ruff/mypy/pytest/coverage
gates that S-104 and S-105 rely on to be enforceable at all.

## Gaps / watch-list
- ~~The 90% coverage gate is enforced in **CI only** this session (DL-002).~~
  **Resolved (DL-004):** PyPI/npm egress is now open; the full dep set installs
  locally and the coverage gate (`--cov=core --cov-fail-under=90`) was verified
  locally this session as well as in CI.
- `api/` is exercised by the a11y suite but is **not** in `[tool.coverage.run]
  source` (still `core` only, per DL-003). `api/` is presentation; the DoD
  coverage bar is on `core/`, which S-102 does not touch. Widen `source` when
  business logic (not just template wiring) lands under `api/`.
- The a11y suite requires a Chromium build (DL-005). CI installs it; a runner
  without it turns the suite red rather than skipping silently — intentional.
