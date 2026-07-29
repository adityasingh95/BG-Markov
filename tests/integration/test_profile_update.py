"""S-1010 — appending a patient-profile version (SDET, written RED first).

Clinical constants have been versioned since S-201 (REQ-054) with **no action that appends
a version**. Until this lands, the only way to set the ICR is editing the database by hand,
which is why the S-1003 calculator renders "setting missing" and nothing in the app can
change it.

Two adversarial directions, both of which feel like the sensible choice:

1. **`UPDATE` instead of `INSERT`.** Smaller, obvious — and it destroys the only record of
   what the calculator was actually using last month. It would pass a "the calculator sees
   the new value" test perfectly, which is why that test is not the one that matters here.
2. **Blocking out-of-range values because it feels safer.** It moves a genuine clinical
   change to a hand-edit of the database, out of the audit log entirely (DL-048).

RED: `data.profile` does not exist; `POST /api/operator/profile` 404s.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.profile import ProfileFlag, append_profile_version
from data.repositories import active_profile
from data.tables import AuditLog, LoggedBy, PatientProfile
from prescribe.bolus import recommend_bolus

_JAN = dt.date(2026, 1, 1)
_MAR = dt.date(2026, 3, 1)


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'profile.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(session: Session, *, icr: float = 9.0, isf: float = 30.0) -> None:
    append_profile_version(
        session, effective_from=_JAN, icr=icr, isf=isf, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()


# --- ★ append, never mutate (REQ-054) ----------------------------------------


def test_appending_leaves_the_previous_version_completely_intact(session: Session) -> None:
    """★ THE ONE THAT CATCHES THE OBVIOUS IMPLEMENTATION.

    An `UPDATE` is smaller, reads fine, and would pass every "the calculator sees the new
    value" test. It also destroys the only record of what the calculator was actually
    using last month — and a dose computed in January was computed with January's numbers.
    """
    _seed(session, icr=9.0, isf=30.0)
    append_profile_version(
        session, effective_from=_MAR, icr=8.0, isf=32.0, target_bg=130,
        changed_by=LoggedBy.operator,
    )
    session.flush()

    rows = list(session.scalars(select(PatientProfile).order_by(PatientProfile.effective_from)))
    assert len(rows) == 2, f"expected two versions, got {len(rows)} — this was an UPDATE"

    old = rows[0]
    assert old.effective_from == _JAN
    assert old.icr == 9.0 and old.isf == 30.0 and old.target_bg == 135, (
        "the previous version was mutated"
    )


def test_the_latest_version_is_the_active_one(session: Session) -> None:
    _seed(session, icr=9.0)
    append_profile_version(
        session, effective_from=_MAR, icr=8.0, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()
    profile = active_profile(session)
    assert profile is not None and profile.icr == 8.0


def test_two_versions_on_the_same_day_resolve_to_the_later_row(session: Session) -> None:
    """Insertion order breaks the tie, not whichever the DB happens to return first."""
    _seed(session, icr=9.0)
    append_profile_version(
        session, effective_from=_JAN, icr=7.5, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()
    profile = active_profile(session)
    assert profile is not None and profile.icr == 7.5


# --- ★ the calculator picks it up live ---------------------------------------


def test_the_calculator_reflects_a_new_version_on_the_next_call(session: Session) -> None:
    """★ Live, not cached (ADR-7 in spirit). The same session, a new version, a different
    dose — because the calculator reads the profile rather than remembering it."""
    _seed(session, icr=9.0)
    before = active_profile(session)
    assert before is not None
    dose_before = recommend_bolus(
        icr=before.icr, isf=before.isf, carbs_g=45.0, current_bg=180.0,
        target_bg=float(before.target_bg), iob=0.0,
    ).total_units

    append_profile_version(
        session, effective_from=_MAR, icr=6.0, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()

    after = active_profile(session)
    assert after is not None
    dose_after = recommend_bolus(
        icr=after.icr, isf=after.isf, carbs_g=45.0, current_bg=180.0,
        target_bg=float(after.target_bg), iob=0.0,
    ).total_units

    assert dose_after > dose_before, (
        "a smaller ICR must give a larger carb dose; the calculator did not see the change"
    )


# --- ★ refuse nonsense (DL-048) ----------------------------------------------


@pytest.mark.parametrize("icr", [0.0, -3.0])
def test_a_non_positive_icr_is_refused_and_nothing_is_written(
    session: Session, icr: float
) -> None:
    """The calculator divides by it — there is no meaningful behaviour to fall back on."""
    with pytest.raises(ValueError):
        append_profile_version(
            session, effective_from=_JAN, icr=icr, isf=30.0, target_bg=135,
            changed_by=LoggedBy.operator,
        )
    assert session.query(PatientProfile).count() == 0


@pytest.mark.parametrize("isf", [0.0, -12.0])
def test_a_non_positive_isf_is_refused(session: Session, isf: float) -> None:
    with pytest.raises(ValueError):
        append_profile_version(
            session, effective_from=_JAN, icr=9.0, isf=isf, target_bg=135,
            changed_by=LoggedBy.operator,
        )
    assert session.query(PatientProfile).count() == 0


@pytest.mark.parametrize("target_bg", [0, -90])
def test_a_non_positive_target_bg_is_refused_by_the_function_not_only_the_schema(
    session: Session, target_bg: int
) -> None:
    """★ ADVERSARIAL (SDET, added after the plants).

    `ProfileVersionCreate` already refuses this with `Field(gt=0)` — so the HTTP door is
    shut and the test below passes. The **function** door is not, and it is the one every
    other caller uses: a CLI, a migration, a fixture, the next screen.

    It matters because ``target_bg`` is the number every correction is measured *from*:
    `prescribe/bolus.py` computes ``(current_bg - target_bg) / isf``. At a target of 0,
    every correction is sized as though her whole blood glucose were excess. INV-3 caps the
    result at 15 U and flags it, so this is bounded rather than unbounded — but a capped
    wrong dose is still a wrong dose, and it arrives with no explanation of why.

    ``icr`` and ``isf`` are refused in both layers. The third clinical number should not be
    the one where the guard depends on which door you came in through.
    """
    with pytest.raises(ValueError):
        append_profile_version(
            session, effective_from=_JAN, icr=9.0, isf=30.0, target_bg=target_bg,
            changed_by=LoggedBy.operator,
        )
    assert session.query(PatientProfile).count() == 0


# --- ★ flag, but do not block (DL-048) ---------------------------------------


def test_an_out_of_range_icr_is_flagged_and_still_written(session: Session) -> None:
    """★ 04 §1 expects ICR 7–10. Twenty is unusual, and it is written anyway.

    Blocking it would send a genuine clinical change to a hand-edit of the database, which
    is audited nowhere and versioned by nobody — the safer-looking option produces the less
    safe outcome.
    """
    result = append_profile_version(
        session, effective_from=_JAN, icr=20.0, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()
    assert session.query(PatientProfile).count() == 1, "an unusual value was blocked"
    assert ProfileFlag.ICR_OUTSIDE_EXPECTED_RANGE in result.flags


def test_a_ten_times_typo_is_flagged_even_where_no_range_is_documented(
    session: Session,
) -> None:
    """★ `04 §1` gives no expected range for ISF, so an absolute band would have to be
    invented. A **factor-of-ten change from her own current value** catches the misplaced
    decimal point without inventing one."""
    _seed(session, icr=9.0, isf=30.0)
    result = append_profile_version(
        session, effective_from=_MAR, icr=9.0, isf=300.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()
    assert ProfileFlag.LARGE_CHANGE in result.flags
    assert session.query(PatientProfile).count() == 2, "the typo was blocked rather than flagged"


def test_a_ten_times_icr_typo_is_flagged_too(session: Session) -> None:
    _seed(session, icr=9.0)
    result = append_profile_version(
        session, effective_from=_MAR, icr=90.0, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    assert ProfileFlag.LARGE_CHANGE in result.flags


def test_an_ordinary_adjustment_is_not_flagged(session: Session) -> None:
    """★ A screen that warns about everything warns about nothing. 9 → 8.5 is a normal
    clinical tweak and must pass silently."""
    _seed(session, icr=9.0, isf=30.0)
    result = append_profile_version(
        session, effective_from=_MAR, icr=8.5, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    assert result.flags == ()


def test_the_first_ever_version_is_not_flagged_as_a_large_change(session: Session) -> None:
    """There is nothing to compare against, so "changed by 10×" is not a claim that can be
    made. It must not fire on the very first entry."""
    result = append_profile_version(
        session, effective_from=_JAN, icr=9.0, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    assert ProfileFlag.LARGE_CHANGE not in result.flags


# --- audit -------------------------------------------------------------------


def test_every_changed_field_is_audited_old_to_new(session: Session) -> None:
    """04 §10 — every edit to a clinical record. These are the numbers the calculator
    divides by, so *who changed them and when* must be answerable from the database."""
    _seed(session, icr=9.0, isf=30.0)
    append_profile_version(
        session, effective_from=_MAR, icr=8.0, isf=32.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()

    audits = {
        a.field: (a.old_value, a.new_value)
        for a in session.scalars(select(AuditLog).where(AuditLog.table_name == "patient_profile"))
    }
    assert audits["icr"] == ("9.0", "8.0")
    assert audits["isf"] == ("30.0", "32.0")
    assert "target_bg" not in audits, "an unchanged field was audited as a change"


# --- the screen ---------------------------------------------------------------


def test_the_endpoint_appends_a_version(client: TestClient, session: Session) -> None:
    _seed(session)
    r = client.post(
        "/api/operator/profile",
        json={"effective_from": "2026-03-01", "icr": 8.0, "isf": 30.0, "target_bg": 135},
    )
    assert r.status_code in (200, 201), r.text
    assert session.query(PatientProfile).count() == 2


def test_the_endpoint_refuses_a_non_positive_icr(client: TestClient, session: Session) -> None:
    r = client.post(
        "/api/operator/profile",
        json={"effective_from": "2026-03-01", "icr": 0, "isf": 30.0, "target_bg": 135},
    )
    assert r.status_code == 422, r.text
    assert session.query(PatientProfile).count() == 0


def test_the_endpoint_returns_the_flags_rather_than_refusing(
    client: TestClient, session: Session
) -> None:
    """★ The flag reaches the caller. A validation result nobody can see is not a warning."""
    _seed(session, icr=9.0)
    r = client.post(
        "/api/operator/profile",
        json={"effective_from": "2026-03-01", "icr": 90.0, "isf": 30.0, "target_bg": 135},
    )
    assert r.status_code in (200, 201), r.text
    assert "large_change" in r.text or "unusual" in r.text.lower()


def test_the_profile_page_shows_the_current_values_and_the_history(
    client: TestClient, session: Session
) -> None:
    _seed(session, icr=9.0)
    append_profile_version(
        session, effective_from=_MAR, icr=8.0, isf=30.0, target_bg=135,
        changed_by=LoggedBy.operator,
    )
    session.flush()

    body = client.get("/operator/profile").text.lower()
    assert "8.0" in body, "the current value is not shown"
    assert "9.0" in body, "the history is not shown — versioning is the point of this screen"
    assert "icr" in body and "isf" in body


def test_the_profile_page_renders_with_no_profile_at_all(client: TestClient) -> None:
    """Day one — and the state the calculator is in right now."""
    r = client.get("/operator/profile")
    assert r.status_code == 200
    assert "not set" in r.text.lower() or "no profile" in r.text.lower()
