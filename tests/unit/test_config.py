"""S-103 — clinical config loader: value validation (SDET, written RED first).

The config is the typed source of the `07 §1` clinical constants. It must reject
malformed input at load time — an over-dosing ISF, an out-of-range dose cap, or
an unknown key that would silently do nothing.
"""

from __future__ import annotations

import pytest
from core.config import ClinicalConfig, load_config, load_config_file
from pydantic import ValidationError


def test_defaults_match_clinical_spec() -> None:
    """Defaults match 07 §1 when only the required minimum is supplied."""
    cfg = ClinicalConfig()
    assert cfg.isf == 30.0
    assert cfg.target_bg == 135
    assert cfg.iob_tp == 55.0
    assert cfg.iob_td == 240.0
    assert cfg.basal_halflife_h == 25.0
    assert cfg.max_bolus_u == 15.0
    assert cfg.icr is None  # unconfirmed by default (OQ-1)


@pytest.mark.parametrize("bad_isf", [0.0, -1.0, -0.0001])
def test_isf_non_positive_raises(bad_isf: float) -> None:
    """isf <= 0 raises — a zero/negative ISF is an over-dosing hazard."""
    with pytest.raises(ValidationError):
        ClinicalConfig(isf=bad_isf)


def test_isf_small_positive_loads() -> None:
    assert ClinicalConfig(isf=0.1).isf == 0.1


@pytest.mark.parametrize("bad_cap", [25.0001, 26.0, 100.0, 900.0])
def test_max_bolus_u_above_ceiling_raises(bad_cap: float) -> None:
    """max_bolus_u > 25 raises (hard-coded config ceiling)."""
    with pytest.raises(ValidationError):
        ClinicalConfig(max_bolus_u=bad_cap)


def test_max_bolus_u_at_ceiling_loads() -> None:
    assert ClinicalConfig(max_bolus_u=25.0).max_bolus_u == 25.0


@pytest.mark.parametrize("bad_cap", [0.0, -1.0])
def test_max_bolus_u_non_positive_raises(bad_cap: float) -> None:
    with pytest.raises(ValidationError):
        ClinicalConfig(max_bolus_u=bad_cap)


def test_unknown_key_raises() -> None:
    """extra='forbid' — an unknown key is a config error, never silently dropped."""
    with pytest.raises(ValidationError):
        ClinicalConfig(icr=8.3, unknown_knob=1)  # type: ignore[call-arg]


def test_degenerate_iob_curve_raises() -> None:
    """iob_td must exceed iob_tp; otherwise the IOB curve is undefined."""
    with pytest.raises(ValidationError):
        ClinicalConfig(iob_tp=240.0, iob_td=240.0)
    with pytest.raises(ValidationError):
        ClinicalConfig(iob_tp=250.0, iob_td=240.0)


def test_load_config_from_mapping() -> None:
    cfg = load_config({"icr": 8.3, "isf": 45.0})
    assert cfg.icr == 8.3
    assert cfg.isf == 45.0
    assert cfg.prescriptive_enabled is True


def test_load_config_mapping_forbids_unknown_key() -> None:
    with pytest.raises(ValidationError):
        load_config({"isf": 30.0, "nope": True})


def test_load_config_file_roundtrips(tmp_path: object) -> None:
    from pathlib import Path

    p = Path(str(tmp_path)) / "clinical.toml"
    p.write_text('icr = 9.0\nisf = 30.0\ntarget_bg = 135\n', encoding="utf-8")
    cfg = load_config_file(p)
    assert cfg.icr == 9.0
    assert cfg.target_bg == 135


def test_load_config_file_unknown_key_raises(tmp_path: object) -> None:
    from pathlib import Path

    p = Path(str(tmp_path)) / "bad.toml"
    p.write_text('isf = 30.0\nmystery = 1\n', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config_file(p)
