"""S-203 — validity accessors + the INV-7 wiring (SDET, written RED first).

get_training_set() excludes invalid rows; get_hypo_events() RETAINS rescued
rows. The regression guard is the load-bearing test: it catches a future
refactor that silently deletes every low she ever had.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from core.safety import SafetyViolation
from data import repositories
from data.repositories import get_hypo_events, get_training_set
from data.tables import LoggedBy, MealEvent, MealType


def _meal(day: int, *, rescued: bool = False, post_bg: int | None = 140,
          macro_confidence: int = 95, elapsed: int | None = 120) -> MealEvent:
    when = datetime(2026, 1, 1, 8, 0) + timedelta(days=day)  # one/day: no contamination
    return MealEvent(
        datetime=when,
        logged_at=when,
        logged_by=LoggedBy.patient,
        meal_type=MealType.breakfast,
        pre_bg=120,
        pre_bg_time=when,
        meal_bolus_units=5.0,
        bolus_offset_min=-10,
        carbs_g=40.0,
        post_bg=(95 if rescued else post_bg),  # rescued: post looks normal post-rescue
        post_bg_time=when + timedelta(minutes=120),
        elapsed_min=elapsed,
        hypo_treatment=rescued,
        macro_confidence=macro_confidence,
    )


def test_get_training_set_excludes_invalid_rows(session: Session) -> None:
    session.add_all([
        _meal(0),                       # valid
        _meal(1, post_bg=None),         # missing_outcome
        _meal(2, elapsed=200),          # outside_window
        _meal(3, macro_confidence=10),  # low_confidence
    ])
    session.commit()
    training = get_training_set(session)
    assert len(training) == 1
    assert training[0].post_bg == 140


def test_get_hypo_events_retains_a_rescued_meal_with_normal_post_bg(session: Session) -> None:
    session.add_all([_meal(0), _meal(1, rescued=True)])
    session.commit()
    hypo = get_hypo_events(session)
    assert len(hypo) == 1
    assert hypo[0].hypo_treatment is True
    assert hypo[0].post_bg == 95  # normal-looking, still retained as a hypo event


def test_regression_guard_100_meals_20_rescued(session: Session) -> None:
    """★ 100 meals, 20 rescued ⇒ training excludes all 20; hypo returns exactly 20.

    Do not delete this test. It catches the refactor that trains the model on a
    world where she never goes low.
    """
    rescued_days = set(range(0, 100, 5))  # 20 rescued
    session.add_all([_meal(d, rescued=(d in rescued_days)) for d in range(100)])
    session.commit()

    training = get_training_set(session)
    hypo = get_hypo_events(session)

    training_days = {m.datetime.toordinal() for m in training}
    rescued_ordinals = {
        (datetime(2026, 1, 1, 8, 0) + timedelta(days=d)).toordinal() for d in rescued_days
    }
    assert training_days.isdisjoint(rescued_ordinals), "a rescued meal leaked into training"
    assert len(training) == 80
    assert len(hypo) == 20


def test_inv7_wiring_bites_if_rescued_leaks_into_training(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subvert the exclusion logic so a rescued meal is treated as valid (the
    exact forbidden refactor). get_training_set must raise via INV-7."""
    session.add_all([_meal(0), _meal(1, rescued=True)])
    session.commit()
    # Pretend every meal is valid — rescued rows would leak into training.
    monkeypatch.setattr(repositories, "exclusion_reasons", lambda **_: [])
    with pytest.raises(SafetyViolation):
        get_training_set(session)
