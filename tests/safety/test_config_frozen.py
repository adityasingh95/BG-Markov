"""S-103 [SAFETY] — config immutability + the INV-1 precondition boundary.

Adversarial by intent (CLAUDE.md: assume a future refactor tries to weaken
this). `prescriptive_enabled` must be a computed, read-only *precondition* —
never a settable bypass — and the config must be immutable after load so no
clinical constant can be mutated mid-run.

These do NOT test INV-1 itself (that is enforced live in core/safety.py, S-104).
They test that the config cannot be used to *defeat* it.
"""

from __future__ import annotations

import pytest
from core.config import ClinicalConfig
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError


@given(
    icr=st.one_of(
        st.none(),
        st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
    )
)
def test_prescriptive_enabled_iff_icr_present(icr: float | None) -> None:
    """Property: prescriptive_enabled == (icr is not None), for every icr."""
    cfg = ClinicalConfig(icr=icr)
    assert cfg.prescriptive_enabled == (icr is not None)


def test_icr_none_forces_prescriptive_disabled() -> None:
    """icr is None ⇒ prescriptive_enabled is False, unconditionally."""
    assert ClinicalConfig(icr=None).prescriptive_enabled is False


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


def test_prescriptive_enabled_cannot_be_assigned() -> None:
    """It is not a settable field — assigning it raises, so it cannot be a bypass."""
    cfg = ClinicalConfig(icr=None)
    with pytest.raises((ValidationError, AttributeError)):
        cfg.prescriptive_enabled = True  # type: ignore[misc]
    assert cfg.prescriptive_enabled is False


def test_prescriptive_enabled_cannot_be_injected_at_construction() -> None:
    """Passing prescriptive_enabled=True with icr=None must NOT yield an enabled
    config. extra='forbid' rejects the injected key; the gate cannot be opened
    by a config value (03 §3: no config-flag bypass)."""
    with pytest.raises(ValidationError):
        ClinicalConfig(icr=None, prescriptive_enabled=True)  # type: ignore[call-arg]


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
