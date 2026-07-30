"""Seed a **demo** database from the S-1004 synthetic generator. NOT patient data.

The generator deliberately produces plain dataclasses and cannot write anywhere (S-1004),
so this is the bridge for demos and manual exploration. It is a script, not production code:
nothing under `core/`, `models/`, `prescribe/` or `api/` imports it.

★ It writes through the real capture paths where they exist — `record_basal` for basal,
`annotate_validity` for meal validity — rather than hand-setting the columns. A seeder that
sets `is_valid = True` itself would produce a database no real usage could produce, and every
demo run on top of it would be measuring the seeder.

Usage:  python -m scripts.seed_demo_db --db demo.db --days 240 --seed 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib

from data.basal import record_basal
from data.db import create_all, make_engine, session_factory
from data.profile import append_profile_version
from data.repositories import annotate_validity
from data.tables import (
    BolusLog,
    BolusType,
    ExIntensity,
    HypoRescueLog,
    LoggedBy,
    MealEvent,
    MealType,
)
from synthetic.generator import generate


class _SeedClock:
    """A fixed clock for `logged_at`. The seed run must be reproducible, so even the
    system-clock field is deterministic (ADR-8 keeps it distinct from reported times)."""

    def __init__(self, at: dt.datetime) -> None:
        self._at = at

    def now(self) -> dt.datetime:
        return self._at


def seed(db_path: str, *, days: int, seed_value: int, end: dt.date) -> dict[str, int]:
    start = end - dt.timedelta(days=days - 1)
    data = generate(seed=seed_value, days=days, start=start)

    engine = make_engine(f"sqlite:///{db_path}")
    create_all(engine)
    counts = {"meals": 0, "boluses": 0, "basal": 0, "rescues": 0, "valid": 0}

    with session_factory(engine)() as session:
        append_profile_version(
            session, effective_from=start, icr=9.0, isf=30.0, target_bg=135,
            changed_by=LoggedBy.operator,
        )

        for b in data.basal:
            record_basal(
                session, date=b.date, units=b.units, time_taken=dt.time(22, 0),
                logged_by=LoggedBy.patient,
                clock=_SeedClock(dt.datetime.combine(b.date, dt.time(22, 30))),
            )
            counts["basal"] += 1

        prev: dt.datetime | None = None
        for m in data.meals:
            meal = MealEvent(
                datetime=m.datetime,
                logged_at=m.logged_at,          # ADR-8: strictly later, never equal
                logged_by=LoggedBy.patient,
                meal_type=MealType(m.meal_type),
                pre_bg=m.pre_bg,
                pre_bg_time=m.pre_bg_time,
                post_bg=m.post_bg,
                post_bg_time=m.post_bg_time,
                elapsed_min=m.elapsed_min,
                meal_bolus_units=m.meal_bolus_units,
                correction_bolus_units=m.correction_bolus_units,
                bolus_offset_min=m.bolus_offset_min,
                carbs_g=m.carbs_g,
                protein_g=m.protein_g,
                fat_g=m.fat_g,
                fiber_g=m.fiber_g,
                macro_confidence=m.macro_confidence,
                ex_intensity=ExIntensity(m.ex_intensity),
                ex_duration_min=m.ex_duration_min,
                ex_offset_min=m.ex_offset_min,
                pre_ex_intensity=ExIntensity(m.pre_ex_intensity),
                pre_ex_duration_min=m.pre_ex_duration_min,
                hypo_treatment=m.hypo_treatment,
                hypo_treatment_g=m.hypo_treatment_g,
                snack_during_window=m.snack_during_window,
            )
            # Through the real S-203 path, not a hand-set column.
            annotate_validity(meal, prev)
            session.add(meal)
            session.flush()
            counts["meals"] += 1
            counts["valid"] += 1 if meal.is_valid else 0
            prev = m.datetime

            bolus_at = m.datetime + dt.timedelta(minutes=m.bolus_offset_min)
            for units, kind in (
                (m.meal_bolus_units, BolusType.meal),
                (m.correction_bolus_units, BolusType.correction),
            ):
                if units > 0:
                    session.add(
                        BolusLog(
                            datetime=bolus_at, logged_at=m.logged_at, units=units,
                            bolus_type=kind, meal_id=meal.meal_id,
                            logged_by=LoggedBy.patient,
                        )
                    )
                    counts["boluses"] += 1

            if m.hypo_treatment:
                # ★ The independent ledger (S-305). INV-7 reconciles against it, so a
                # seeder that skipped it would produce a database INV-7 declares corrupt.
                session.add(
                    HypoRescueLog(
                        meal_id=meal.meal_id, grams=m.hypo_treatment_g,
                        logged_at=m.logged_at,
                    )
                )
                counts["rescues"] += 1

        session.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="seed_demo_db", description="Seed a DEMO database")
    p.add_argument("--db", default="demo.db")
    p.add_argument("--days", type=int, default=240)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--end", default="2026-07-30", help="last day of synthetic data")
    args = p.parse_args(argv)

    path = pathlib.Path(args.db)
    if path.exists():
        path.unlink()
    counts = seed(
        str(path), days=args.days, seed_value=args.seed,
        end=dt.date.fromisoformat(args.end),
    )
    print(f"seeded {args.db}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
