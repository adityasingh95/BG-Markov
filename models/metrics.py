"""The reporting metric suite (S-702, REQ-035, 07 §9).

The metric decides what "good" means, and on this imbalanced 5-class problem plain
accuracy rewards predicting the majority state while never catching a low — a model
useless in exactly the way that endangers her, wearing a good grade. So **plain accuracy
is not a function in this module** (and ``accuracy_score`` appears nowhere — forbidden
guard). The suite is built from the rare-event recall at controlled cost (hypo recall @
FAR — the PRIMARY metric), whether the probabilities are honest (calibration, Brier), and
how clinically dangerous the errors are (Clarke grid, severe-state-error).

Pure — imports only ``numpy``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

_FloatArray = npt.NDArray[np.float64]


# --- hypo recall @ fixed FAR (PRIMARY) --------------------------------------


@dataclass(frozen=True)
class HypoRecallResult:
    recall: float          # of the lows that happened, the fraction flagged
    far: float             # achieved false-alarm rate (<= target)
    threshold: float       # score threshold applied
    target_far: float


def hypo_recall_at_far(
    hypo_score: npt.ArrayLike,
    is_hypo: npt.ArrayLike,
    *,
    target_far: float = 0.10,
) -> HypoRecallResult:
    """Hypo recall at a fixed false-alarm rate — the PRIMARY metric (07 §9).

    Choose the score threshold that **maximises recall of hypo events subject to
    ``FAR ≤ target_far``**, where ``FAR`` is false positives over non-hypo rows. She
    cannot feel a low, so this — not accuracy — is what "good" means.
    """
    score = np.asarray(hypo_score, dtype=float)
    truth = np.asarray(is_hypo, dtype=bool)
    n_pos = int(truth.sum())
    n_neg = int((~truth).sum())
    if n_pos == 0 or n_neg == 0:
        raise ValueError("hypo_recall_at_far needs both hypo and non-hypo rows")

    # Candidate thresholds: each unique score, plus one above the max (flag nothing).
    candidates = np.unique(score)
    candidates = np.concatenate([candidates, [candidates[-1] + 1.0]])

    best = HypoRecallResult(recall=0.0, far=0.0, threshold=float(candidates[-1]),
                            target_far=target_far)
    best_recall = -1.0
    for thr in candidates:
        flagged = score >= thr
        tp = int(np.sum(flagged & truth))
        fp = int(np.sum(flagged & ~truth))
        far = fp / n_neg
        if far > target_far + 1e-12:
            continue
        recall = tp / n_pos
        if recall > best_recall:
            best_recall = recall
            best = HypoRecallResult(recall=recall, far=far, threshold=float(thr),
                                    target_far=target_far)
    return best


# --- Brier ------------------------------------------------------------------


def brier_score(
    proba: npt.ArrayLike, y_true: npt.ArrayLike, *, states: tuple[int, ...]
) -> float:
    """Multiclass Brier score: mean over rows of ``Σ_k (p_k − 1[y=k])²`` (columns
    ordered by ``states``). Lower is better; a perfect one-hot prediction scores 0."""
    p = np.asarray(proba, dtype=float)
    y = np.asarray(y_true)
    onehot = np.zeros_like(p)
    index = {s: i for i, s in enumerate(states)}
    for row, label in enumerate(y.tolist()):
        onehot[row, index[int(label)]] = 1.0
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


# --- reliability / calibration ----------------------------------------------


@dataclass(frozen=True)
class CalibrationBin:
    mean_predicted: float
    observed_frequency: float
    count: int


def reliability_curve(
    prob: npt.ArrayLike, is_event: npt.ArrayLike, *, n_bins: int = 10
) -> tuple[CalibrationBin, ...]:
    """The reliability-diagram data: for each non-empty probability bin, the mean
    predicted probability vs the observed event frequency (07 §9 — "if it says 20%, it
    must happen 20% of the time")."""
    p = np.asarray(prob, dtype=float)
    y = np.asarray(is_event, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[CalibrationBin] = []
    for lo, hi, last in zip(edges[:-1], edges[1:], range(n_bins), strict=False):
        mask = (p >= lo) & (p < hi) if last < n_bins - 1 else (p >= lo) & (p <= hi)
        count = int(mask.sum())
        if count == 0:
            continue
        bins.append(
            CalibrationBin(
                mean_predicted=float(p[mask].mean()),
                observed_frequency=float(y[mask].mean()),
                count=count,
            )
        )
    return tuple(bins)


# --- MAE --------------------------------------------------------------------


def mae_mgdl(predicted_bg: npt.ArrayLike, true_bg: npt.ArrayLike) -> float:
    """Mean absolute error (mg/dL) on the continuous baseline prediction."""
    pred = np.asarray(predicted_bg, dtype=float)
    true = np.asarray(true_bg, dtype=float)
    return float(np.mean(np.abs(pred - true)))


# --- Clarke error grid ------------------------------------------------------


def clarke_zone(reference_bg: float, predicted_bg: float) -> str:
    """Clarke Error Grid zone (A–E) for a ``(reference, predicted)`` mg/dL pair.

    The grid weights error by **clinical danger**, not magnitude. The dangerous zones
    are **D** (failure to detect — truly low/high, predicted normal) and **E** (erroneous
    treatment — the reading is reversed). Zone A is clinically accurate; B is benign
    error.
    """
    ref = float(reference_bg)
    pred = float(predicted_bg)
    if ref <= 0.0:
        raise ValueError(f"reference BG must be positive, got {ref}")

    # A — within 20%, or both in the hypo range
    if (ref < 70.0 and pred < 70.0) or abs(pred - ref) <= 0.2 * ref:
        return "A"
    # E — erroneous treatment (reading reversed across the range)
    if (ref >= 180.0 and pred <= 70.0) or (ref <= 70.0 and pred >= 180.0):
        return "E"
    # C — overcorrection
    if (70.0 <= ref <= 290.0 and pred >= ref + 110.0) or (
        130.0 <= ref <= 180.0 and pred <= 1.4 * ref - 182.0
    ):
        return "C"
    # D — failure to detect (truly abnormal, predicted normal)
    if (ref >= 240.0 and 70.0 <= pred <= 180.0) or (ref <= 70.0 and 70.0 <= pred <= 180.0):
        return "D"
    # B — benign error
    return "B"


def clarke_grid(reference: npt.ArrayLike, predicted: npt.ArrayLike) -> dict[str, int]:
    """Count of ``(reference, predicted)`` pairs falling in each Clarke zone A–E."""
    ref = np.asarray(reference, dtype=float)
    pred = np.asarray(predicted, dtype=float)
    counts = {z: 0 for z in ("A", "B", "C", "D", "E")}
    for r, p in zip(ref.tolist(), pred.tolist(), strict=True):
        counts[clarke_zone(r, p)] += 1
    return counts


# --- ordinal error rates (no plain accuracy) --------------------------------


def off_by_one_rate(pred_state: npt.ArrayLike, true_state: npt.ArrayLike) -> float:
    """Fraction of predictions off by **exactly one** state — the minor, ordinal-aware
    error rate (07 §9)."""
    diff = np.abs(np.asarray(pred_state, dtype=int) - np.asarray(true_state, dtype=int))
    return float(np.mean(diff == 1))


def severe_state_error_rate(pred_state: npt.ArrayLike, true_state: npt.ArrayLike) -> float:
    """Fraction of predictions off by **two or more** states — the catastrophic errors
    (e.g. predicting State 4 when the truth is State 1)."""
    diff = np.abs(np.asarray(pred_state, dtype=int) - np.asarray(true_state, dtype=int))
    return float(np.mean(diff >= 2))
