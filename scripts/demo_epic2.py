"""End-to-end demo of the EPIC 2 data layer — run it and read the output.

    python scripts/demo_epic2.py

Builds a throwaway SQLite DB and exercises the real code:
  1. Dish table: portion scaling (2×roti = double) and free-text ⇒ confidence 60.
  2. Reported timestamps (ADR-8): datetime = reported, logged_at = system clock.
  3. Validity + INV-7: rescued meals are excluded from training but retained as
     hypo events — the safety property the whole system exists to protect.

Nothing here is a test; it is a readable walk-through of the behaviour the tests
lock in. It creates its DB in a temp dir and cleans up.
"""

from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

# Make the project importable when run as `python scripts/demo_epic2.py` from
# any directory (a script's sys.path[0] is its own dir, not the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.db import create_all, make_engine, session_factory
from data.dishes import IFCT_SEED, dish_macros, find_dish, ingest_dishes, resolve_dish
from data.recording import record_meal, record_post_bg
from data.repositories import get_hypo_events, get_training_set
from data.tables import LoggedBy, MealEvent, MealType


def _rule(title: str) -> None:
    print(f"\n{'─' * 68}\n{title}\n{'─' * 68}")


def main() -> None:
    tmpdir = tempfile.mkdtemp(prefix="bgdemo-")
    try:
        engine = make_engine(f"sqlite:///{Path(tmpdir) / 'demo.db'}")
        create_all(engine)
        session = session_factory(engine)()

        # 1 — Dish table -----------------------------------------------------
        _rule("1. Dish table — portions scale linearly; free text is less trusted")
        ingest_dishes(session, IFCT_SEED)
        roti = find_dish(session, "ROTI")  # case-insensitive
        assert roti is not None
        one, two = dish_macros(roti, 1), dish_macros(roti, 2)
        print(f"  1 × roti : carbs={one.carbs_g:g}g  protein={one.protein_g:g}g")
        print(f"  2 × roti : carbs={two.carbs_g:g}g  protein={two.protein_g:g}g (exactly double)")

        known = resolve_dish(session, "dal")
        free = resolve_dish(session, "aunty's special khichdi")
        print(f"  resolve 'dal'          -> confidence {known.macro_confidence}, "
              f"review={known.needs_review}")
        print(f"  resolve free-text dish -> confidence {free.macro_confidence}, "
              f"review={free.needs_review}  (60, not 95; queued for operator)")

        # 2 — Reported timestamps (ADR-8) -----------------------------------
        _rule("2. Reported timestamps — she logs at the laptop, not at the table")
        meal = record_meal(
            reported_datetime=dt.datetime(2026, 7, 1, 8, 0),   # when she ATE
            meal_type=MealType.breakfast,
            pre_bg=142,
            pre_bg_time=dt.datetime(2026, 7, 1, 7, 55),
            meal_bolus_units=6.0,
            bolus_datetime=dt.datetime(2026, 7, 1, 7, 45),      # 15 min pre-bolus
            carbs_g=45.0,
            logged_by=LoggedBy.patient,
        )  # logged_at defaults to the real system clock
        print(f"  reported mealtime (datetime) : {meal.datetime}")
        print(f"  system clock   (logged_at)   : {meal.logged_at}  <- different field, real now()")
        print(f"  bolus_offset_min             : {meal.bolus_offset_min}  (negative = pre-bolus)")
        record_post_bg(meal, post_bg=168, post_bg_time=dt.datetime(2026, 7, 1, 10, 0))
        print(f"  post-BG 168 @ reported 10:00 -> elapsed_min = {meal.elapsed_min}  (from 10:00)")

        # 3 — Validity + INV-7 ----------------------------------------------
        _rule("3. Validity + INV-7 — rescued lows are excluded from training, KEPT as hypo events")
        base = dt.datetime(2026, 2, 1, 8, 0)
        meals = []
        for i in range(10):
            rescued = i in (3, 7)  # 2 rescued lows out of 10
            when = base + dt.timedelta(days=i)
            meals.append(
                MealEvent(
                    datetime=when, logged_at=when, logged_by=LoggedBy.patient,
                    meal_type=MealType.lunch, pre_bg=120, pre_bg_time=when,
                    meal_bolus_units=5.0, bolus_offset_min=-10, carbs_g=40.0,
                    post_bg=(96 if rescued else 150),  # rescued: post looks normal
                    post_bg_time=when + dt.timedelta(minutes=120),
                    elapsed_min=120, hypo_treatment=rescued, macro_confidence=95,
                )
            )
        session.add_all(meals)
        session.commit()

        training = get_training_set(session)   # calls INV-7 before returning
        hypo = get_hypo_events(session)
        rescued_in_training = [m for m in training if m.hypo_treatment]
        print("  10 meals logged, 2 of them rescued lows")
        print(f"  get_training_set()  -> {len(training)} meals, rescued among them: "
              f"{len(rescued_in_training)}")
        print(f"  get_hypo_events()   -> {len(hypo)} events (the 2 rescued lows, retained)")
        print("  INV-7 held: get_training_set() called the invariant and did not raise.")
        print("  A refactor letting a rescued meal into training would raise SafetyViolation.")

        print("\n✅ EPIC 2 behaviour demonstrated on real code + a real SQLite DB.")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
