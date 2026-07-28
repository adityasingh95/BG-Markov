"""S-1012 [SAFETY] — "are its percentages honest?" (SDET, written RED first).

The fifth Gate-1 condition. Not *"is the model good?"* — that is hypo recall vs the
baseline. This asks only: **when it puts a number on the risk, is the number true?**

A model can rank meals correctly and still be badly wrong about magnitudes — saying 30%
when the truth is 60%. For someone who can feel a low coming that is an annoyance she
corrects herself. For her, **the number is the warning**.

The rule is operator-approved (OQ-9, DL-042) and deliberately coarse and **asymmetric**.
These tests exist mostly to keep it that way: the natural refactor is `abs(gap)`, which
reads cleaner, silently prices "told her she was fine when she wasn't" the same as a
false alarm, and shows up nowhere in a green build.

RED: `models.metrics.hypo_calibration` does not exist.
"""

from __future__ import annotations

import numpy as np
import pytest

from models.metrics import (
    HYPO_CALIB_MAX_OVERSTATEMENT,
    HYPO_CALIB_MAX_UNDERSTATEMENT,
    HYPO_CALIB_MIN_BUCKET_N,
    hypo_calibration,
)


def _bucket(claimed: float, observed_rate: float, n: int) -> tuple[list[float], list[int]]:
    """n predictions all claiming ``claimed``, of which ``observed_rate`` actually went low."""
    n_hypo = round(observed_rate * n)
    return [claimed] * n, [1] * n_hypo + [0] * (n - n_hypo)


def _verdict(*buckets: tuple[list[float], list[int]]):  # type: ignore[no-untyped-def]
    scores: list[float] = []
    hypos: list[int] = []
    for s, h in buckets:
        scores += s
        hypos += h
    return hypo_calibration(np.array(scores), np.array(hypos))


# --- the constants are the approved rule, not a team choice -------------------


def test_the_approved_constants_are_what_dl042_says() -> None:
    """★ These four numbers were escalated and answered (OQ-9 → DL-042). Pinning them
    means a change is a visible change to an approved decision, not a tweak."""
    from models.metrics import HYPO_CALIB_BUCKET_EDGES

    assert HYPO_CALIB_BUCKET_EDGES == (0.20, 0.50)
    assert HYPO_CALIB_MIN_BUCKET_N == 20
    assert HYPO_CALIB_MAX_UNDERSTATEMENT == 0.10
    assert HYPO_CALIB_MAX_OVERSTATEMENT == 0.20
    assert HYPO_CALIB_MAX_UNDERSTATEMENT < HYPO_CALIB_MAX_OVERSTATEMENT, (
        "the tolerance for understating risk must be STRICTER than for overstating it"
    )


# --- ★ THE ASYMMETRY — the point of the whole story ---------------------------


def test_the_same_gap_gives_opposite_verdicts_in_the_two_directions() -> None:
    """★ THE TEST THIS STORY EXISTS FOR.

    Both buckets are off by exactly 0.15. One passes, one fails.

    - Claimed 0.20, actually 0.35 → it **understated** the risk. It told her a meal was
      probably fine and it was not. That is the failure this system exists to prevent.
    - Claimed 0.50, actually 0.35 → it **overstated**. She checked and was fine. That
      costs a fingerstick, not a harm.

    If a future refactor writes `abs(gap)` — which reads cleaner and is the obvious
    simplification — this test is what dies. Nothing else would notice.
    """
    understated = _verdict(_bucket(claimed=0.20, observed_rate=0.35, n=40))
    assert understated.is_acceptable is False

    overstated = _verdict(_bucket(claimed=0.50, observed_rate=0.35, n=40))
    assert overstated.is_acceptable is True


def test_understatement_boundary_is_exact() -> None:
    """0.10 out passes; more does not."""
    ok = _verdict(_bucket(claimed=0.20, observed_rate=0.30, n=100))
    assert ok.is_acceptable is True
    bad = _verdict(_bucket(claimed=0.20, observed_rate=0.31, n=100))
    assert bad.is_acceptable is False


def test_overstatement_boundary_is_exact() -> None:
    """0.20 out passes; more does not."""
    ok = _verdict(_bucket(claimed=0.60, observed_rate=0.40, n=100))
    assert ok.is_acceptable is True
    bad = _verdict(_bucket(claimed=0.61, observed_rate=0.40, n=100))
    assert bad.is_acceptable is False


def test_the_gap_is_signed_not_absolute() -> None:
    """★ Pins the sign convention directly, so the asymmetry cannot be lost in a
    rename. Positive gap = observed above claimed = the model UNDERSTATED the risk."""
    v = _verdict(_bucket(claimed=0.20, observed_rate=0.35, n=40))
    judged = [b for b in v.buckets if b.counts]
    assert len(judged) == 1
    assert judged[0].gap == pytest.approx(0.15), "gap must be observed − claimed, signed"


# --- the minimum bucket size --------------------------------------------------


def test_nineteen_is_not_evidence_and_twenty_is() -> None:
    """★ At ~150 meals with 15–20 lows, a handful of events per bucket is noise wearing
    the costume of precision. Below the floor a bucket is not judged at all."""
    nineteen = _verdict(_bucket(claimed=0.20, observed_rate=0.20, n=19))
    assert [b.counts for b in nineteen.buckets if b.n] == [False]
    assert nineteen.is_acceptable is False, "nothing judgeable ⇒ not acceptable"

    twenty = _verdict(_bucket(claimed=0.20, observed_rate=0.20, n=20))
    assert [b.counts for b in twenty.buckets if b.n] == [True]
    assert twenty.is_acceptable is True


def test_a_bucket_below_the_floor_is_still_reported() -> None:
    """It must be visible on the dashboard as "too few to judge" — never silently
    dropped. A bucket that vanishes cannot be reasoned about by the operator."""
    v = _verdict(
        _bucket(claimed=0.10, observed_rate=0.10, n=50),   # judged
        _bucket(claimed=0.60, observed_rate=0.90, n=5),    # far off, but too few
    )
    high = [b for b in v.buckets if b.lower >= 0.50][0]
    assert high.n == 5
    assert high.counts is False
    assert v.is_acceptable is True, "an unjudgeable bucket cannot fail the check either"


def test_an_unjudgeable_bucket_does_not_rescue_a_failing_one() -> None:
    """Symmetric to the above: too-few cuts both ways and decides nothing."""
    v = _verdict(
        _bucket(claimed=0.20, observed_rate=0.40, n=40),   # judged, understates badly
        _bucket(claimed=0.60, observed_rate=0.60, n=5),    # perfect, but too few
    )
    assert v.is_acceptable is False


# --- fails closed -------------------------------------------------------------


def test_no_predictions_is_not_acceptable() -> None:
    """★ Day one. An empty result is *no evidence*, not *no problem*."""
    v = hypo_calibration(np.array([]), np.array([]))
    assert v.is_acceptable is False
    assert v.n_judged == 0


def test_everything_below_the_floor_fails_closed_with_an_honest_reason() -> None:
    """★ The tempting reading of an empty result is "nothing looks wrong". The reason
    text must say it could not judge, not that the model is fine — this string is what
    the operator reads on the screen where Gate 1 gets opened."""
    v = _verdict(
        _bucket(claimed=0.10, observed_rate=0.10, n=8),
        _bucket(claimed=0.30, observed_rate=0.30, n=8),
        _bucket(claimed=0.70, observed_rate=0.70, n=8),
    )
    assert v.is_acceptable is False
    assert v.n_judged == 0
    reason = v.reason.lower()
    assert "not enough" in reason or "too few" in reason
    for forbidden in ("acceptable", "honest", "good", "fine", "pass"):
        assert forbidden not in reason, (
            f"a cannot-judge reason must not read as reassurance; found {forbidden!r}"
        )


# --- bucketing ----------------------------------------------------------------


def test_the_three_buckets_partition_zero_to_one_with_no_gaps() -> None:
    """Every score lands in exactly one bucket; the edges belong to the upper bucket."""
    v = _verdict(
        _bucket(claimed=0.00, observed_rate=0.0, n=25),
        _bucket(claimed=0.19, observed_rate=0.2, n=25),
        _bucket(claimed=0.20, observed_rate=0.2, n=25),   # edge → middle
        _bucket(claimed=0.50, observed_rate=0.5, n=25),   # edge → top
        _bucket(claimed=1.00, observed_rate=1.0, n=25),
    )
    assert len(v.buckets) == 3
    assert sum(b.n for b in v.buckets) == 125, "every prediction must land in a bucket"
    low, mid, high = v.buckets
    assert low.n == 50    # 0.00 and 0.19          → [0.00, 0.20)
    assert mid.n == 25    # 0.20 (edge → upper)    → [0.20, 0.50)
    assert high.n == 50   # 0.50 (edge → upper), 1.00 → [0.50, 1.00]


def test_a_well_calibrated_model_across_all_three_buckets_is_acceptable() -> None:
    v = _verdict(
        _bucket(claimed=0.10, observed_rate=0.10, n=60),
        _bucket(claimed=0.35, observed_rate=0.35, n=40),
        _bucket(claimed=0.75, observed_rate=0.75, n=20),
    )
    assert v.is_acceptable is True
    assert v.n_judged == 3


def test_one_bad_bucket_fails_the_whole_check() -> None:
    """★ Honest in two ranges out of three is not honest. She only needs to be misled
    once, and the failure is not confined to the range it occurs in."""
    v = _verdict(
        _bucket(claimed=0.10, observed_rate=0.10, n=60),
        _bucket(claimed=0.35, observed_rate=0.35, n=40),
        _bucket(claimed=0.60, observed_rate=0.85, n=40),   # understates badly
    )
    assert v.is_acceptable is False
