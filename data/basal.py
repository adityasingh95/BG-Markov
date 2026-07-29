"""Recording the daily Tresiba (S-1013, REQ-007).

`basal_log` has existed since S-201 and `features/basal.py` has computed `effective_basal`
from it since S-402 — with **nothing able to write to it** (DL-046). This module is the
missing writer, and until it existed the model could not be fitted on real data at all.

**`time_taken` is REPORTED; `logged_at` is the clock** (ADR-8). She takes Tresiba at
roughly the same time each night and logs it whenever she is next at the laptop. The EWMA's
25-hour half-life is a function of the time axis, so a `time_taken` quietly filled from the
system clock would distort every later `effective_basal` — with no error and no way to tell
afterwards.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from core.clock import Clock, SystemClock
from data.tables import AuditLog, BasalLog, LoggedBy


def record_basal(
    session: Session,
    *,
    date: dt.date,
    units: float,
    time_taken: dt.time,
    logged_by: LoggedBy = LoggedBy.patient,
    clock: Clock | None = None,
) -> BasalLog:
    """Record (or correct) the dose for one date.

    **One row per date.** Re-recording an existing date is a **correction**, not a second
    dose: the row is updated and the change written to ``audit_log`` (old → new), as
    `04 §10` requires of every edit to a clinical record. Two rows for one day would
    double-count in the EWMA, and the resulting `effective_basal` would look like a
    titration that never happened.

    A **first** entry is not audited as a change — auditing it would bury the real
    corrections in noise.
    """
    if units <= 0:
        raise ValueError(f"a basal dose must be positive; got {units!r}")

    now = (clock or SystemClock()).now()
    existing = session.get(BasalLog, date)
    if existing is None:
        row = BasalLog(date=date, units=units, time_taken=time_taken, logged_at=now)
        session.add(row)
        return row

    if existing.units != units:
        session.add(
            AuditLog(
                table_name="basal_log",
                record_id=0,  # basal_log is keyed by date, not an int id
                field="units",
                old_value=str(existing.units),
                new_value=str(units),
                changed_by=logged_by,
            )
        )
    existing.units = units
    existing.time_taken = time_taken
    existing.logged_at = now
    return existing
