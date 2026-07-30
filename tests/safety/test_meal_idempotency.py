"""S-1016 [SAFETY] — a retried meal submission must not double her insulin record.

`05 §`: *"All write endpoints are idempotent — the client generates a UUID per record."*
`MealCreate.idempotency_key` has been **required** since S-301 and read by **nothing**.

A duplicate meal is annoying. A duplicate **bolus** is dangerous: `bolus_log` is REQ-006's
*sole source of truth for IOB*, so one double-tap inflates `iob_at(t)` for ~5 hours, and the
calculator then subtracts that inflated IOB and **under-doses her** — silently, plausibly,
with no screen on which it looks different from a real injection.

Four adversarial directions:

1. **Dedupe the meal, re-insert the boluses.** Passes a meal-count test and preserves the
   entire harm. This is why the headline assertion is on `bolus_log`, and then on IOB, and
   then on the dose.
2. **Check-then-insert with no database constraint.** Correct until it isn't.
3. **Update the existing row** with the retry's data — an unaudited edit to a clinical
   record (`04 §10`).
4. **Return 409**, which tells her a successful log failed and invites a third attempt.

RED: `meal_event.idempotency_key` does not exist; two identical POSTs create two meals and
two boluses.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.profile import append_profile_version
from data.repositories import iob_at_start_at
from data.tables import AuditLog, BolusLog, LoggedBy, MealEvent
from prescribe.bolus import recommend_bolus

_NOW = dt.datetime(2026, 7, 30, 12, 0)
_KEY = "11111111-2222-3333-4444-555555555555"


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        append_profile_version(
            s, effective_from=(_NOW - dt.timedelta(days=300)).date(),
            icr=9.0, isf=30.0, target_bg=135, changed_by=LoggedBy.operator,
        )
        s.commit()
        yield s


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _payload(*, key: str = _KEY, **overrides: Any) -> dict[str, Any]:
    when = _NOW - dt.timedelta(hours=1)
    payload: dict[str, Any] = {
        "idempotency_key": key,
        "datetime": when.isoformat(),
        "meal_type": "lunch",
        "pre_bg": 150,
        "pre_bg_time": (when - dt.timedelta(minutes=5)).isoformat(),
        "meal_bolus_units": 6.0,
        "correction_bolus_units": 1.0,   # two bolus rows per submit — both must dedupe
        "bolus_offset_min": -10,
        "carbs_g": 55.0,
        "protein_g": 20.0,
        "fat_g": 12.0,
        "fiber_g": 5.0,
        "macro_confidence": 90,
        "logged_by": "patient",
    }
    payload.update(overrides)
    return payload


# --- ★ the harm: her insulin record --------------------------------------------


def test_a_retry_creates_NO_SECOND_BOLUS(client: TestClient, session: Session) -> None:
    """★ THE ONE THAT MATTERS.

    A meal-count assertion passes for an implementation that dedupes the meal and re-inserts
    the boluses — which is the entire harm. `bolus_log` is REQ-006's sole source of truth for
    IOB, so this is the row that must not double.
    """
    client.post("/api/meals", json=_payload())
    client.post("/api/meals", json=_payload())      # the double-tap

    assert session.scalar(select(func.count()).select_from(MealEvent)) == 1
    assert session.scalar(select(func.count()).select_from(BolusLog)) == 2, (
        "the retry duplicated her insulin record — one submit writes one meal + one "
        "correction bolus, so two submits must still leave exactly two rows"
    )


def test_IOB_is_unchanged_by_a_retry(client: TestClient, session: Session) -> None:
    """★ Asserted through the quantity the calculator actually consumes, not the row count
    that implies it. Fiasp runs ~5 h, so an inflated IOB is wrong for hours."""
    client.post("/api/meals", json=_payload())
    session.expire_all()
    at = _NOW - dt.timedelta(minutes=30)
    before = iob_at_start_at(session, at)

    client.post("/api/meals", json=_payload())
    session.expire_all()
    assert iob_at_start_at(session, at) == pytest.approx(before)
    assert before > 0.0, "the fixture logged no insulin — this assertion would be vacuous"


def test_the_RECOMMENDED_DOSE_is_unchanged_by_a_retry(
    client: TestClient, session: Session
) -> None:
    """★ The end of the causal chain, asserted directly.

    An inflated IOB is subtracted by `prescribe/bolus.py`, so a doubled bolus makes the
    calculator recommend **less insulin than she needs** — silently, and plausibly.
    """
    client.post("/api/meals", json=_payload())
    session.expire_all()
    at = _NOW - dt.timedelta(minutes=30)

    def _dose() -> float:
        return recommend_bolus(
            icr=9.0, isf=30.0, carbs_g=45.0, current_bg=190.0, target_bg=135.0,
            iob=iob_at_start_at(session, at),
        ).total_units

    before = _dose()
    client.post("/api/meals", json=_payload())
    session.expire_all()
    assert _dose() == pytest.approx(before), "a retry changed the dose she would be offered"


# --- ★ what the retry sees -----------------------------------------------------


def test_a_retry_returns_200_and_the_SAME_meal_id(
    client: TestClient, session: Session
) -> None:
    """★ Not 409. A retry is not an error — she pressed the button twice and there is one
    meal, which is what she meant. Telling her a successful log failed invites a third
    attempt, which is the harm this story exists to prevent."""
    first = client.post("/api/meals", json=_payload())
    second = client.post("/api/meals", json=_payload())

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["meal_id"] == first.json()["meal_id"]


def test_same_key_different_data_leaves_the_FIRST_record_unchanged(
    client: TestClient, session: Session
) -> None:
    """★ A key identifies **a submission**, not a slot to overwrite.

    Silently updating a clinical record because a retry carried different numbers is an
    unaudited edit, which `04 §10` forbids — and a retry is far likelier to be a stale form
    than a considered correction. Corrections have their own audited path.
    """
    client.post("/api/meals", json=_payload(carbs_g=55.0))
    audits_before = session.scalar(select(func.count()).select_from(AuditLog)) or 0

    client.post("/api/meals", json=_payload(carbs_g=999.0, meal_bolus_units=99.0))

    meal = session.scalars(select(MealEvent)).one()
    assert meal.carbs_g == 55.0, "the retry silently overwrote a clinical record"
    assert meal.meal_bolus_units == 6.0
    assert session.scalar(select(func.count()).select_from(AuditLog)) == audits_before


def test_two_DIFFERENT_keys_with_identical_data_create_two_meals(
    client: TestClient, session: Session
) -> None:
    """★ Deduping on CONTENT would silently drop a real second meal. She can eat the same
    dish twice; the key is what distinguishes a retry from a repeat."""
    client.post("/api/meals", json=_payload(key="key-a"))
    client.post("/api/meals", json=_payload(key="key-b"))
    assert session.scalar(select(func.count()).select_from(MealEvent)) == 2
    assert session.scalar(select(func.count()).select_from(BolusLog)) == 4


# --- ★ the constraint is in the database, not in Python ------------------------


def test_the_database_itself_refuses_a_duplicate_key(session: Session) -> None:
    """★ THE ONE THAT CATCHES 'CHECK-THEN-INSERT'.

    A read-then-insert races: two submissions can both find nothing and both insert. On a
    single-user laptop that is unlikely — but "unlikely" is exactly what the double-tap
    already was, and a constraint costs nothing. Asserted by bypassing the route entirely.
    """
    from sqlalchemy.exc import IntegrityError

    def _row(key: str) -> MealEvent:
        when = _NOW - dt.timedelta(hours=2)
        return MealEvent(
            datetime=when, logged_at=when, logged_by=LoggedBy.patient,
            meal_type=__import__("data.tables", fromlist=["MealType"]).MealType.lunch,
            pre_bg=140, pre_bg_time=when, meal_bolus_units=4.0, bolus_offset_min=-10,
            carbs_g=40.0, idempotency_key=key,
        )

    session.add(_row("dupe"))
    session.flush()
    session.add(_row("dupe"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_many_historical_meals_with_NO_key_coexist(session: Session) -> None:
    """★ Every meal recorded before this story has no key. A naive `UNIQUE` that rejects a
    second NULL would break every historical row — and backfilling invented keys would
    fabricate provenance for submissions that never had one."""
    for i in range(5):
        when = _NOW - dt.timedelta(days=10 + i)
        session.add(
            MealEvent(
                datetime=when, logged_at=when, logged_by=LoggedBy.patient,
                meal_type=__import__("data.tables", fromlist=["MealType"]).MealType.dinner,
                pre_bg=130, pre_bg_time=when, meal_bolus_units=4.0, bolus_offset_min=-10,
                carbs_g=40.0,
            )
        )
    session.flush()
    assert session.scalar(select(func.count()).select_from(MealEvent)) == 5


def test_the_key_is_persisted_so_a_retry_can_find_it(
    client: TestClient, session: Session
) -> None:
    client.post("/api/meals", json=_payload())
    meal = session.scalars(select(MealEvent)).one()
    assert meal.idempotency_key == _KEY
