"""S-1004 [SAFETY] — the synthetic-data generator (SDET, written RED first).

This generator manufactures records indistinguishable from hers. Both failure modes are
silent: a synthetic row fitted as if it were real, or a synthetic number read as a real
reading. So these tests are adversarial about the three cheap mistakes named in
docs/stories/S-1004.md — seeding from the clock, setting `logged_at = datetime`, and
adding a hypo-rate knob.

RED: the `synthetic` package does not exist.
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import pathlib

import pytest

from synthetic.generator import SyntheticDataset, generate

_START = dt.date(2026, 1, 6)  # a Monday; fixed, never "today"


def _digest(ds: SyntheticDataset) -> str:
    """A stable digest of the WHOLE dataset.

    Deliberately not a field-by-field comparison: a field-by-field check silently stops
    covering any field added later, which is exactly when determinism quietly breaks.
    """
    return hashlib.sha256(
        json.dumps(ds.to_jsonable(), sort_keys=True, default=str).encode()
    ).hexdigest()


# --- determinism -------------------------------------------------------------


def test_same_seed_is_byte_identical() -> None:
    """★ The same seed twice ⇒ identical output. Without this a failing E2E run is not
    investigable — you cannot re-run the thing that failed."""
    a = generate(seed=7, days=30, start=_START)
    b = generate(seed=7, days=30, start=_START)
    assert _digest(a) == _digest(b)


def test_different_seeds_differ() -> None:
    """★ Otherwise 'deterministic' is satisfiable by returning a constant."""
    a = generate(seed=7, days=30, start=_START)
    b = generate(seed=8, days=30, start=_START)
    assert _digest(a) != _digest(b)


# --- ADR-8: reported vs logged timestamps ------------------------------------


def test_logged_at_is_always_later_than_the_reported_mealtime() -> None:
    """★ ADR-8. She logs at the laptop, not at the table.

    If the generator set `logged_at == datetime`, an end-to-end run would pass whether or
    not production code respects the distinction — the suite would be blind to the exact
    bug ADR-8 exists to catch. So the lag is generated, and asserted here.
    """
    ds = generate(seed=11, days=30, start=_START)
    assert ds.meals, "generator produced no meals"
    for m in ds.meals:
        assert m.logged_at > m.datetime, f"logged_at not after mealtime: {m}"
        assert m.logged_at != m.datetime


def test_elapsed_min_is_computed_from_reported_times_only() -> None:
    """`elapsed_min` must reconcile with post_bg_time − datetime (both REPORTED)."""
    ds = generate(seed=12, days=30, start=_START)
    checked = 0
    for m in ds.meals:
        if m.post_bg_time is None or m.elapsed_min is None:
            continue
        expected = round((m.post_bg_time - m.datetime).total_seconds() / 60)
        assert m.elapsed_min == expected, f"elapsed_min != reported delta for {m}"
        checked += 1
    assert checked > 0, "no completed meals to check elapsed_min against"


def test_no_generated_clinical_timestamp_depends_on_the_wall_clock() -> None:
    """★ The generator's only entropy is the injected seed + start date.

    A clock read would make runs unreproducible AND re-introduce the ADR-8 hazard inside
    the very fixture meant to expose it.
    """
    pkg = pathlib.Path(__file__).resolve().parents[2] / "synthetic"
    offenders: list[str] = []
    for path in pkg.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "now", "today", "utcnow", "fromtimestamp"
            }:
                offenders.append(f"{path.name}: .{node.attr}()")
            # Using the process-GLOBAL RNG (`random.random()`, `random.choice()`,
            # `random.seed()`) is forbidden: it is shared mutable state, so output would
            # depend on whatever else touched it. `random.Random(seed)` is the sanctioned
            # opposite — it CONSTRUCTS an isolated, seeded instance — so it is allowed.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "random"
                and node.func.attr != "Random"
            ):
                offenders.append(f"{path.name}: random.{node.func.attr}() (global RNG)")
    assert not offenders, f"generator reads the clock or a global RNG: {offenders}"


# --- shape -------------------------------------------------------------------


def test_requested_days_are_produced_with_plausible_meal_counts() -> None:
    ds = generate(seed=3, days=45, start=_START)
    days = {m.datetime.date() for m in ds.meals}
    assert len(days) == 45
    per_day = [sum(1 for m in ds.meals if m.datetime.date() == d) for d in days]
    assert all(1 <= n <= 4 for n in per_day), f"implausible meals/day: {sorted(set(per_day))}"


def test_bolus_offset_is_signed_and_takes_both_directions() -> None:
    """REQ-003: negative = pre-bolus. A generator that only emits one sign would leave the
    pre-bolus half of the feature space untested downstream."""
    ds = generate(seed=4, days=60, start=_START)
    offsets = {m.bolus_offset_min for m in ds.meals}
    assert any(o < 0 for o in offsets), "no pre-bolus meals generated"
    assert any(o >= 0 for o in offsets), "no at/after-meal boluses generated"


def test_macros_are_non_negative_and_net_carbs_never_negative() -> None:
    ds = generate(seed=5, days=30, start=_START)
    for m in ds.meals:
        assert m.carbs_g >= 0 and m.protein_g >= 0 and m.fat_g >= 0 and m.fiber_g >= 0
        assert m.net_carbs_g >= 0, f"net carbs went negative: {m}"


# --- the hypo minority must be real, and must NOT be dialable ----------------


def test_hypo_rate_is_a_real_minority_and_emerges_from_the_simulation() -> None:
    """★ Not zero — INV-7 and hypo recall would be untestable end-to-end.
    Not a majority — that is not her life, and a model tested on it means nothing."""
    ds = generate(seed=6, days=120, start=_START)
    completed = [m for m in ds.meals if m.post_bg is not None]
    assert completed, "no completed meals"
    rate = sum(1 for m in completed if m.post_bg is not None and m.post_bg < 80) / len(completed)
    assert 0.0 < rate < 0.5, f"hypo rate {rate:.2f} is not a plausible minority"


def test_there_is_no_hypo_rate_knob() -> None:
    """★ A caller who can dial the hypo rate can dial the headline metric. The rate must
    emerge from carbs/insulin/exercise, so the model is evaluated on something it did not
    choose. This asserts the knob does not exist."""
    import inspect

    params = set(inspect.signature(generate).parameters)
    for knob in ("hypo_rate", "hypo_rate_target", "target_hypo_rate", "force_hypo", "hypo_pct"):
        assert knob not in params, f"generate() exposes a hypo-rate knob: {knob}"


def test_rescued_meals_exist_and_carry_grams() -> None:
    """INV-7 needs rescued meals to exist end-to-end (S-1005 asserts they are excluded from
    training yet retained as hypo events)."""
    ds = generate(seed=9, days=120, start=_START)
    rescued = [m for m in ds.meals if m.hypo_treatment]
    assert rescued, "no hypo-rescued meals generated — INV-7 would be untestable e2e"
    for m in rescued:
        assert m.hypo_treatment_g is not None and m.hypo_treatment_g > 0


# --- it cannot write to a database -------------------------------------------


def test_generator_holds_no_database_access() -> None:
    """★ The generator returns plain data. It imports no Session/engine, so merely CALLING
    it can never contaminate a store — persisting is a deliberate act by the caller."""
    pkg = pathlib.Path(__file__).resolve().parents[2] / "synthetic"
    banned = {"sqlalchemy", "data.db", "data.recording"}
    offenders: list[str] = []
    for path in pkg.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "") in banned:
                offenders.append(f"{path.name}: from {node.module}")
            if isinstance(node, ast.Import):
                offenders += [
                    f"{path.name}: import {a.name}" for a in node.names if a.name in banned
                ]
    assert not offenders, f"generator can reach a database: {offenders}"


def test_dataset_is_serialisable_without_a_clock_or_session() -> None:
    ds = generate(seed=13, days=10, start=_START)
    payload = ds.to_jsonable()
    assert isinstance(payload, dict)
    json.dumps(payload, sort_keys=True, default=str)  # must not raise


@pytest.mark.parametrize("days", [1, 7])
def test_small_runs_do_not_crash(days: int) -> None:
    ds = generate(seed=2, days=days, start=_START)
    assert len({m.datetime.date() for m in ds.meals}) == days
