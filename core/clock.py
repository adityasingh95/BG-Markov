"""The one sanctioned reader of the system wall clock.

`SystemClock.now()` is used **only** to populate `logged_at` (the system clock,
per ADR-8) — never a clinical timestamp. Write-path functions take an injectable
`Clock` so `logged_at` is deterministic in tests and so there is a single,
greppable place the wall clock is read.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class Clock(Protocol):
    def now(self) -> dt.datetime: ...


class SystemClock:
    """Reads the real system clock. For `logged_at` only (ADR-8)."""

    def now(self) -> dt.datetime:
        return dt.datetime.now()
