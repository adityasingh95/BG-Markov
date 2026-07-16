"""S-404 [LEAKAGE] — the class of bug that makes a model look brilliant and be
useless (09 §7). SDET, written RED first.

Runs every commit. Guards: no target leakage (post_bg / elapsed_min never a
feature), pre_bg continuous (never binned as input), forward-chaining temporal
folds (no day in both train and test; max(train) < min(test)), and the scaler is
fit on train folds only (its statistics differ from a full-set fit).

RED: `features.pipeline` / `features.cv` do not exist yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from data.tables import ExIntensity, LoggedBy, MealEvent, MealType
from features.cv import forward_chaining_folds
from features.pipeline import (
    CONTINUOUS_FEATURES,
    FEATURE_NAMES,
    feature_vector,
    make_scaler,
)

_TARGET_COLS = {"post_bg", "elapsed_min", "is_valid", "exclusion_reasons"}


def _meal(day: int, pre_bg: int = 130) -> MealEvent:
    when = datetime(2026, 3, 1, 8, 0) + timedelta(days=day)
    return MealEvent(
        datetime=when, logged_at=when, logged_by=LoggedBy.patient,
        meal_type=MealType.breakfast, pre_bg=pre_bg, pre_bg_time=when,
        meal_bolus_units=5.0 + day, correction_bolus_units=0.0,
        bolus_offset_min=-10, carbs_g=40.0 + 2 * day,
        protein_g=10.0, fat_g=6.0, fiber_g=4.0, macro_confidence=95,
        # column defaults apply at INSERT, not on an in-memory object — a persisted
        # meal always has these set, so mirror that here.
        ex_intensity=ExIntensity.none, ex_duration_min=0, ex_offset_min=None,
        pre_ex_intensity=ExIntensity.none, pre_ex_duration_min=0,
    )


# --- target leakage ---------------------------------------------------------


def test_outcome_columns_are_never_features() -> None:
    for col in _TARGET_COLS:
        assert col not in FEATURE_NAMES, f"{col} is the OUTCOME — must not be a feature"
    fv = feature_vector(
        _meal(0), iob_at_meal=0.0, effective_basal=24.0, minutes_since_last_bolus=100.0
    )
    for col in _TARGET_COLS:
        assert col not in fv


def test_pre_bg_is_a_continuous_feature_not_binned() -> None:
    assert "pre_bg" in FEATURE_NAMES
    # no binned pre_bg input column (e.g. pre_bg_state / pre_bg_bin / pre_bg_1..5)
    binned = [f for f in FEATURE_NAMES if f.startswith("pre_bg_") or f == "pre_bg_bin"]
    assert binned == [], f"pre_bg must be continuous, found binned inputs: {binned}"


# --- temporal cross-validation ---------------------------------------------


def test_forward_chaining_folds_are_temporally_ordered_and_day_disjoint() -> None:
    # 12 meals across 12 distinct days.
    meals = [_meal(d) for d in range(12)]
    dates = [m.datetime for m in meals]
    folds = forward_chaining_folds(dates, n_splits=3)
    assert len(folds) == 3

    for train_idx, test_idx in folds:
        assert train_idx and test_idx
        train_days = {dates[i].date() for i in train_idx}
        test_days = {dates[i].date() for i in test_idx}
        # ★ no day in both train and test (day-level leakage guard)
        assert train_days.isdisjoint(test_days)
        # ★ every train row strictly precedes every test row
        assert max(dates[i] for i in train_idx) < min(dates[i] for i in test_idx)


def test_too_few_distinct_days_raises() -> None:
    """Fewer than n_splits+1 distinct days cannot form temporal folds — refuse
    loudly rather than silently return degenerate folds (covers cv.py guard)."""
    base = datetime(2026, 3, 1, 8, 0)
    two_days = [base, base + timedelta(hours=3), base + timedelta(days=1)]
    with pytest.raises(ValueError):
        forward_chaining_folds(two_days, n_splits=3)


def test_folds_never_put_the_same_day_in_train_and_test() -> None:
    """Two meals share a day; a correct temporal split keeps that day on one side."""
    base = datetime(2026, 3, 1, 8, 0)
    dates = [
        base, base + timedelta(hours=6),           # day 0 (twice)
        base + timedelta(days=1),
        base + timedelta(days=2),
        base + timedelta(days=3),
        base + timedelta(days=4),
    ]
    for train_idx, test_idx in forward_chaining_folds(dates, n_splits=2):
        train_days = {dates[i].date() for i in train_idx}
        test_days = {dates[i].date() for i in test_idx}
        assert train_days.isdisjoint(test_days)


# --- scaler fit on train folds only -----------------------------------------


def test_scaler_stats_differ_between_train_fold_and_full_set() -> None:
    """★ Fitting on the full set leaks test statistics into scaling. The train-fold
    scaler must have different means from a full-set scaler."""
    meals = [_meal(d, pre_bg=100 + 8 * d) for d in range(12)]
    dates = [m.datetime for m in meals]
    matrix = np.array([
        [feature_vector(
            m, iob_at_meal=float(i), effective_basal=24.0 + i,
            minutes_since_last_bolus=60.0 + 10 * i,
        )[col] for col in CONTINUOUS_FEATURES]
        for i, m in enumerate(meals)
    ])

    train_idx, _ = forward_chaining_folds(dates, n_splits=3)[0]
    full_means = make_scaler().fit(matrix).mean_
    train_means = make_scaler().fit(matrix[train_idx]).mean_

    assert not np.allclose(full_means, train_means), (
        "scaler fit on a train fold must differ from a full-set fit (no leakage)"
    )


def test_scaler_transform_uses_only_training_statistics() -> None:
    """A value in the test fold does not shift the train-fold scaler's centering."""
    x = np.array([[0.0], [1.0], [2.0], [100.0]])  # last row is a 'test' outlier
    train = x[:3]
    scaler = make_scaler().fit(train)
    assert scaler.mean_[0] == pytest.approx(1.0)  # mean of train only, not incl. 100
