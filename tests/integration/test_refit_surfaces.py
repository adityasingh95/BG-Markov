"""S-1009 — the two surfaces the refit feeds (SDET, written RED first).

`python -m cli refit`, and `api/app.py::load_shadow_evidence`, which has returned a
deliberate `None` since S-1001a because there was nothing real to return.

The adversarial direction here is **the opposite of the usual one**: not a guard that fails
to fire, but a dashboard that fills itself in. An empty shadow page is a true statement
about the evidence. A populated one built from a model that was never scored is not — and it
is the one the operator would open Gate 1 on.

RED: `cli refit` is an unknown subcommand; `load_shadow_evidence` returns `None` always.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.app import app, load_shadow_evidence
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.predictions import backfill_actual_states, record_prediction
from data.tables import (
    ExIntensity,
    LoggedBy,
    MealEvent,
    MealType,
    ModelArtifact,
)
from models.state import bg_to_state

_NOW = dt.datetime(2026, 7, 1, 12, 0)


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'surfaces.db'}")
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


def _scored_meal(session: Session, *, i: int, post_bg: int, version: str) -> None:
    when = _NOW - dt.timedelta(days=2 + i)
    meal = MealEvent(
        datetime=when, logged_at=when, logged_by=LoggedBy.patient, meal_type=MealType.lunch,
        pre_bg=140, pre_bg_time=when, post_bg=post_bg,
        post_bg_time=when + dt.timedelta(minutes=240), elapsed_min=240,
        meal_bolus_units=5.0, bolus_offset_min=-10, carbs_g=45.0, fiber_g=5.0,
        ex_intensity=ExIntensity.none,
    )
    session.add(meal)
    session.flush()
    record_prediction(
        session, model_version=version, gate_state="shadow",
        input_features={"pre_bg": 140.0},
        predicted_distribution={str(s): 0.2 for s in (1, 2, 3, 4, 5)},
        baseline_state=bg_to_state(post_bg), meal_id=meal.meal_id,
    )
    session.flush()


def _promoted(session: Session, *, version: str = "v-2026-07") -> None:
    session.add(
        ModelArtifact(
            version=version, fit_date=_NOW, data_hash="h", n_rows=30,
            feature_list=[], metrics={"hypo_recall": 0.8}, is_promoted=True,
        )
    )
    session.flush()


# --- ★ fails closed -----------------------------------------------------------


def test_no_promoted_model_still_returns_the_empty_state(session: Session) -> None:
    """★ Wiring this function is the moment it becomes tempting to make the page look
    populated. With no promoted model there is nothing to report, and saying so is the
    correct output."""
    report, _baseline, _calibration = load_shadow_evidence(session)
    assert report is None


def test_a_promoted_model_with_no_scored_predictions_still_returns_the_empty_state(
    session: Session,
) -> None:
    """★ A model exists; nothing has been scored against it. A report built from zero
    outcomes would show a hypo recall — of nothing — and the operator opens Gate 1 on
    exactly this screen."""
    _promoted(session)
    report, _baseline, _calibration = load_shadow_evidence(session)
    assert report is None


def test_predictions_whose_outcomes_are_not_backfilled_do_not_count(
    session: Session,
) -> None:
    """The DL-049 failure mode from the dashboard's side: rows exist, outcomes are NULL,
    and there is still nothing to score."""
    _promoted(session)
    for i in range(10):
        _scored_meal(session, i=i, post_bg=150, version="v-2026-07")
    # deliberately NOT backfilled
    report, _baseline, _calibration = load_shadow_evidence(session)
    assert report is None


# --- ★ and reports when there is something to report --------------------------


def test_a_scored_promoted_model_produces_a_real_report(session: Session) -> None:
    _promoted(session)
    for i in range(12):
        _scored_meal(session, i=i, post_bg=(70, 150, 150, 210)[i % 4], version="v-2026-07")
    backfill_actual_states(session)

    report, _baseline, _calibration = load_shadow_evidence(session)
    assert report is not None
    assert report.n_predictions == 12


def test_only_the_promoted_versions_predictions_are_scored(session: Session) -> None:
    """★ A prediction made by last month's model is not evidence about this month's. Mixing
    them would let a retired model's record flatter — or damn — the current one."""
    _promoted(session, version="v-new")
    for i in range(12):
        _scored_meal(session, i=i, post_bg=150, version="v-new")
    for i in range(12, 20):
        _scored_meal(session, i=i, post_bg=70, version="v-old")
    backfill_actual_states(session)

    report, _baseline, _calibration = load_shadow_evidence(session)
    assert report is not None
    assert report.n_predictions == 12, "predictions from another model version were scored"


def test_the_dashboard_renders_the_real_report(client: TestClient, session: Session) -> None:
    _promoted(session)
    for i in range(12):
        _scored_meal(session, i=i, post_bg=(70, 150, 150, 210)[i % 4], version="v-2026-07")
    backfill_actual_states(session)

    r = client.get("/operator/shadow")
    assert r.status_code == 200
    body = r.text.lower()
    assert "no model" not in body and "not yet" not in body, "the empty state is still shown"
    assert "accuracy" not in body, "a plain-accuracy figure appeared on the shadow page"


# --- ★ the CLI ----------------------------------------------------------------


def test_cli_refit_writes_an_unpromoted_artifact(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ The refit is now one command away from an artifact, which is exactly when adding
    `--promote` starts to feel helpful. The S-1001b AST guard forbids `cli/` calling
    `promote_model`; this asserts the behaviour the guard protects."""
    from cli.__main__ import main
    from data.basal import record_basal

    db = tmp_path / "cli.db"
    engine = make_engine(f"sqlite:///{db}")
    create_all(engine)
    with session_factory(engine)() as s:
        start = (_NOW - dt.timedelta(days=200)).date()
        for i in range(200):
            record_basal(
                s, date=start + dt.timedelta(days=i), units=24.0,
                time_taken=dt.time(22, 0), logged_by=LoggedBy.patient, clock=lambda: _NOW,
            )
        for i in range(25):
            _scored_meal(s, i=i, post_bg=(70, 120, 150, 210, 260)[i % 5], version="seed")
        s.commit()

    monkeypatch.setenv("BGAPP_DB_PATH", str(db))
    assert main(["refit"]) == 0

    out = capsys.readouterr().out.lower()
    assert "not promoted" in out, "the output does not say the artifact is unpromoted"

    with session_factory(engine)() as s:
        artifact = s.scalars(select(ModelArtifact)).one()
        assert artifact.is_promoted is False
