"""Clinical configuration — the frozen, validated source of the 07 §1 constants.

This is the process configuration read at startup. It is **not** the versioned
`patient_profile` DB table (S-201). It is immutable after load so no clinical
constant can be mutated mid-run, and it rejects malformed input at load time.

Safety note (INV-1 precondition — see docs/stories/S-103.md):
``prescriptive_enabled`` is a *computed, read-only* property equal to
``icr is not None``. It is a necessary precondition, **never** authorisation:
INV-1 / Gate 2 are enforced in ``core/safety.py`` from live data on every call
(ADR-7). No config value opens a gate. This module re-implements no invariant.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

# Hard config ceiling on the per-dose cap. Distinct from INV-3's MAX_BOLUS_U
# (15 U) recommendation cap in core/safety.py; this only rejects out-of-range
# config values (typos / misconfiguration). See docs/stories/S-103.md.
MAX_BOLUS_U_CEILING: float = 25.0


class ClinicalConfig(BaseModel):
    """Frozen clinical constants (07 §1). Mutation and unknown keys both raise."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ICR is unconfirmed by default (OQ-1). Null is permitted and forces the
    # prescriptive precondition off.
    icr: float | None = None
    # ISF sits in the denominator of the correction term; <= 0 is an over-dosing
    # hazard, so it is rejected outright (07 §1 warning box).
    isf: float = 30.0
    target_bg: int = 135
    # Operational per-dose cap. Bounded to (0, 25]; see MAX_BOLUS_U_CEILING.
    max_bolus_u: float = 15.0
    # Fiasp IOB curve constants (07 §2). td must exceed tp.
    iob_tp: float = 55.0
    iob_td: float = 240.0
    # Tresiba effective-basal EWMA halflife (07 §3).
    basal_halflife_h: float = 25.0

    @model_validator(mode="after")
    def _check_ranges(self) -> ClinicalConfig:
        if self.icr is not None and self.icr <= 0:
            raise ValueError("icr must be > 0 when set")
        if self.isf <= 0:
            raise ValueError("isf must be > 0 (an isf <= 0 is an over-dosing hazard)")
        if not (0 < self.max_bolus_u <= MAX_BOLUS_U_CEILING):
            raise ValueError(
                f"max_bolus_u must be in (0, {MAX_BOLUS_U_CEILING}]; "
                f"got {self.max_bolus_u}"
            )
        if self.iob_tp <= 0:
            raise ValueError("iob_tp must be > 0")
        if self.iob_td <= self.iob_tp:
            raise ValueError("iob_td must exceed iob_tp (else the IOB curve is undefined)")
        if self.basal_halflife_h <= 0:
            raise ValueError("basal_halflife_h must be > 0")
        if self.target_bg <= 0:
            raise ValueError("target_bg must be > 0")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def prescriptive_enabled(self) -> bool:
        """Precondition flag: ICR is present. NOT a gate — INV-1 is evaluated live."""
        return self.icr is not None


def load_config(data: Mapping[str, Any]) -> ClinicalConfig:
    """Validate a mapping into a frozen ClinicalConfig. Unknown keys raise."""
    return ClinicalConfig(**data)


def load_config_file(path: str | Path) -> ClinicalConfig:
    """Load and validate a TOML config file. Unknown keys raise."""
    with Path(path).open("rb") as fh:
        data = tomllib.load(fh)
    return load_config(data)
