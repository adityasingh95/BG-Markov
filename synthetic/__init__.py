"""Synthetic data for tests and demos (S-1004, REQ-056). **Never real patient data.**

This package manufactures records that look exactly like hers. It exists so the
end-to-end test (S-1005) and the UI stories have something to drive, and for nothing
else.

**Production code must never import this package.** `core`, `features`, `models`,
`prescribe`, `data`, `api`, and `cli` are scanned by `detect_synthetic_import` in
`tests/forbidden/`, which fails the build on any import of `synthetic`. The guard is
structural rather than a convention because both failure modes here are silent: a
synthetic row fitted as if it were real, and a synthetic number displayed as a real
reading.

Nothing here holds a database session or engine — the generator returns plain data, so
*calling* it can never contaminate a store. Persisting synthetic rows is a deliberate act
by the caller.

Synthetic data proves **wiring**, never clinical validity. No metric computed on it may
be quoted as evidence about the real model, and it shortens neither the 150-meal nor the
90-day requirement.
"""

from __future__ import annotations

__all__ = ["generator"]
