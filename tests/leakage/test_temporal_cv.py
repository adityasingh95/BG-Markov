"""S-701 [SAFETY/LEAKAGE] — the temporal CV runner (SDET, written RED first).

Leakage is how a model comes to look brilliant on retrospective data and be quietly
wrong about a low. The runner drives the ACTUAL model across forward-chaining folds and,
adversarially, re-asserts on every fold that train strictly precedes test and that no
calendar day straddles the split — raising rather than scoring on a leaky fold. See
docs/stories/S-701.md.

RED: `models.validation` does not exist yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from models.validation import (
    TemporalCVResult,
    TemporalLeakageError,
    assert_temporal_split,
    temporal_cv,
)


def _dates(n_days: int, per_day: int = 1) -> list[datetime]:
    base = datetime(2026, 3, 1, 8, 0)
    out: list[datetime] = []
    for d in range(n_days):
        for k in range(per_day):
            out.append(base + timedelta(days=d, hours=3 * k))
    return out


def _identity_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    # a trivial model: predict the train-mean state for every test row
    return np.full(x_test.shape[0], float(np.mean(y_train)))


def test_runner_produces_out_of_sample_predictions_for_every_test_row() -> None:
    dates = _dates(12)
    x = np.arange(12, dtype=float).reshape(-1, 1)
    y = np.array([1, 2, 3, 4, 5] * 2 + [3, 3])
    result = temporal_cv(x, y, dates, _identity_predict, n_splits=3)
    assert isinstance(result, TemporalCVResult)
    assert len(result.folds) == 3
    for fold in result.folds:
        train_days = {dates[i].date() for i in fold.train_idx}
        test_days = {dates[i].date() for i in fold.test_idx}
        assert train_days.isdisjoint(test_days)
        assert max(dates[i] for i in fold.train_idx) < min(dates[i] for i in fold.test_idx)
        assert fold.test_pred.shape[0] == len(fold.test_idx)
    # every test row across folds gets exactly one out-of-sample prediction
    assert result.oos_predictions().shape[0] == result.oos_truth().shape[0]


def test_assert_temporal_split_rejects_a_shared_day() -> None:
    """★ Day-level leakage: the same calendar day in train and test must raise."""
    dates = _dates(4, per_day=2)  # 4 days, two meals each
    # put day-0 morning in train and day-0 afternoon in test → shared day
    train_idx = [0, 2, 3]   # day0-am, day1-am, day1-pm
    test_idx = [1, 4]       # day0-pm (SHARES day 0 with train), day2-am
    with pytest.raises(TemporalLeakageError):
        assert_temporal_split(dates, train_idx, test_idx)


def test_assert_temporal_split_rejects_out_of_order() -> None:
    """max(train) >= min(test) is a temporal-order violation."""
    dates = _dates(5)
    train_idx = [2, 3, 4]   # later days
    test_idx = [0, 1]       # earlier days → order violated
    with pytest.raises(TemporalLeakageError):
        assert_temporal_split(dates, train_idx, test_idx)


def test_temporal_cv_raises_on_an_injected_leaky_fold() -> None:
    """★ Hand the runner a leaky fold (shared day) → it raises, never scores."""
    dates = _dates(4, per_day=2)
    x = np.arange(len(dates), dtype=float).reshape(-1, 1)
    y = np.array([1, 2, 3, 4, 5, 1, 2, 3])
    leaky = [([0, 1, 2], [3, 0])]  # index 0 is in both train and test
    with pytest.raises(TemporalLeakageError):
        temporal_cv(x, y, dates, _identity_predict, folds=leaky)


def test_shuffled_random_split_is_rejected() -> None:
    """★ A shuffled/interleaved split (days on both sides) must be rejected — the
    'looks brilliant, is useless' path is blocked."""
    dates = _dates(8)
    x = np.arange(8, dtype=float).reshape(-1, 1)
    y = np.array([1, 2, 3, 4, 5, 1, 2, 3])
    rng = np.random.RandomState(0)
    perm = rng.permutation(8)
    shuffled = [(list(perm[:5]), list(perm[5:]))]  # random split, days interleaved
    with pytest.raises(TemporalLeakageError):
        temporal_cv(x, y, dates, _identity_predict, folds=shuffled)


def test_scaler_is_fit_on_train_fold_only() -> None:
    """A giant outlier in the test fold does not shift the train-fold centering the
    model is fit against."""
    dates = _dates(8)
    x = np.array([[0.0], [1.0], [2.0], [3.0], [4.0], [5.0], [6.0], [10_000.0]])
    y = np.array([1, 2, 3, 4, 5, 1, 2, 3])
    captured: dict[str, np.ndarray] = {}

    def _capture(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
        captured["train"] = x_train
        return np.zeros(x_test.shape[0])

    temporal_cv(x, y, dates, _capture, n_splits=3, scale=True)
    # the last fold's train rows are standardised on train stats only → ~zero mean,
    # unaffected by the 10_000 outlier that lives in a test fold.
    assert abs(float(captured["train"].mean())) < 1e-6


def test_runs_against_the_real_ordinal_fit() -> None:
    """★ The harness drives the ACTUAL ordinal model and yields out-of-sample
    probabilities (each test row sums to 1) — no leakage raised."""
    from models.ordinal import fit_ordinal

    rng = np.random.RandomState(0)
    n_days = 40
    dates = _dates(n_days, per_day=3)
    n = len(dates)
    pre_bg = rng.uniform(40.0, 320.0, n)
    carbs = rng.uniform(0.0, 90.0, n)
    latent = 0.9 * pre_bg + 0.3 * carbs + rng.normal(0.0, 18.0, n)
    from models.state import bg_to_state

    y = np.array([bg_to_state(v) for v in latent], dtype=int)
    x = np.column_stack([pre_bg, carbs]).astype(float)

    def _fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
        fit = fit_ordinal(x_train, y_train, confidence_weights=np.ones(len(y_train)))
        return fit.predict_proba(x_test)

    result = temporal_cv(x, y, dates, _fit_predict, n_splits=3, scale=True)
    preds = result.oos_predictions()
    assert preds.shape[0] == result.oos_truth().shape[0]
    assert np.allclose(preds.sum(axis=1), 1.0)  # genuine out-of-sample probabilities
