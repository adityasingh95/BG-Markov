"""S-203 — validity engine (SDET, written RED first).

The six exclusion rules of 04 §5, with ALL applicable reasons recorded — not
just the first. `is_valid` iff the reason list is empty.
"""

from __future__ import annotations

import pytest

from core.validity import exclusion_reasons, is_valid


def _reasons(**overrides: object) -> list[str]:
    """A valid baseline meal; override one field to trigger a rule."""
    fields: dict[str, object] = {
        "post_bg": 140,
        "elapsed_min": 120,
        "hypo_treatment": False,
        "snack_during_window": False,
        "minutes_since_prev_meal": 600,
        "macro_confidence": 95,
    }
    fields.update(overrides)
    return exclusion_reasons(**fields)  # type: ignore[arg-type]


def test_baseline_meal_is_valid() -> None:
    assert _reasons() == []
    assert is_valid(_reasons()) is True


@pytest.mark.parametrize(
    ("elapsed", "valid"), [(105, True), (135, True), (104, False), (136, False)]
)
def test_elapsed_window_boundaries(elapsed: int, valid: bool) -> None:
    reasons = _reasons(elapsed_min=elapsed)
    if valid:
        assert "outside_window" not in reasons
        assert reasons == []
    else:
        assert reasons == ["outside_window"]


def test_missing_outcome() -> None:
    # No post reading at all: missing_outcome, and no spurious outside_window.
    assert _reasons(post_bg=None, elapsed_min=None) == ["missing_outcome"]


def test_rescued_reason() -> None:
    assert _reasons(hypo_treatment=True) == ["rescued"]


def test_uncontrolled_intake_reason() -> None:
    assert _reasons(snack_during_window=True) == ["uncontrolled_intake"]


@pytest.mark.parametrize(("gap", "contaminated"), [(179, True), (180, False), (181, False)])
def test_iob_cob_contamination(gap: int, contaminated: bool) -> None:
    reasons = _reasons(minutes_since_prev_meal=gap)
    assert ("iob_cob_contamination" in reasons) is contaminated


def test_no_contamination_when_no_previous_meal() -> None:
    assert _reasons(minutes_since_prev_meal=None) == []


@pytest.mark.parametrize(("conf", "low"), [(49, True), (50, False), (51, False)])
def test_low_confidence(conf: int, low: bool) -> None:
    reasons = _reasons(macro_confidence=conf)
    assert ("low_confidence" in reasons) is low


def test_all_applicable_reasons_recorded_not_just_first() -> None:
    reasons = _reasons(
        elapsed_min=200,          # outside_window
        hypo_treatment=True,      # rescued
        snack_during_window=True, # uncontrolled_intake
        minutes_since_prev_meal=60,  # iob_cob_contamination
        macro_confidence=10,      # low_confidence
    )
    assert set(reasons) == {
        "outside_window",
        "rescued",
        "uncontrolled_intake",
        "iob_cob_contamination",
        "low_confidence",
    }
    # canonical order preserved
    assert reasons == sorted(
        reasons,
        key=[
            "missing_outcome",
            "outside_window",
            "rescued",
            "uncontrolled_intake",
            "iob_cob_contamination",
            "low_confidence",
        ].index,
    )
    assert is_valid(reasons) is False
