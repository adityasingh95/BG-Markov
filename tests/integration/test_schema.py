"""S-201 — schema + migrations (SDET, written RED first).

Structural guarantees that make silent data corruption impossible rather than
merely discouraged: signed offsets stay signed, net carbs cannot go negative,
reported time and log time are separate columns, and clinical constants are
versioned rather than overwritten. See docs/stories/S-201.md.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory
from data.tables import (
    Base,
    BolusLog,
    BolusType,
    LoggedBy,
    MealEvent,
    MealType,
    PatientProfile,
    ProfileImmutableError,
)

_EXPECTED_TABLES = {
    "patient_profile",
    "bolus_log",
    "basal_log",
    "meal_event",
    "correction_event",
    "dish",
    "prediction_log",
    "model_artifact",
    "audit_log",
}

# Clinical (reported) timestamp columns that must NEVER carry a now() default.
_CLINICAL_TS = [
    (MealEvent, "datetime"),
    (MealEvent, "pre_bg_time"),
    (MealEvent, "post_bg_time"),
    (BolusLog, "datetime"),
]


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    create_all(engine)
    return session_factory(engine)()


def _meal(**overrides: object) -> MealEvent:
    """A minimal valid meal; overridable per test."""
    fields: dict[str, object] = {
        "datetime": datetime(2026, 7, 1, 8, 0),
        "logged_at": datetime(2026, 7, 1, 9, 40),
        "logged_by": LoggedBy.patient,
        "meal_type": MealType.breakfast,
        "pre_bg": 142,
        "pre_bg_time": datetime(2026, 7, 1, 7, 55),
        "meal_bolus_units": 6.0,
        "bolus_offset_min": -15,
        "carbs_g": 45.0,
    }
    fields.update(overrides)
    return MealEvent(**fields)


def test_all_tables_present_in_metadata_and_db(session: Session) -> None:
    assert set(Base.metadata.tables) >= _EXPECTED_TABLES, "missing ORM tables"
    tables = set(inspect(session.get_bind()).get_table_names())
    assert tables >= _EXPECTED_TABLES, f"missing DB tables: {_EXPECTED_TABLES - tables}"


def test_bolus_offset_min_accepts_negative(session: Session) -> None:
    """SIGNED: -15 (a pre-bolus) must round-trip as -15, not be clamped/abs'd."""
    session.add(_meal(bolus_offset_min=-15))
    session.commit()
    stored = session.query(MealEvent).one()
    assert stored.bolus_offset_min == -15


def test_net_carbs_is_computed_and_floored_at_zero(session: Session) -> None:
    """carbs=30, fiber=40 => net_carbs=0 (not -10). And 50/10 => 40."""
    session.add(_meal(carbs_g=30.0, fiber_g=40.0))
    session.add(_meal(carbs_g=50.0, fiber_g=10.0))
    session.commit()
    rows = session.query(MealEvent).order_by(MealEvent.carbs_g).all()
    assert rows[0].net_carbs_g == 0.0, "net carbs must floor at 0, never negative"
    assert rows[1].net_carbs_g == 40.0


def test_logged_at_is_distinct_from_reported_datetime(session: Session) -> None:
    """05b/ADR-8: reported mealtime and system log time are separate columns."""
    session.add(_meal(datetime=datetime(2026, 7, 1, 8, 0),
                      logged_at=datetime(2026, 7, 1, 9, 40)))
    session.commit()
    m = session.query(MealEvent).one()
    assert m.datetime == datetime(2026, 7, 1, 8, 0)
    assert m.logged_at == datetime(2026, 7, 1, 9, 40)
    assert m.datetime != m.logged_at, "reported time must not equal log time here"


def test_no_clinical_timestamp_has_a_now_default(session: Session) -> None:
    """ADR-8 at the schema level: a clinical timestamp must never be auto-filled
    with the system clock."""
    for model, col_name in _CLINICAL_TS:
        col = model.__table__.c[col_name]
        assert col.default is None, f"{model.__name__}.{col_name} has a Python default"
        assert col.server_default is None, f"{model.__name__}.{col_name} has a server default"


def _profile(**overrides: object) -> PatientProfile:
    fields: dict[str, object] = {
        "effective_from": date(2026, 1, 1),
        "icr": 8.3,
        "isf": 30.0,
        "target_bg": 135,
    }
    fields.update(overrides)
    return PatientProfile(**fields)


def test_patient_profile_change_creates_a_new_row(session: Session) -> None:
    """REQ-054: a profile change is a new version, not an overwrite."""
    session.add(_profile(effective_from=date(2026, 1, 1), icr=8.3))
    session.commit()
    session.add(_profile(effective_from=date(2026, 4, 1), icr=9.0))
    session.commit()
    rows = session.query(PatientProfile).order_by(PatientProfile.effective_from).all()
    assert len(rows) == 2
    assert rows[0].profile_id != rows[1].profile_id
    assert (rows[0].icr, rows[1].icr) == (8.3, 9.0)


def test_patient_profile_is_immutable_in_place(session: Session) -> None:
    """REQ-054: updating a persisted profile row raises; versioning is the only
    way to change a clinical constant."""
    session.add(_profile(icr=8.3))
    session.commit()
    row = session.query(PatientProfile).one()
    row.icr = 9.0
    with pytest.raises(ProfileImmutableError):
        session.commit()


def test_bolus_log_roundtrips(session: Session) -> None:
    """REQ-006: every bolus is written to bolus_log."""
    session.add(
        BolusLog(
            datetime=datetime(2026, 7, 1, 7, 45),
            logged_at=datetime(2026, 7, 1, 9, 40),
            units=6.0,
            bolus_type=BolusType.meal,
            logged_by=LoggedBy.patient,
        )
    )
    session.commit()
    b = session.query(BolusLog).one()
    assert b.units == 6.0
    assert b.bolus_type == BolusType.meal


def test_alembic_migration_creates_full_schema(tmp_path: Path) -> None:
    """The Alembic initial migration builds the whole schema on an empty DB."""
    from alembic.config import Config

    from alembic import command

    repo_root = Path(__file__).resolve().parents[2]
    db_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    engine = make_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    assert tables >= _EXPECTED_TABLES, f"migration missing: {_EXPECTED_TABLES - tables}"
