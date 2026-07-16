"""Forward-chaining temporal cross-validation (S-404, 07 §8 / 09 §7).

**Never random.** Basal is constant within a day and days autocorrelate, so a
random split leaks day-level information into test and makes a model look brilliant
while being useless. These folds partition the *unique days* into ordered
contiguous blocks, so every fold has ``max(train day) < min(test day)`` and no day
appears in both train and test.
"""

from __future__ import annotations

import datetime as dt


def _split_contiguous(items: list[dt.date], k: int) -> list[list[dt.date]]:
    """Split ``items`` into ``k`` contiguous, roughly-equal blocks (order kept)."""
    n = len(items)
    sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
    blocks: list[list[dt.date]] = []
    start = 0
    for size in sizes:
        blocks.append(items[start:start + size])
        start += size
    return blocks


def forward_chaining_folds(
    dates: list[dt.datetime], n_splits: int = 3
) -> list[tuple[list[int], list[int]]]:
    """Expanding-window temporal folds over row ``dates``.

    Returns ``[(train_idx, test_idx), …]`` with ``n_splits`` folds. Fold ``k``
    trains on the first ``k+1`` day-blocks and tests on block ``k+1``, so train
    always strictly precedes test and train/test day-sets are disjoint.
    """
    days = [d.date() for d in dates]
    unique_days = sorted(set(days))
    if len(unique_days) < n_splits + 1:
        raise ValueError(
            f"forward-chaining CV needs at least {n_splits + 1} distinct days, "
            f"got {len(unique_days)}"
        )

    blocks = _split_contiguous(unique_days, n_splits + 1)
    folds: list[tuple[list[int], list[int]]] = []
    for k in range(n_splits):
        train_days: set[dt.date] = set()
        for block in blocks[: k + 1]:
            train_days.update(block)
        test_days = set(blocks[k + 1])
        train_idx = [i for i, day in enumerate(days) if day in train_days]
        test_idx = [i for i, day in enumerate(days) if day in test_days]
        folds.append((train_idx, test_idx))
    return folds
