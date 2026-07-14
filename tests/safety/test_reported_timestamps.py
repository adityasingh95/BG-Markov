"""S-202 [SAFETY] — reported-timestamp discipline on the write path (ADR-8).

She logs at the laptop, not at the table. `datetime` is what she reports;
`logged_at` is the system clock; the two derived features come from reported
times only. Defaulting a clinical time to now() corrupts the model silently —
these tests, plus the S-105 guard scanning data/recording.py, make it loud.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import data.recording as recording
from data.recording import record_meal, record_post_bg
from data.tables import LoggedBy, MealType


class _FixedClock:
    """A deterministic clock so logged_at is not the real wall time in tests."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _build() -> object:
    # Logged at 09:40, reporting an 08:00 mealtime with a 07:45 pre-bolus.
    return record_meal(
        reported_datetime=datetime(2026, 7, 1, 8, 0),
        meal_type=MealType.breakfast,
        pre_bg=142,
        pre_bg_time=datetime(2026, 7, 1, 7, 55),
        meal_bolus_units=6.0,
        bolus_datetime=datetime(2026, 7, 1, 7, 45),
        carbs_g=45.0,
        logged_by=LoggedBy.patient,
        clock=_FixedClock(datetime(2026, 7, 1, 9, 40)),
    )


def test_reported_datetime_and_logged_at_differ() -> None:
    meal = _build()
    assert meal.datetime == datetime(2026, 7, 1, 8, 0)  # type: ignore[attr-defined]
    assert meal.logged_at == datetime(2026, 7, 1, 9, 40)  # type: ignore[attr-defined]
    assert meal.datetime != meal.logged_at  # type: ignore[attr-defined]


def test_bolus_offset_is_computed_from_reported_times() -> None:
    meal = _build()
    assert meal.bolus_offset_min == -15  # type: ignore[attr-defined]


def test_elapsed_min_uses_reported_reading_time_not_entry_time() -> None:
    """Post-BG for a 10:00 reading, entered later at 11:30: elapsed uses 10:00."""
    meal = _build()  # meal reported at 08:00
    record_post_bg(meal, post_bg=168, post_bg_time=datetime(2026, 7, 1, 10, 0))
    assert meal.post_bg == 168  # type: ignore[attr-defined]
    assert meal.post_bg_time == datetime(2026, 7, 1, 10, 0)  # type: ignore[attr-defined]
    assert meal.elapsed_min == 120  # from reported 10:00, not any entry time


def test_logged_at_uses_the_injected_clock() -> None:
    """logged_at is the (injected) system clock, not a reported value."""
    meal = record_meal(
        reported_datetime=datetime(2026, 7, 1, 8, 0),
        meal_type=MealType.lunch,
        pre_bg=120,
        pre_bg_time=datetime(2026, 7, 1, 7, 58),
        meal_bolus_units=5.0,
        bolus_datetime=datetime(2026, 7, 1, 8, 0),
        carbs_g=30.0,
        logged_by=LoggedBy.operator,
        clock=_FixedClock(datetime(2030, 1, 1, 0, 0)),
    )
    assert meal.logged_at == datetime(2030, 1, 1, 0, 0)  # type: ignore[attr-defined]


# --- Targeted write-path guard: now() may only populate logged_at (ADR-8) ---


def _is_now_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in {"now", "utcnow", "today"}:
        return True
    return isinstance(func, ast.Name) and func.id in {"now", "utcnow"}


def test_now_is_bound_only_to_logged_at_in_recording_module() -> None:
    """The positive statement of ADR-8 for the write path: a system-clock read
    populates logged_at and nothing else."""
    tree = ast.parse(Path(recording.__file__).read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_now_call(node.value):
            for target in node.targets:
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name != "logged_at":
                    offenders.append(f"assign to {name}")
        elif isinstance(node, ast.Call):
            offenders += [
                f"kwarg {kw.arg}"
                for kw in node.keywords
                if _is_now_call(kw.value) and kw.arg != "logged_at"
            ]
    assert not offenders, f"now() bound to non-logged_at target(s): {offenders}"
