"""Seeded synthetic logging cycle (S-1004, REQ-056). **Not real patient data.**

Produces meals with macros, boluses, exercise, post-meal readings and hypo rescues, over
a requested number of days, from a caller-supplied seed and start date.

Three properties are load-bearing and each is pinned by a test:

* **Determinism.** All entropy comes from ``random.Random(seed)``. There is no clock read
  and no module-level RNG, so a failing end-to-end run can be re-run exactly.
* **Reported-timestamp discipline (ADR-8).** ``logged_at`` is generated *strictly later*
  than the reported ``datetime`` — she logs at the laptop, not at the table. A generator
  that set them equal would make an end-to-end run pass whether or not production code
  respects the distinction, blinding the suite to the bug ADR-8 exists to catch.
* **The hypo minority emerges.** There is deliberately **no hypo-rate parameter**: the
  rate falls out of carbs, insulin and exercise. A caller who could dial the hypo rate
  could dial the headline metric.

The module holds no session or engine (see the package docstring).
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import asdict, dataclass, field
from typing import Any

# Physiology used to *simulate* outcomes. These are simulation parameters for fake data,
# NOT clinical constants: nothing here is read by the model, the baseline, or the dose
# path, and changing them changes only the fixture.
_SIM_ICR = 9.0          # g carb per unit
_SIM_ISF = 30.0         # mg/dL per unit
_SIM_TARGET = 135.0     # mg/dL
_MEAL_MINUTES = {"breakfast": (7, 30), "lunch": (13, 0), "dinner": (20, 0)}
_POST_MEAL_MIN = 120    # she is prompted to test at mealtime + 2 h


@dataclass(frozen=True)
class SyntheticMeal:
    """One synthetic meal. Mirrors the ``meal_event`` fields the pipeline reads.

    Deliberately a plain dataclass, not an ORM row: the generator cannot write anywhere.
    """

    datetime: dt.datetime          # REPORTED — when she ate
    logged_at: dt.datetime         # system-clock analogue; ALWAYS later (ADR-8)
    meal_type: str
    pre_bg: int
    pre_bg_time: dt.datetime       # REPORTED
    post_bg: int | None
    post_bg_time: dt.datetime | None   # REPORTED
    elapsed_min: int | None        # from REPORTED times only
    meal_bolus_units: float
    correction_bolus_units: float
    bolus_offset_min: int          # SIGNED: negative = pre-bolus
    carbs_g: float
    protein_g: float
    fat_g: float
    fiber_g: float
    net_carbs_g: float
    macro_confidence: int
    ex_intensity: str
    ex_duration_min: int
    ex_offset_min: int | None
    pre_ex_intensity: str
    pre_ex_duration_min: int
    hypo_treatment: bool
    hypo_treatment_g: float | None
    snack_during_window: bool


@dataclass(frozen=True)
class SyntheticBasal:
    """A daily Tresiba dose. Constant within a day — which is exactly why a random
    train/test split leaks and forward-chaining CV is mandatory."""

    date: dt.date
    units: float


@dataclass(frozen=True)
class SyntheticDataset:
    """The generated cycle. ``seed``/``days``/``start`` are carried so any run is
    reproducible from the dataset itself."""

    seed: int
    days: int
    start: dt.date
    meals: list[SyntheticMeal] = field(default_factory=list)
    basal: list[SyntheticBasal] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """A stable, fully-ordered dict — the basis of the determinism digest."""
        return {
            "seed": self.seed,
            "days": self.days,
            "start": self.start.isoformat(),
            "meals": [asdict(m) for m in self.meals],
            "basal": [asdict(b) for b in self.basal],
        }


def _exercise(rng: random.Random) -> tuple[str, int]:
    """Post-meal activity. Light walks are common; intense sessions are rarer and are the
    main driver of the lows this fixture must contain."""
    roll = rng.random()
    if roll < 0.25:
        return "light", rng.randint(20, 45)
    if roll < 0.35:
        return "intense", rng.randint(30, 60)
    return "none", 0


def _simulate_post_bg(
    *,
    pre_bg: float,
    carbs_g: float,
    meal_bolus: float,
    correction: float,
    ex_intensity: str,
    ex_duration_min: int,
    rng: random.Random,
) -> float:
    """A plausible 2-hour outcome (07 §4 shape) plus residual noise.

    Carbs raise; bolus and correction lower; exercise lowers. The hypo rate is whatever
    this produces — there is no knob.
    """
    bg = (
        pre_bg
        + (carbs_g / _SIM_ICR) * _SIM_ISF
        - (meal_bolus + correction) * _SIM_ISF
    )
    if ex_intensity == "light":
        bg -= 0.55 * ex_duration_min
    elif ex_intensity == "intense":
        bg -= 1.25 * ex_duration_min
    bg += rng.gauss(0, 18)
    return min(max(bg, 25.0), 480.0)


def generate(
    *,
    seed: int,
    days: int,
    start: dt.date,
    completion_rate: float = 0.9,
) -> SyntheticDataset:
    """Generate ``days`` of synthetic logging from ``seed``, beginning on ``start``.

    ``completion_rate`` is the share of meals that get a post-meal reading (she misses
    some). There is **no hypo-rate parameter** — see the module docstring.
    """
    if days < 1:
        raise ValueError(f"days must be >= 1; got {days}")
    if not 0.0 <= completion_rate <= 1.0:
        raise ValueError(f"completion_rate must be in [0, 1]; got {completion_rate}")

    rng = random.Random(seed)
    meals: list[SyntheticMeal] = []
    basal: list[SyntheticBasal] = []

    for day_index in range(days):
        day = start + dt.timedelta(days=day_index)
        basal.append(SyntheticBasal(date=day, units=round(rng.uniform(20.0, 24.0), 1)))

        for meal_type, (hour, minute) in _MEAL_MINUTES.items():
            # She skips a meal occasionally; every day still keeps at least breakfast.
            if meal_type != "breakfast" and rng.random() < 0.12:
                continue

            ate_at = dt.datetime.combine(day, dt.time(hour, minute)) + dt.timedelta(
                minutes=rng.randint(-20, 20)
            )
            # ADR-8: she logs at the laptop afterwards. ALWAYS strictly later.
            logged_at = ate_at + dt.timedelta(minutes=rng.randint(5, 75))

            pre_bg = rng.uniform(90, 200)
            carbs = rng.uniform(20, 90)
            fiber = rng.uniform(0, 8)
            protein = rng.uniform(5, 30)
            fat = rng.uniform(2, 25)

            meal_bolus = max(0.0, carbs / _SIM_ICR * rng.uniform(0.90, 1.05))
            correction = max(0.0, (pre_bg - _SIM_TARGET) / _SIM_ISF * rng.uniform(0.7, 1.0))
            # Signed offset: negative = pre-bolus. Both directions must occur.
            bolus_offset = rng.choice([-20, -15, -10, -5, 0, 0, 10, 15])

            ex_intensity, ex_duration = _exercise(rng)
            pre_bg_time = ate_at - dt.timedelta(minutes=rng.randint(2, 10))

            post_bg_val: int | None = None
            post_bg_time: dt.datetime | None = None
            elapsed: int | None = None
            hypo_treatment = False
            hypo_grams: float | None = None

            if rng.random() < completion_rate:
                # Reported reading time drifts around the mealtime+120 prompt.
                elapsed = _POST_MEAL_MIN + rng.randint(-20, 20)
                post_bg_time = ate_at + dt.timedelta(minutes=elapsed)
                raw = _simulate_post_bg(
                    pre_bg=pre_bg, carbs_g=carbs, meal_bolus=meal_bolus,
                    correction=correction, ex_intensity=ex_intensity,
                    ex_duration_min=ex_duration, rng=rng,
                )
                post_bg_val = int(round(raw))
                # A share of lows get treated during the window — INV-7 needs these to
                # exist so S-1005 can prove they are excluded from training yet retained
                # as hypo events.
                if post_bg_val < 80 and rng.random() < 0.5:
                    hypo_treatment = True
                    hypo_grams = float(rng.choice([10, 15, 20]))

            meals.append(
                SyntheticMeal(
                    datetime=ate_at,
                    logged_at=logged_at,
                    meal_type=meal_type,
                    pre_bg=int(round(pre_bg)),
                    pre_bg_time=pre_bg_time,
                    post_bg=post_bg_val,
                    post_bg_time=post_bg_time,
                    elapsed_min=elapsed,
                    meal_bolus_units=round(meal_bolus, 2),
                    correction_bolus_units=round(correction, 2),
                    bolus_offset_min=bolus_offset,
                    carbs_g=round(carbs, 1),
                    protein_g=round(protein, 1),
                    fat_g=round(fat, 1),
                    fiber_g=round(fiber, 1),
                    net_carbs_g=round(max(carbs - fiber, 0.0), 1),
                    macro_confidence=rng.choice([95, 95, 95, 60]),
                    ex_intensity=ex_intensity,
                    ex_duration_min=ex_duration,
                    ex_offset_min=rng.randint(0, 30) if ex_duration else None,
                    pre_ex_intensity="none",
                    pre_ex_duration_min=0,
                    hypo_treatment=hypo_treatment,
                    hypo_treatment_g=hypo_grams,
                    snack_during_window=rng.random() < 0.05,
                )
            )

    return SyntheticDataset(seed=seed, days=days, start=start, meals=meals, basal=basal)
