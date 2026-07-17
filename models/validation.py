"""Temporal cross-validation runner — the leakage guard for the whole model (S-701,
REQ-034, 07 §9).

The most likely failure of this project is a model that looks brilliant on retrospective
data and is quietly wrong about a low, and the largest cause of "looks brilliant" is
leakage: basal is constant within a day and days autocorrelate, so any day that straddles
the train/test split is scored on information the model effectively already saw.

``forward_chaining_folds`` (S-404) builds ordered, day-disjoint folds; this runner drives
the **actual model** across them and — adversarially — **re-asserts on every fold** that
``max(train.datetime) < min(test.datetime)`` and that no calendar day appears in both
train and test, raising ``TemporalLeakageError`` rather than silently producing an
optimistic score. The scaler is fit on the train fold only.

This module imports from ``features/`` (it is above the feature layer) but not from
``core`` — a leakage failure is a validation-integrity error, not one of INV-1..9.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from features.cv import forward_chaining_folds
from features.pipeline import make_scaler

_FloatArray = npt.NDArray[np.float64]

# fit_predict(x_train, y_train, x_test) -> test predictions (states or probabilities)
FitPredict = Callable[[_FloatArray, npt.NDArray[np.int_], _FloatArray], npt.ArrayLike]


class TemporalLeakageError(Exception):
    """A fold violates temporal order or day-disjointness — scoring it would leak
    day-level information into test (REQ-034)."""


def assert_temporal_split(
    dates: Sequence[dt.datetime],
    train_idx: Sequence[int],
    test_idx: Sequence[int],
) -> None:
    """Raise ``TemporalLeakageError`` unless the split is a valid temporal one:
    non-empty on both sides, no calendar day shared, and every train row strictly
    before every test row."""
    if not len(train_idx) or not len(test_idx):
        raise TemporalLeakageError("empty train or test fold")

    train_days = {dates[i].date() for i in train_idx}
    test_days = {dates[i].date() for i in test_idx}
    shared = train_days & test_days
    if shared:
        raise TemporalLeakageError(
            f"day-level leakage: day(s) {sorted(shared)} appear in both train and test"
        )

    max_train = max(dates[i] for i in train_idx)
    min_test = min(dates[i] for i in test_idx)
    if not max_train < min_test:
        raise TemporalLeakageError(
            f"temporal order violated: max(train)={max_train.isoformat()} "
            f">= min(test)={min_test.isoformat()}"
        )


@dataclass(frozen=True)
class FoldPrediction:
    fold: int
    train_idx: tuple[int, ...]
    test_idx: tuple[int, ...]
    test_pred: _FloatArray
    test_truth: npt.NDArray[np.int_]


@dataclass(frozen=True)
class TemporalCVResult:
    folds: tuple[FoldPrediction, ...]

    def oos_predictions(self) -> _FloatArray:
        """Out-of-sample predictions concatenated across folds (metric-suite input)."""
        if not self.folds:
            return np.empty((0,), dtype=float)
        return np.concatenate([f.test_pred for f in self.folds], axis=0)

    def oos_truth(self) -> npt.NDArray[np.int_]:
        """Out-of-sample truth states concatenated across folds, aligned with
        :meth:`oos_predictions`."""
        if not self.folds:
            return np.empty((0,), dtype=int)
        return np.concatenate([f.test_truth for f in self.folds], axis=0)


def temporal_cv(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    dates: Sequence[dt.datetime],
    fit_predict: FitPredict,
    *,
    n_splits: int = 3,
    scale: bool = True,
    folds: Sequence[tuple[Sequence[int], Sequence[int]]] | None = None,
) -> TemporalCVResult:
    """Run forward-chaining temporal CV, driving ``fit_predict`` per fold.

    For each fold the temporal invariants are **re-asserted** (defense in depth, even for
    internally-generated folds); the scaler is fit on the train rows only; and the model
    produces out-of-sample predictions for the test rows. ``folds`` may be injected to
    exercise the guard on an adversarial split.
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y)
    split = list(folds) if folds is not None else forward_chaining_folds(list(dates), n_splits)

    results: list[FoldPrediction] = []
    for k, (train_idx, test_idx) in enumerate(split):
        assert_temporal_split(dates, train_idx, test_idx)  # raise on any leaky fold

        train_i = list(train_idx)
        test_i = list(test_idx)
        if scale:
            scaler = make_scaler().fit(x_arr[train_i])
            x_train = np.asarray(scaler.transform(x_arr[train_i]), dtype=float)
            x_test = np.asarray(scaler.transform(x_arr[test_i]), dtype=float)
        else:
            x_train = x_arr[train_i]
            x_test = x_arr[test_i]

        pred = np.asarray(fit_predict(x_train, y_arr[train_i], x_test), dtype=float)
        results.append(
            FoldPrediction(
                fold=k,
                train_idx=tuple(train_i),
                test_idx=tuple(test_i),
                test_pred=pred,
                test_truth=np.asarray(y_arr[test_i]),
            )
        )

    return TemporalCVResult(folds=tuple(results))
