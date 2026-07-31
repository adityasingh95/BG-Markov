"""What kind of data a database holds (S-1024, DL-062).

★ **The marker lives in the database, not in the environment.** `BGAPP_DEMO=1` can be
forgotten, inherited from a parent shell, or left set from the previous run — and the
mistake is silent in *both* directions: a real database rendering "DEMO", or a synthetic one
rendering nothing. Provenance belongs to the data. Move the file, reopen it in a month, hand
it to someone else, and it still says what it is.

This is the same principle as `shadow_days` being a **derived count rather than a stored
boolean** (S-1007) and gates being evaluated live (ADR-7): the answer comes from the thing
itself, so it cannot drift from reality.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.tables import DataProvenance

#: The exact string the banner renders. Tests assert on **this**, so a reworded banner
#: cannot silently stop being detectable — the S-1021 drift lesson.
DEMO_BANNER_MARK = "DEMO DATA — not her records"

_DEMO = "demo"


def mark_demo_database(session: Session, *, note: str | None = None) -> None:
    """Record that this database holds **synthetic** data. Idempotent.

    Re-seeding an existing file must not accumulate rows: the question is *what is this
    database*, not *how many times did somebody say so*.
    """
    existing = session.scalars(
        select(DataProvenance).where(DataProvenance.kind == _DEMO)
    ).first()
    if existing is not None:
        existing.note = note
        return
    session.add(
        DataProvenance(
            kind=_DEMO,
            note=note,
            # A creation timestamp for a *file*, not a clinical event — the one place a
            # wall-clock read is the right answer (ADR-8 governs reported times, not this).
            created_at=dt.datetime.now(),
        )
    )


def is_demo_database(session: Session) -> bool:
    """True only when this database has been **explicitly marked** as synthetic.

    ★ Absence means *not marked* — it does **not** mean demo, and it does not mean patient.
    Defaulting to "demo" would stamp a banner across her real records on the first day of
    capture, which teaches her to ignore banners; defaulting the other way is what this
    function exists to prevent, and is why the seeder is tested to always mark.
    """
    return (
        session.scalars(
            select(DataProvenance).where(DataProvenance.kind == _DEMO).limit(1)
        ).first()
        is not None
    )
