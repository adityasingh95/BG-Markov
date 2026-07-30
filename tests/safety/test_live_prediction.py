"""S-1015 [SAFETY] — serving a prediction when a meal is logged (SDET, written RED first).

`serve_meal_prediction` has existed since S-1008, fully tested, and **no route calls it**.
This story connects it, which makes it the first moment a model output exists in the running
application — and the first moment INV-2 has something real to hold back.

Four adversarial directions:

1. **Returning the prediction in the meal response.** The single most natural thing to
   write, and a direct INV-2 breach.
2. **Wrapping the whole meal handler in `try/except Exception`.** Protects her capture
   surface and silently disarms INV-9 and INV-6 together, in one line.
3. **Assembling the served features separately from `data.training`.** They drift, and the
   drift shows up as a model that scores well and predicts badly.
4. **Serving before committing the meal**, so a model failure loses her meal.

RED: `prescribe.live` does not exist; `POST /api/meals` writes no `prediction_log` row.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from core.safety import SafetyViolation
from data.db import create_all, make_engine, session_factory
from data.model_store import load_fitted_model
from data.profile import append_profile_version
from data.repositories import shadow_days
from data.tables import LoggedBy, MealEvent, ModelArtifact, PredictionLog
from models.refit import run_refit
from prescribe.live import predict_for_meal

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_NOW = dt.datetime(2026, 7, 30, 12, 0)


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'live.db'}")
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


def _seed_and_promote(session: Session) -> ModelArtifact:
    """A trained, stored, PROMOTED model — the state in which a prediction can be served."""
    from tests.integration.test_refit import _basal_series, _spread_meals

    append_profile_version(
        session, effective_from=(_NOW - dt.timedelta(days=300)).date(),
        icr=9.0, isf=30.0, target_bg=135, changed_by=LoggedBy.operator,
    )
    _basal_series(session, start=(_NOW - dt.timedelta(days=250)).date(), days=250, units=24.0)
    _spread_meals(session, n=40, end=_NOW - dt.timedelta(days=2))
    artifact = run_refit(session, as_of=_NOW)
    artifact.is_promoted = True
    session.flush()
    return artifact


def _meal_payload() -> dict[str, Any]:
    when = _NOW - dt.timedelta(hours=1)
    return {
        "datetime": when.isoformat(),
        "meal_type": "lunch",
        "pre_bg": 145,
        "pre_bg_time": (when - dt.timedelta(minutes=5)).isoformat(),
        "meal_bolus_units": 5.0,
        "correction_bolus_units": 0.0,
        "bolus_offset_min": -10,
        "carbs_g": 48.0,
        "protein_g": 20.0,
        "fat_g": 12.0,
        "fiber_g": 6.0,
        "macro_confidence": 90,
        "logged_by": "patient",
        # `MealCreate` requires it (S-301): a retried submit must not double-log a meal.
        "idempotency_key": "s1015-demo-key",
    }


# --- ★ INV-2: written, and shown to nobody -----------------------------------


def test_the_meal_response_carries_no_prediction(
    client: TestClient, session: Session
) -> None:
    """★ INV-2. The single most natural thing to write here is to hand the prediction back
    in the response, and it would be a direct breach: she cannot see model output before
    Gate 1, and the meal response is a patient surface."""
    _seed_and_promote(session)
    r = client.post("/api/meals", json=_meal_payload())
    assert r.status_code == 200, r.text

    body = r.json()
    for banned in ("prediction", "probability", "proba", "predicted_state", "risk",
                   "distribution", "model_version", "hypo"):
        assert banned not in body, f"{banned!r} reached the patient meal response"
    assert set(body) <= {"meal_id", "test_at", "message"}, body


def test_the_meal_response_SCHEMA_has_no_prediction_field() -> None:
    """★ The body check above passes if a prediction field exists but happens to be null.
    This asserts on the schema itself, which is the actual boundary."""
    src = (_REPO_ROOT / "api" / "schemas.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MealCreated":
            fields = [
                n.target.id for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            ]
            assert fields == ["meal_id", "test_at", "message"], fields
            return
    pytest.fail("MealCreated not found")


def test_the_patient_readout_is_still_refused_after_a_prediction_exists(
    client: TestClient, session: Session
) -> None:
    """★ The state this story creates for the first time: a real prediction exists in the
    database, Gate 1 is shut, and she still sees nothing. Before S-1015 this test could not
    even be written — there was never a prediction to withhold."""
    _seed_and_promote(session)
    r = client.post("/api/meals", json=_meal_payload())
    meal_id = r.json()["meal_id"]
    assert session.scalar(select(func.count()).select_from(PredictionLog)) == 1

    page = client.get(f"/meals/{meal_id}/readout")
    assert page.status_code == 200
    body = page.text.lower()
    for banned in ("probability", "% chance", "predicted state", "the model"):
        assert banned not in body, f"{banned!r} is visible to her with Gate 1 shut"


# --- ★ INV-9: written before anything else happens ---------------------------


def test_logging_a_meal_writes_a_prediction_row(client: TestClient, session: Session) -> None:
    """★ INV-9, and the reason this story exists: without this row, prediction_log stays
    empty, shadow evidence never accrues, the 90-day clock never starts, and Gate 1 can
    never open."""
    _seed_and_promote(session)
    r = client.post("/api/meals", json=_meal_payload())
    meal_id = r.json()["meal_id"]

    row = session.scalars(select(PredictionLog)).one()
    assert row.meal_id == meal_id
    assert row.created_at is not None, "no created_at — the shadow clock cannot start"
    assert row.predicted_distribution
    assert row.actual_state is None, "the outcome is not known yet and must not be invented"


def test_the_shadow_clock_starts(client: TestClient, session: Session) -> None:
    _seed_and_promote(session)
    assert shadow_days(session, now=_NOW + dt.timedelta(days=5)) == 0
    client.post("/api/meals", json=_meal_payload())
    session.flush()
    assert shadow_days(session, now=_NOW + dt.timedelta(days=5)) > 0


# --- ★ DL-053: capture survives a broken model; invariants do not go quiet ----


def test_a_broken_model_does_not_stop_her_logging_a_meal(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Meal logging is her PRIMARY CAPTURE SURFACE. If a model error takes this route
    down she cannot log, which is worse for her than having no prediction."""
    import prescribe.live as live

    _seed_and_promote(session)

    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("the model exploded")

    monkeypatch.setattr(live, "predict_for_meal", _boom, raising=True)

    before = session.scalar(select(func.count()).select_from(MealEvent)) or 0
    r = client.post("/api/meals", json=_meal_payload())
    assert r.status_code == 200, r.text
    # The fixture seeds 40 training meals, so count the DELTA — an absolute count would be
    # asserting about the fixture rather than about her meal surviving.
    assert session.scalar(select(func.count()).select_from(MealEvent)) == before + 1, (
        "her meal was lost because the model failed"
    )
    assert session.scalar(select(func.count()).select_from(PredictionLog)) == 0


def test_but_a_SAFETY_VIOLATION_still_propagates(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ THE ONE THAT SEPARATES THE TWO CASES.

    `try/except Exception` around the handler protects her capture surface and disarms INV-9
    and INV-6 together, in one line, invisibly. A breached invariant must stay loud — that is
    the entire point of raising `SafetyViolation` rather than returning a flag.

    ⚠ **Scope, after the DL-053 amendment (operator-approved 2026-07-30):** this covers a
    `SafetyViolation` from *anywhere except the baseline computation* — notably the INV-9
    write path. An out-of-range **baseline** is handled separately below: it is caught,
    recorded, and her meal is kept, because the baseline is an internal diagnostic she never
    sees and losing her meal is the worse outcome.
    """
    import prescribe.live as live

    _seed_and_promote(session)

    def _violate(*_a: object, **_k: object) -> None:
        raise SafetyViolation("INV-9: prediction was not persisted before return")

    monkeypatch.setattr(live, "predict_for_meal", _violate, raising=True)

    with pytest.raises(SafetyViolation):
        client.post("/api/meals", json=_meal_payload())


# --- ★ DL-053 amended: an out-of-range BASELINE must not cost her the meal ----


def _implausible_meal() -> dict[str, Any]:
    """A meal whose `07 §4` baseline lands outside INV-6's [20, 600].

    Not contrived: a large correction on top of a meal bolus, which is a real thing to log.
    """
    payload = dict(_meal_payload())
    payload.update(
        idempotency_key="s1015-implausible",
        pre_bg=110, carbs_g=10.0, meal_bolus_units=2.0, correction_bolus_units=14.0,
    )
    return payload


def test_an_out_of_range_baseline_does_not_cost_her_the_meal(
    client: TestClient, session: Session
) -> None:
    """★ THE OPERATOR'S DECISION, 2026-07-30.

    INV-6 fires on the baseline — an internal diagnostic she never sees — while she is
    logging. Before the amendment this returned HTTP 500 and **the meal was lost**. Her
    primary capture surface must not depend on the arithmetic of a number nobody reads.

    INV-6 is not weakened: it still raises inside `predict_baseline_bg`, and no out-of-range
    value is used or shown anywhere.
    """
    _seed_and_promote(session)
    before = session.scalar(select(func.count()).select_from(MealEvent)) or 0

    r = client.post("/api/meals", json=_implausible_meal())
    assert r.status_code == 200, r.text
    assert session.scalar(select(func.count()).select_from(MealEvent)) == before + 1


def test_the_refusal_is_RECORDED_not_swallowed(client: TestClient, session: Session) -> None:
    """★ Caught is not the same as silent. A refusal is persisted like any other prediction
    (S-801/S-802) — auditable, never a blank — so "the model stopped predicting" cannot look
    identical to "no model is promoted"."""
    _seed_and_promote(session)
    client.post("/api/meals", json=_implausible_meal())

    row = session.scalars(
        select(PredictionLog).where(PredictionLog.guardrail_fired.is_not(None))
    ).one()
    assert row.guardrail_fired == "baseline_out_of_range"
    assert row.predicted_distribution == {}, "a refusal must carry no distribution"


def test_a_refusal_is_NOT_scored_as_a_prediction(session: Session) -> None:
    """★ A refusal carries no distribution, so scoring it reads as **"the model predicted no
    low"** — a different statement from "the model declined", and one the model's own record
    gets blamed for. Refusals are countable; they are not evidence about accuracy."""
    from data.scoring import scored_predictions
    from data.tables import ModelArtifact

    session.add(
        ModelArtifact(
            version="v-score", fit_date=_NOW, data_hash="h", n_rows=10,
            feature_list=[], metrics={},
        )
    )
    for i in range(14):
        when = _NOW - dt.timedelta(days=2 + i)
        meal = MealEvent(
            datetime=when, logged_at=when, logged_by=LoggedBy.patient,
            meal_type=__import__("data.tables", fromlist=["MealType"]).MealType.lunch,
            pre_bg=140, pre_bg_time=when, post_bg=(70, 150)[i % 2],
            post_bg_time=when + dt.timedelta(minutes=120), elapsed_min=120,
            meal_bolus_units=5.0, bolus_offset_min=-10, carbs_g=45.0, fiber_g=5.0,
        )
        session.add(meal)
        session.flush()
        session.add(
            PredictionLog(
                meal_id=meal.meal_id, model_version="v-score", gate_state="shadow",
                input_features={}, baseline_state=3,
                predicted_distribution={} if i < 4 else {"3": 0.9},
                guardrail_fired="refused" if i < 4 else None,
                actual_state=2 if i % 2 == 0 else 3,
            )
        )
    session.flush()

    scored = scored_predictions(session, model_version="v-score")
    assert scored is not None
    assert len(scored) == 10, "refusals were scored as predictions"


def test_the_meal_is_committed_before_the_model_is_consulted(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Serving before committing would lose her meal on any model failure. Asserted by
    failing the model and requiring the meal to be durable anyway."""
    import prescribe.live as live

    _seed_and_promote(session)
    monkeypatch.setattr(
        live, "predict_for_meal",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("late failure")),
        raising=True,
    )
    before = session.scalar(select(func.count()).select_from(MealEvent)) or 0
    client.post("/api/meals", json=_meal_payload())
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(MealEvent)) == before + 1


# --- ★ fails closed -----------------------------------------------------------


def test_no_promoted_model_means_no_prediction_and_no_error(
    client: TestClient, session: Session
) -> None:
    """Today's real state. No model ⇒ no row, no exception, and the meal still logs."""
    append_profile_version(
        session, effective_from=(_NOW - dt.timedelta(days=300)).date(),
        icr=9.0, isf=30.0, target_bg=135, changed_by=LoggedBy.operator,
    )
    r = client.post("/api/meals", json=_meal_payload())
    assert r.status_code == 200
    assert session.scalar(select(func.count()).select_from(PredictionLog)) == 0


def test_an_unpromoted_model_serves_nothing(client: TestClient, session: Session) -> None:
    """★ Promoted ≠ most recent. A refit deliberately writes an UNPROMOTED artifact; it must
    not start predicting merely because it is newest."""
    from tests.integration.test_refit import _basal_series, _spread_meals

    append_profile_version(
        session, effective_from=(_NOW - dt.timedelta(days=300)).date(),
        icr=9.0, isf=30.0, target_bg=135, changed_by=LoggedBy.operator,
    )
    _basal_series(session, start=(_NOW - dt.timedelta(days=250)).date(), days=250, units=24.0)
    _spread_meals(session, n=40, end=_NOW - dt.timedelta(days=2))
    run_refit(session, as_of=_NOW)          # NOT promoted
    session.flush()

    client.post("/api/meals", json=_meal_payload())
    assert session.scalar(select(func.count()).select_from(PredictionLog)) == 0


def test_no_profile_means_no_prediction(client: TestClient, session: Session) -> None:
    """No ICR ⇒ no baseline ⇒ nothing to compare a model against. Fails closed."""
    r = client.post("/api/meals", json=_meal_payload())
    assert r.status_code == 200
    assert session.scalar(select(func.count()).select_from(PredictionLog)) == 0


# --- ★ the served features are the trained features ---------------------------


def test_the_served_features_match_the_trained_features(session: Session) -> None:
    """★ A second, parallel feature path drifts, and the drift shows up as a model that
    scores well and predicts badly — the single most dangerous failure this system has.

    Asserted by comparing the vector `predict_for_meal` builds for a meal against the row
    `assemble_training_data` builds for that same meal.
    """
    from data.training import assemble_training_data

    artifact = _seed_and_promote(session)
    data = assemble_training_data(session, as_of=_NOW)
    meal = session.get(MealEvent, data.meal_ids[-1])
    assert meal is not None

    outcome = predict_for_meal(session, meal, now=_NOW)
    assert outcome is not None and outcome.served is not None

    trained_row = data.x[data.meal_ids.index(meal.meal_id)]
    served = np.array(
        [outcome.input_features[name] for name in data.feature_names], dtype=float
    )
    np.testing.assert_allclose(served, trained_row, rtol=1e-9, atol=1e-9)
    assert artifact.feature_list  # the model was fitted on a subset; both agree on names


def test_the_prediction_records_the_promoted_version(session: Session) -> None:
    """Shadow scoring is scoped to one model version (S-1009). A row that does not say which
    model made it cannot be scored against anything."""
    artifact = _seed_and_promote(session)
    from data.training import assemble_training_data

    data = assemble_training_data(session, as_of=_NOW)
    meal = session.get(MealEvent, data.meal_ids[-1])
    assert meal is not None
    predict_for_meal(session, meal, now=_NOW)
    session.flush()

    row = session.scalars(select(PredictionLog)).one()
    assert row.model_version == artifact.version


def test_the_stored_model_is_the_one_that_predicts(session: Session) -> None:
    """★ Not a freshly-refitted one. Serving must use what was PROMOTED, because that is
    what the operator looked at the evidence for."""
    artifact = _seed_and_promote(session)
    loaded = load_fitted_model(session, artifact)
    assert loaded is not None

    from data.training import assemble_training_data

    data = assemble_training_data(session, as_of=_NOW)
    meal = session.get(MealEvent, data.meal_ids[-1])
    assert meal is not None
    outcome = predict_for_meal(session, meal, now=_NOW)
    assert outcome is not None and outcome.served is not None

    keep = [data.feature_names.index(n) for n in artifact.feature_list]
    expected = loaded.predict_proba(data.x[[data.meal_ids.index(meal.meal_id)]][:, keep])[0]
    # `GuardedPrediction` carries the argmax state, not the raw vector — assert on what the
    # guardrail layer actually publishes rather than reaching past it.
    expected_state = int(np.asarray(loaded.states)[int(np.argmax(expected))])
    assert outcome.served.guarded.model_state == expected_state
