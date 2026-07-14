"""S-202 — the sanctioned system-clock reader (SDET).

SystemClock is the ONE place the wall clock is read (for logged_at only). It is
exercised here so the sanctioned path is not dead code.
"""

from __future__ import annotations

from datetime import datetime

from core.clock import SystemClock


def test_system_clock_returns_a_datetime() -> None:
    before = datetime.now()
    now = SystemClock().now()
    after = datetime.now()
    assert isinstance(now, datetime)
    assert before <= now <= after
