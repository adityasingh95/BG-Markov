"""Appending a patient-profile version (S-1010, REQ-061/REQ-054).

Clinical constants have been versioned since S-201 and **nothing appended a version** — the
only way to set the ICR was editing the database by hand.

**Appends, never mutates.** A dose computed in January was computed with January's numbers,
and the record has to still say so. An ``UPDATE`` here would be smaller, would read fine,
and would destroy the only evidence of what the calculator was actually using.

**Refuses nonsense, flags the unusual** (DL-048, operator-approved). Hard limits would push
a genuine out-of-range clinical change into a hand-edit — audited nowhere, versioned by
nobody — so the safer-looking option produces the less safe outcome.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.tables import AuditLog, LoggedBy, PatientProfile

# `04 §1`: "icr | float | g carb per unit. **Expected 7–10.**" Traced to the spec, not
# chosen here. There is deliberately no ISF band: `04 §1` does not give one, and inventing
# a clinical range is not this module's business (DL-048).
ICR_EXPECTED_MIN, ICR_EXPECTED_MAX = 7.0, 10.0

# A typo-detection heuristic on RELATIVE change, not a clinical range: a value that moves
# by this factor from her own current one is almost always a misplaced decimal point
# (9 → 90, 30 → 300). It works for ISF precisely because it needs no absolute band, and it
# only ever flags.
LARGE_CHANGE_FACTOR = 2.0


class ProfileFlag(StrEnum):
    """Things worth saying out loud. **None of them blocks the write.**"""

    ICR_OUTSIDE_EXPECTED_RANGE = "icr_outside_expected_range"
    LARGE_CHANGE = "large_change"


@dataclass(frozen=True)
class ProfileUpdate:
    version: PatientProfile
    flags: tuple[ProfileFlag, ...]


def _is_large_change(old: float | None, new: float) -> bool:
    if old is None or old <= 0:
        return False  # nothing to compare against; "changed by 10x" is not a claim yet
    ratio = new / old
    return ratio >= LARGE_CHANGE_FACTOR or ratio <= 1.0 / LARGE_CHANGE_FACTOR


def append_profile_version(
    session: Session,
    *,
    effective_from: dt.date,
    icr: float,
    isf: float,
    target_bg: int,
    changed_by: LoggedBy = LoggedBy.operator,
) -> ProfileUpdate:
    """Append a new profile version and report anything worth a second look.

    **Refuses** ``icr <= 0`` / ``isf <= 0`` / ``target_bg <= 0``: the calculator divides by
    the first two and measures every correction *from* the third, so there is no meaningful
    behaviour to fall back on and this is an input error at the door rather than a
    ``ValueError`` three layers down.

    All three are refused **here**, not only in `ProfileVersionCreate`. The schema shuts the
    HTTP door; this shuts the one every other caller uses — a CLI, a migration, a fixture,
    the next screen. A guard that depends on which door you came in through is not a guard.

    **Flags but never blocks** an ICR outside `04 §1`'s expected 7–10, and any value that
    moves by a factor of ``LARGE_CHANGE_FACTOR`` from the current one.

    Only **changed** fields are audited — auditing unchanged ones would bury the real
    changes.
    """
    if icr <= 0:
        raise ValueError(f"icr must be a positive number of grams per unit; got {icr!r}")
    if isf <= 0:
        raise ValueError(f"isf must be a positive number of mg/dL per unit; got {isf!r}")
    if target_bg <= 0:
        raise ValueError(f"target_bg must be a positive mg/dL reading; got {target_bg!r}")

    current = session.scalars(
        select(PatientProfile).order_by(
            PatientProfile.effective_from.desc(), PatientProfile.profile_id.desc()
        )
    ).first()

    flags: list[ProfileFlag] = []
    if not ICR_EXPECTED_MIN <= icr <= ICR_EXPECTED_MAX:
        flags.append(ProfileFlag.ICR_OUTSIDE_EXPECTED_RANGE)
    if current is not None and (
        _is_large_change(current.icr, icr) or _is_large_change(current.isf, isf)
    ):
        flags.append(ProfileFlag.LARGE_CHANGE)

    version = PatientProfile(
        effective_from=effective_from, icr=icr, isf=isf, target_bg=target_bg
    )
    session.add(version)

    if current is not None:
        for field, old, new in (
            ("icr", current.icr, icr),
            ("isf", current.isf, isf),
            ("target_bg", current.target_bg, target_bg),
        ):
            if old != new:
                session.add(
                    AuditLog(
                        table_name="patient_profile",
                        record_id=current.profile_id,
                        field=field,
                        old_value=str(old),
                        new_value=str(new),
                        changed_by=changed_by,
                    )
                )

    return ProfileUpdate(version=version, flags=tuple(flags))


def profile_history(session: Session) -> list[PatientProfile]:
    """Every version, newest first. Versioning is the point of this screen, so the history
    is shown rather than kept."""
    return list(
        session.scalars(
            select(PatientProfile).order_by(
                PatientProfile.effective_from.desc(), PatientProfile.profile_id.desc()
            )
        )
    )
