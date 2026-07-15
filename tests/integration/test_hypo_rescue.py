"""S-305 [SAFETY] — Hypo rescue capture + the independent INV-7 ledger.

The capture flag/grams already exist (S-303). What this story adds is an
*independent* append-only ledger (`hypo_rescue_log`) so INV-7 can catch the one
loss the flag-only wiring could not (audit H4 / DL-019): a rescued **meal row
that disappears from the database entirely**.

Written RED first: `HypoRescueLog`, `record_hypo_rescue`, and
`get_recorded_rescue_meal_ids` do not exist yet, and the migration does not create
the table, so these fail before the implementation lands.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect
from sqlalchemy.orm import Session, sessionmaker

from api.app import app
from api.deps import get_session
from core.safety import SafetyViolation
from data.db import create_all, make_engine, session_factory
from data.recording import record_hypo_rescue
from data.repositories import (
    get_recorded_rescue_meal_ids,
    get_training_set,
)
from data.tables import Base, HypoRescueLog, LoggedBy, MealEvent, MealType


# --- helpers ---------------------------------------------------------------


class _FixedClock:
    """A deterministic clock so logged_at is not the real wall time in tests."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _meal(day: int, *, rescued: bool = False, post_bg: int | None = 140,
          elapsed: int | None = 120) -> MealEvent:
    """One meal per day (no inter-meal contamination). Rescued meals look normal
    post-rescue (post_bg 95) but are excluded from training + retained as lows."""
    when = datetime(2026, 1, 1, 8, 0) + timedelta(days=day)
    return MealEvent(
        datetime=when,
        logged_at=when,
        logged_by=LoggedBy.patient,
        meal_type=MealType.breakfast,
        pre_bg=120,
        pre_bg_time=when,
        meal_bolus_units=5.0,
        bolus_offset_min=-10,
        carbs_g=40.0,
        post_bg=(95 if rescued else post_bg),
        post_bg_time=when + timedelta(minutes=120),
        elapsed_min=elapsed,
        hypo_treatment=rescued,
        macro_confidence=95,
    )


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'rescue.db'}")
    create_all(engine)
    sess = session_factory(engine)()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = make_engine(f"sqlite:///{tmp_path / 'rescue_api.db'}")
    create_all(engine)
    factory = session_factory(engine)

    def _override() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app), factory
    finally:
        app.dependency_overrides.clear()


# --- schema / migration ----------------------------------------------------


def test_hypo_rescue_log_in_metadata_and_db(session: Session) -> None:
    assert "hypo_rescue_log" in Base.metadata.tables
    tables = set(inspect(session.get_bind()).get_table_names())
    assert "hypo_rescue_log" in tables


def test_alembic_migration_creates_hypo_rescue_log(tmp_path: Path) -> None:
    """The ledger must be created by a real migration, not only by create_all —
    the production DB is migrated, and a low must survive a fresh deploy."""
    from alembic.config import Config

    from alembic import command

    repo_root = Path(__file__).resolve().parents[2]
    db_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    tables = set(inspect(make_engine(db_url)).get_table_names())
    assert "hypo_rescue_log" in tables


def test_ledger_meal_id_has_no_cascading_fk(session: Session) -> None:
    """Independence is the whole point: the ledger must NOT be wiped when the meal
    row is. `meal_id` is a plain reference, so there is no FK that could cascade a
    delete from meal_event into hypo_rescue_log."""
    col = HypoRescueLog.__table__.c["meal_id"]
    assert not col.foreign_keys, "ledger meal_id must not be a cascading FK to meal_event"


# --- write path ------------------------------------------------------------


def test_record_hypo_rescue_writes_independent_row(session: Session) -> None:
    meal = _meal(0, rescued=True)
    session.add(meal)
    session.commit()

    clock = FrozenClock(datetime(2026, 1, 2, 9, 40))
    row = record_hypo_rescue(meal_id=meal.meal_id, grams=15.0, clock=clock)
    session.add(row)
    session.commit()

    stored = session.query(HypoRescueLog).one()
    assert stored.meal_id == meal.meal_id
    assert stored.grams == 15.0
    assert stored.logged_at == datetime(2026, 1, 2, 9, 40)  # system clock, injected


def test_post_bg_with_rescue_appends_one_ledger_row(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    resp = api.post("/api/meals", json={
        "idempotency_key": "55555555-5555-5555-5555-555555555555",
        "datetime": "2026-07-13T08:00:00", "meal_type": "breakfast",
        "pre_bg": 142, "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 45.0, "meal_bolus_units": 6.0, "bolus_offset_min": -15,
        "logged_by": "patient",
    })
    meal_id = int(resp.json()["meal_id"])

    resp = api.patch(f"/api/meals/{meal_id}/post-bg", json={
        "post_bg": 96, "post_bg_time": "2026-07-13T10:05:00",
        "hypo_treatment": True, "hypo_treatment_g": 12.0,
    })
    assert resp.status_code == 200, resp.text

    with factory() as s:
        rows = s.query(HypoRescueLog).all()
        assert len(rows) == 1
        assert rows[0].meal_id == meal_id
        assert rows[0].grams == 12.0


def test_post_bg_without_rescue_writes_no_ledger_row(
    client: tuple[TestClient, sessionmaker[Session]]
) -> None:
    api, factory = client
    resp = api.post("/api/meals", json={
        "idempotency_key": "66666666-6666-6666-6666-666666666666",
        "datetime": "2026-07-13T08:00:00", "meal_type": "breakfast",
        "pre_bg": 142, "pre_bg_time": "2026-07-13T07:55:00",
        "carbs_g": 45.0, "meal_bolus_units": 6.0, "bolus_offset_min": -15,
        "logged_by": "patient",
    })
    meal_id = int(resp.json()["meal_id"])
    api.patch(f"/api/meals/{meal_id}/post-bg", json={
        "post_bg": 168, "post_bg_time": "2026-07-13T10:05:00",
    })
    with factory() as s:
        assert s.query(HypoRescueLog).count() == 0


# --- the reconciliation accessor -------------------------------------------


def test_recorded_rescue_ids_union_flag_and_ledger(session: Session) -> None:
    """The rescued set INV-7 checks is the union of currently-flagged meals AND
    the independent ledger — so neither a cleared flag nor a deleted row can drop
    a meal_id out of it."""
    flagged = _meal(0, rescued=True)     # flagged, no ledger row
    ledgered = _meal(1, rescued=False)   # not flagged, only in the ledger
    session.add_all([flagged, ledgered])
    session.commit()
    session.add(record_hypo_rescue(meal_id=ledgered.meal_id, grams=10.0,
                                   clock=FrozenClock(datetime(2026, 1, 2, 9, 0))))
    session.commit()

    ids = set(get_recorded_rescue_meal_ids(session))
    assert ids == {flagged.meal_id, ledgered.meal_id}


# --- ★ INV-7 safety guards (load-bearing — do not delete) ------------------


def test_inv7_fires_when_a_recorded_rescue_meal_row_is_deleted(session: Session) -> None:
    """★ The H4 case the flag-only wiring could not catch (DL-019).

    A rescued meal + its ledger row. Hard-delete the meal ROW. The flag-derived
    hypo events lose it, but the ledger does not — so INV-7's `rescued − hypo`
    branch must fire. Do not delete this test: it is the loud alarm for a low that
    vanished from the database.
    """
    keep = _meal(0)                       # ordinary valid meal
    rescued = _meal(1, rescued=True)      # the rescue, will be deleted
    session.add_all([keep, rescued])
    session.commit()
    session.add(record_hypo_rescue(meal_id=rescued.meal_id, grams=15.0,
                                   clock=FrozenClock(datetime(2026, 1, 3, 9, 0))))
    session.commit()

    # A future refactor / manual edit hard-deletes the rescued meal row.
    session.execute(delete(MealEvent).where(MealEvent.meal_id == rescued.meal_id))
    session.commit()

    with pytest.raises(SafetyViolation):
        get_training_set(session)


def test_inv7_fires_when_hypo_flag_cleared_but_ledger_retains(session: Session) -> None:
    """The tamper/mis-edit case: `hypo_treatment` is cleared so the meal would
    re-enter training, but the ledger still lists it. INV-7's leak branch fires."""
    rescued = _meal(0, rescued=True)
    session.add(rescued)
    session.commit()
    session.add(record_hypo_rescue(meal_id=rescued.meal_id, grams=15.0,
                                   clock=FrozenClock(datetime(2026, 1, 3, 9, 0))))
    session.commit()

    # Clear the flag: the row now looks like a valid training meal.
    rescued.hypo_treatment = False
    rescued.post_bg = 140
    session.commit()

    with pytest.raises(SafetyViolation):
        get_training_set(session)


def test_happy_path_rescue_does_not_raise(session: Session) -> None:
    """Flagged + ledgered + present ⇒ all three lists agree ⇒ no false alarm."""
    keep = _meal(0)
    rescued = _meal(1, rescued=True)
    session.add_all([keep, rescued])
    session.commit()
    session.add(record_hypo_rescue(meal_id=rescued.meal_id, grams=15.0,
                                   clock=FrozenClock(datetime(2026, 1, 3, 9, 0))))
    session.commit()

    training = get_training_set(session)  # must not raise
    assert {m.meal_id for m in training} == {keep.meal_id}
