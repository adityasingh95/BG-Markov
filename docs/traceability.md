# Traceability Matrix

*Owner: BA. REQ-nnn → story → test → status. Any REQ without a covering test is
a visible gap. INV-n coverage is tracked in the second table.*

## REQ → story → test

| REQ | Story | Test(s) | Status |
|-----|-------|---------|--------|
| _(none — infra)_ | S-101 | `tests/unit/test_toolchain.py`, `tests/unit/test_version.py` | ✅ Done |

> No `REQ-nnn` is claimed by S-101; it is an infrastructure story. The REQ
> register (`01-prd.md` §5) begins to be consumed at S-102 / EPIC 2.

## INV → story → test

| INV | First enforced by | Test(s) | Status |
|-----|-------------------|---------|--------|
| INV-1..9 | S-104 (module), S-105 (patterns) | — | ⏳ Not yet started |

S-101 introduces no invariant logic. It provides the ruff/mypy/pytest/coverage
gates that S-104 and S-105 rely on to be enforceable at all.

## Gaps / watch-list
- The 90% coverage gate is enforced in **CI only** this session (DL-002).
  When PyPI egress is restored, verify it runs locally too.
