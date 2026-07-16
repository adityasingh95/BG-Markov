"""S-502 [SAFETY] — ISF derivation from correction events (SDET, RED first).

ISF is the most dangerous number in the system (denominator of the correction
term). Derive it from clean correction events, but gate it: >=5 events, never a
silent swap, and a non-positive derived value is a hard stop. See
docs/stories/S-502.md.

RED: `models.isf` does not exist yet.
"""

from __future__ import annotations

import pytest

from core.safety import SafetyViolation
from models.isf import MIN_CLEAN_EVENTS, derive_isf

# Each triple implies ISF (bg_before - bg_after)/units = 30.
_ISF30 = [
    (250.0, 100.0, 5.0),  # 150/5 = 30
    (200.0, 140.0, 2.0),  # 60/2  = 30
    (240.0, 120.0, 4.0),  # 120/4 = 30
    (180.0, 120.0, 2.0),  # 60/2  = 30
    (300.0, 150.0, 5.0),  # 150/5 = 30
]


def test_min_clean_events_is_five() -> None:
    assert MIN_CLEAN_EVENTS == 5


def test_five_events_apply_and_source_becomes_derived() -> None:
    r = derive_isf(_ISF30, current_isf=30.0, current_source="default")
    assert r.n_clean == 5
    assert r.applied is True
    assert r.derived_isf == pytest.approx(30.0)
    assert r.isf == pytest.approx(30.0)
    assert r.isf_source == "derived"


def test_four_events_keep_default_but_report_derived() -> None:
    r = derive_isf(_ISF30[:4], current_isf=45.0, current_source="endo")
    assert r.n_clean == 4
    assert r.applied is False
    assert r.derived_isf == pytest.approx(30.0)  # reported...
    assert r.isf == 45.0                          # ...but the current value stays
    assert r.isf_source == "endo"                 # not silently swapped


def test_derived_can_differ_from_default_and_is_applied_at_five() -> None:
    # five events each implying ISF 50.
    events = [(200.0, 100.0, 2.0)] * 5  # 100/2 = 50
    r = derive_isf(events, current_isf=30.0, current_source="default")
    assert r.applied is True
    assert r.isf == pytest.approx(50.0)
    assert r.isf_source == "derived"


def test_no_events_keeps_default_and_reports_nothing() -> None:
    r = derive_isf([], current_isf=30.0, current_source="default")
    assert r.n_clean == 0
    assert r.applied is False
    assert r.derived_isf is None
    assert r.isf == 30.0
    assert r.isf_source == "default"


def test_non_positive_derived_isf_raises_even_at_five_events() -> None:
    """★ BG rose after a correction ⇒ derived ISF <= 0 ⇒ insulin appears not to
    lower glucose. Hard stop — never applied."""
    rose = [(150.0, 170.0, 4.0)] * 5  # (150-170)/4 = -5
    with pytest.raises(SafetyViolation):
        derive_isf(rose, current_isf=30.0, current_source="default")


def test_zero_derived_isf_raises() -> None:
    flat = [(150.0, 150.0, 4.0)] * 5  # 0/4 = 0
    with pytest.raises(SafetyViolation):
        derive_isf(flat, current_isf=30.0, current_source="default")
