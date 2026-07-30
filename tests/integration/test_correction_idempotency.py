"""S-1019 (SDET) — a retried correction records one event and one bolus. RED first.

`POST /api/correction-events` writes to `bolus_log` (REQ-006), so it carries exactly the
harm S-1016 was written to prevent: a duplicated bolus overstates IOB, and the calculator
subtracts IOB.

The other three write endpoints are deliberately **not** given a key, and the reasons are
stated in `test_the_other_write_endpoints_do_not_need_a_key` rather than left implicit —
"we did not get to it" and "it does not need one" look identical in a codebase.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.tables import BolusLog, CorrectionEvent

KEY = "9f1d2e3a-0000-4000-8000-000000000001"


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'corr.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "idempotency_key": KEY,
        "datetime": "2026-07-24T15:00:00",
        "bg_before": 244,
        "units": 2.0,
        "food_in_window": False,
    }
    body.update(overrides)
    return body


def _counts(db: Session) -> tuple[int, int]:
    db.expire_all()
    events = db.scalar(select(func.count()).select_from(CorrectionEvent)) or 0
    boluses = db.scalar(select(func.count()).select_from(BolusLog)) or 0
    return events, boluses


def test_a_repeated_key_creates_one_event_and_one_bolus(
    client: TestClient, db: Session
) -> None:
    """★ Again the assertion is on `bolus_log`, not the event count."""
    first = client.post("/api/correction-events", json=_payload())
    assert first.status_code == 200, first.text
    second = client.post("/api/correction-events", json=_payload())
    assert second.status_code == 200, second.text

    assert second.json()["event_id"] == first.json()["event_id"]
    assert _counts(db) == (1, 1)


def test_a_repeat_returns_the_first_record_unchanged(client: TestClient, db: Session) -> None:
    """A key identifies a submission, not a slot to overwrite (DL-055)."""
    client.post("/api/correction-events", json=_payload())
    client.post("/api/correction-events", json=_payload(bg_before=99, units=9.0))

    db.expire_all()
    event = db.scalars(select(CorrectionEvent)).one()
    assert event.bg_before == 244, "a retry silently edited the stored record"
    assert event.units == 2.0


def test_two_different_keys_create_two_events(client: TestClient, db: Session) -> None:
    """Two genuine corrections an hour apart must both be recorded."""
    client.post("/api/correction-events", json=_payload())
    client.post("/api/correction-events", json=_payload(
        idempotency_key="9f1d2e3a-0000-4000-8000-000000000002",
        datetime="2026-07-24T19:30:00",
    ))
    assert _counts(db) == (2, 2)


def test_the_database_itself_refuses_a_duplicate_key(db: Session) -> None:
    """★ A check-then-insert races. The constraint is what makes it correct rather than
    usually correct — the same argument as S-1016."""
    import datetime as dt

    from sqlalchemy.exc import IntegrityError

    for _ in range(2):
        db.add(CorrectionEvent(
            datetime=dt.datetime(2026, 7, 25, 10, 0),
            logged_at=dt.datetime(2026, 7, 25, 10, 5),
            bg_before=200, units=1.0, food_in_window=False,
            idempotency_key="dup-key",
        ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_historical_rows_without_a_key_coexist(db: Session) -> None:
    """The column is nullable: rows written before this story have no key, and several
    NULLs must not collide under the unique constraint."""
    import datetime as dt

    for hour in (8, 9, 10):
        db.add(CorrectionEvent(
            datetime=dt.datetime(2026, 7, 26, hour, 0),
            logged_at=dt.datetime(2026, 7, 26, hour, 5),
            bg_before=210, units=1.0, food_in_window=False,
        ))
    db.flush()
    assert (db.scalar(select(func.count()).select_from(CorrectionEvent)) or 0) == 3


def test_the_other_write_endpoints_do_not_need_a_key(client: TestClient) -> None:
    """★ Stated, not skipped. Scope that is merely unfinished looks the same as scope that
    was reasoned about, and this is the second time this project has found a
    declared-and-unconnected gap.

    - `PATCH …/post-bg` updates a **named** meal; applying it twice is the same state.
    - `POST /api/basal` treats a repeat date as a **correction**, by design (S-1013).
    - `POST /api/operator/profile` appends versions and is operator-driven; a duplicate
      version is untidy, not dangerous.

    None of the three writes to `bolus_log`, which is what makes a duplicate harmful.
    """
    from api.schemas import BasalCreate, PostBgUpdate, ProfileVersionCreate

    for schema in (PostBgUpdate, BasalCreate, ProfileVersionCreate):
        assert "idempotency_key" not in schema.model_fields, (
            f"{schema.__name__} gained a key without a reason being recorded here"
        )

    resp = client.patch("/api/meals/999999/post-bg", json={
        "post_bg": 120, "post_bg_time": "2026-07-24T17:00:00",
    })
    assert resp.status_code == 404, "an unknown meal is a 404, not a silent create"
