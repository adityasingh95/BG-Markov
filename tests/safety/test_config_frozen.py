"""S-103 [SAFETY] — config immutability + the ICR-presence flag.

Adversarial by intent (CLAUDE.md: assume a future refactor tries to weaken
this). The config must be immutable after load so no clinical constant can be
mutated mid-run, and `icr_present` must stay a computed, read-only flag.

**S-1011 (DL-035):** this property was `prescriptive_enabled` while Gate 2 / INV-1
existed. With that gate retired it enables nothing, so it is named for what it
actually is — a config-completeness flag. Keeping the old name would invite a
future reader to misread `prescriptive_enabled is False` as "the dose path is
safely off", which would be false. Enforcement now lives in `recommend_bolus`
(a plain `ValueError` on a missing or <= 0 ICR).
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from core.config import ClinicalConfig


@given(
    icr=st.one_of(
        st.none(),
        st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
    )
)
def test_icr_present_iff_icr_is_set(icr: float | None) -> None:
    """Property: icr_present == (icr is not None), for every icr."""
    cfg = ClinicalConfig(icr=icr)
    assert cfg.icr_present == (icr is not None)


def test_icr_none_means_not_present() -> None:
    """icr is None ⇒ icr_present is False, unconditionally."""
    assert ClinicalConfig(icr=None).icr_present is False


def test_config_is_frozen_every_field_mutation_raises() -> None:
    """Mutating any field on a loaded config raises (frozen) — no mid-run drift."""
    cfg = ClinicalConfig(icr=8.3, isf=30.0)
    for field, value in [
        ("icr", 9.0),
        ("isf", 999.0),
        ("target_bg", 200),
        ("max_bolus_u", 25.0),
        ("iob_tp", 10.0),
    ]:
        with pytest.raises(ValidationError):
            setattr(cfg, field, value)


def test_icr_present_cannot_be_assigned() -> None:
    """It is not a settable field — assigning it raises. It reports state; it never grants it."""
    cfg = ClinicalConfig(icr=None)
    with pytest.raises((ValidationError, AttributeError)):
        cfg.icr_present = True  # type: ignore[misc]
    assert cfg.icr_present is False


def test_icr_present_cannot_be_injected_at_construction() -> None:
    """Passing icr_present=True with icr=None must NOT yield an enabled
    config. extra='forbid' rejects the injected key; the gate cannot be opened
    by a config value (03 §3: no config-flag bypass)."""
    with pytest.raises(ValidationError):
        ClinicalConfig(icr=None, icr_present=True)  # type: ignore[call-arg]


@given(
    other_isf=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    bad_cap=st.floats(min_value=25.0001, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_ceiling_cannot_be_raised_regardless_of_other_fields(
    other_isf: float, bad_cap: float
) -> None:
    """No combination of other fields lets max_bolus_u exceed the 25 U ceiling."""
    with pytest.raises(ValidationError):
        ClinicalConfig(isf=other_isf, max_bolus_u=bad_cap)
