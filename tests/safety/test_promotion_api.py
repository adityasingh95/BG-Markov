"""S-1001b [SAFETY] — the promotion endpoint (SDET, written RED first).

The only door Gate 1 has. `data/promotion.py` has existed since S-1006 and nothing
reachable called it, so the manual-promotion requirement was untested as a *workflow*.

These tests are adversarial in three specific directions, because the three plausible
mistakes here all look like caution:

1. **Gating the endpoint on `is_open`.** `is_promoted` is one of Gate 1's five conditions,
   so `is_open` is false by definition before promotion. An endpoint that checks it refuses
   every promotion forever — including the correct one — and a gate that can never open is
   not obviously a bug.
2. **Trusting the client.** The UI disables the button. That is a courtesy, not a control.
3. **Adding preconditions to revoke "for symmetry"**, which would mean the one moment you
   most need to shut the gate is the moment you cannot.

RED: `POST /api/operator/promote` does not exist.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.repositories import get_promoted_artifact
from data.tables import AuditLog, LoggedBy, MealEvent, MealType, ModelArtifact, PredictionLog

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BASE = dt.datetime(2026, 1, 1, 8, 0)


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'promote_api.db'}")
    create_all(engine)
    maker = session_factory(engine)
    with maker() as session:

        def _session() -> Iterator[Session]:
            yield session

        app.dependency_overrides[get_session] = _session
        yield session
        app.dependency_overrides.clear()


@pytest.fixture()
def client(db: Session) -> TestClient:
    return TestClient(app)


def _artifact(session: Session, version: str = "v1") -> None:
    session.add(ModelArtifact(
        version=version, fit_date=_BASE, data_hash="h", n_rows=200,
        feature_list=["pre_bg"], metrics={}, is_promoted=False,
    ))
    session.flush()


def _valid_meals(session: Session, n: int) -> None:
    for i in range(n):
        when = _BASE + dt.timedelta(days=i // 3, hours=i % 3 * 5)
        session.add(MealEvent(
            datetime=when, logged_at=when + dt.timedelta(minutes=30),
            logged_by=LoggedBy.patient, meal_type=MealType.lunch,
            pre_bg=120, pre_bg_time=when, post_bg=140,
            post_bg_time=when + dt.timedelta(minutes=120), elapsed_min=120,
            meal_bolus_units=4.0, correction_bolus_units=0.0, bolus_offset_min=-10,
            carbs_g=40.0, protein_g=10.0, fat_g=8.0, fiber_g=5.0, net_carbs_g=35.0,
            macro_confidence=95, ex_duration_min=0, pre_ex_duration_min=0,
            hypo_treatment=False, snack_during_window=False, is_valid=True,
        ))
    session.flush()


def _shadow_history(session: Session, days: int) -> None:
    session.add(PredictionLog(
        created_at=dt.datetime.now() - dt.timedelta(days=days),
        model_version="v1", gate_state="shadow", input_features={},
        predicted_distribution={}, baseline_state=3,
    ))
    session.flush()


def _ready(monkeypatch: pytest.MonkeyPatch, *, recall: float = 0.9, calibrated: bool = True,
           baseline: float = 0.5) -> None:
    """Make the four AUTOMATIC conditions evaluable: a scored model on the report card."""
    import api.app as app_module
    from api.presenters import BaselineComparison

    class _Cal:
        is_acceptable = calibrated
        n_judged = 3
        reason = "ok" if calibrated else "it understates the risk"

    def _fake(_session: object) -> object:
        import numpy as np

        from models.shadow import build_shadow_report

        is_hypo = np.array([1] * 20 + [0] * 40)
        # a score that yields the requested recall at the metric's chosen threshold
        score = np.where(is_hypo == 1, 0.9, 0.1)
        n_miss = int(round((1 - recall) * 20))
        score[:n_miss] = 0.05
        states = np.where(is_hypo == 1, 2, 3)
        bg = np.where(is_hypo == 1, 67.0, 130.0)
        report = build_shadow_report(
            hypo_score=score, is_hypo=is_hypo, predicted_bg=bg, reference_bg=bg,
            pred_states=states, actual_states=states, unconstrained_beta_insulin=0.4,
        )
        return (report, BaselineComparison(hypo_recall=baseline), _Cal())

    monkeypatch.setattr(app_module, "load_shadow_evidence", _fake)


def _all_conditions_met(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _artifact(db)
    _valid_meals(db, 200)
    _shadow_history(db, 120)
    _ready(monkeypatch)


# --- ★ the unsatisfiable-precondition trap -----------------------------------


def test_promotion_succeeds_when_the_four_automatic_conditions_hold(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ THE TEST THIS STORY EXISTS FOR.

    `is_promoted` is one of Gate 1's five conditions, so `is_open` is FALSE by definition
    at the moment of promotion. An endpoint that gates on `is_open` refuses every promotion
    forever — and a gate that can never open looks like caution, not like a bug. Nothing
    else in the suite would catch it.
    """
    _all_conditions_met(db, monkeypatch)
    r = client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    assert r.status_code == 200, r.text
    assert get_promoted_artifact(db) is not None


def test_after_promotion_gate1_actually_opens(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: the fifth condition becomes true and the gate reads OPEN."""
    _all_conditions_met(db, monkeypatch)
    client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    assert "gate 1 is <strong>open</strong>" in client.get("/operator/shadow").text.lower()


# --- ★ each automatic condition refuses on its own ---------------------------


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        ("volume", "volume"),
        ("baseline", "beats_baseline"),
        ("shadow", "shadow_period"),
        ("calibration", "calibration"),
    ],
)
def test_each_unmet_condition_refuses_with_409_and_names_itself(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch,
    break_it: str, expected: str,
) -> None:
    """★ Every automatic condition is load-bearing on its own."""
    _artifact(db)
    _valid_meals(db, 10 if break_it == "volume" else 200)
    _shadow_history(db, 5 if break_it == "shadow" else 120)
    _ready(
        monkeypatch,
        recall=0.2 if break_it == "baseline" else 0.9,
        calibrated=break_it != "calibration",
    )
    r = client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    assert r.status_code == 409, r.text
    assert expected in r.text, f"the 409 did not name {expected!r}: {r.text}"
    assert get_promoted_artifact(db) is None


def test_several_unmet_conditions_are_all_named_not_just_the_first(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ A refusal that reveals one blocker at a time teaches the operator to treat the
    gate as an obstacle course. The whole list reads as what it is — a description of what
    is not yet true."""
    _artifact(db)
    _valid_meals(db, 10)
    _shadow_history(db, 3)
    _ready(monkeypatch, recall=0.1, calibrated=False)
    r = client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    assert r.status_code == 409
    for name in ("volume", "beats_baseline", "shadow_period", "calibration"):
        assert name in r.text, f"{name} missing from the refusal: {r.text}"


def test_nothing_is_promoted_before_any_evidence_exists(
    client: TestClient, db: Session
) -> None:
    """Day one: no meals, no predictions, no model scored. 409, never a quiet success."""
    _artifact(db)
    r = client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    assert r.status_code == 409
    assert get_promoted_artifact(db) is None


# --- ★ confirmation is not a formality ---------------------------------------


def test_promotion_without_explicit_confirmation_is_refused(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Reaching the URL is not a decision; saying yes is. The difference matters when the
    action is putting someone who cannot feel a low in front of a model."""
    _all_conditions_met(db, monkeypatch)
    for payload in ({"model_version": "v1"}, {"model_version": "v1", "confirmed": False}):
        r = client.post("/api/operator/promote", json=payload)
        assert r.status_code in (400, 422), r.text
        assert get_promoted_artifact(db) is None


def test_an_unknown_version_creates_nothing_and_promotes_nothing(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _valid_meals(db, 200)
    _shadow_history(db, 120)
    _ready(monkeypatch)
    r = client.post("/api/operator/promote", json={"model_version": "ghost", "confirmed": True})
    assert r.status_code == 404
    assert db.query(ModelArtifact).count() == 0
    assert get_promoted_artifact(db) is None


# --- audit --------------------------------------------------------------------


def test_promotion_is_audited(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If she is ever shown something wrong, *who decided, and when* must be answerable
    from the database rather than from memory."""
    _all_conditions_met(db, monkeypatch)
    client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    rows = db.query(AuditLog).filter_by(table_name="model_artifact").all()
    assert rows, "promotion was not audited"
    assert rows[-1].field == "is_promoted"
    assert rows[-1].old_value == "False" and rows[-1].new_value == "True"


# --- ★ revoke is unconditional ------------------------------------------------


def test_revoke_works_even_when_the_conditions_no_longer_hold(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ A gate you cannot shut is not a gate.

    The failure this system exists to prevent is a model that looks good, gets trusted, and
    is quietly wrong about a low. The response to that suspicion must never be blocked by a
    precondition check — least of all the check that the model still looks fine.
    """
    _all_conditions_met(db, monkeypatch)
    assert client.post(
        "/api/operator/promote", json={"model_version": "v1", "confirmed": True}
    ).status_code == 200

    # the world turns: the model is no longer calibrated and the data thins out
    _ready(monkeypatch, recall=0.05, calibrated=False)
    r = client.post("/api/operator/revoke", json={"model_version": "v1", "confirmed": True})
    assert r.status_code == 200, r.text
    assert get_promoted_artifact(db) is None


def test_revoke_takes_effect_on_the_next_read(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gates are live (ADR-7) — no cached "open" survives the revocation."""
    _all_conditions_met(db, monkeypatch)
    client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    assert "gate 1 is <strong>open</strong>" in client.get("/operator/shadow").text.lower()
    client.post("/api/operator/revoke", json={"model_version": "v1", "confirmed": True})
    assert "gate 1 is <strong>closed</strong>" in client.get("/operator/shadow").text.lower()


def test_revoke_is_audited(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _all_conditions_met(db, monkeypatch)
    client.post("/api/operator/promote", json={"model_version": "v1", "confirmed": True})
    client.post("/api/operator/revoke", json={"model_version": "v1", "confirmed": True})
    last = db.query(AuditLog).filter_by(table_name="model_artifact").all()[-1]
    assert last.old_value == "True" and last.new_value == "False"


# --- ★ no bypass --------------------------------------------------------------


def test_no_env_var_or_query_param_promotes(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ 03 §3 — no bypass exists. Not by fixture, mock, config flag or env var."""
    _artifact(db)
    _valid_meals(db, 10)
    for var in ("PROMOTE", "AUTO_PROMOTE", "SKIP_GATE", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    for url in (
        "/api/operator/promote?force=true",
        "/api/operator/promote?skip_preconditions=1",
        "/api/operator/promote",
    ):
        r = client.post(url, json={"model_version": "v1", "confirmed": True, "force": True})
        assert r.status_code != 200, f"{url} promoted despite unmet conditions"
    assert get_promoted_artifact(db) is None


def test_the_client_cannot_assert_its_own_readiness(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ The UI disables the button. That is a courtesy, not a control. Anything reaching
    this URL — a stale tab, a half-finished script, a future bug — meets the same bar."""
    _artifact(db)
    _valid_meals(db, 10)
    r = client.post("/api/operator/promote", json={
        "model_version": "v1", "confirmed": True,
        "preconditions_met": True, "gate1_open": True, "valid_meals": 999,
    })
    assert r.status_code == 409
    assert get_promoted_artifact(db) is None


def test_no_cli_module_calls_promote_model() -> None:
    """★ THE "refit then promote" CRON JOB.

    `07 §Retraining` — "Promotion is manual, on hypo recall." A scheduled refit that
    promotes its own output is one line to write, would look like automation rather than a
    safety breach, and would put her in front of an unreviewed model every month.
    """
    offenders: list[str] = []
    for pkg in ("cli", "models", "features", "core", "prescribe"):
        pkg_dir = _REPO_ROOT / pkg
        if not pkg_dir.is_dir():
            continue
        for path in pkg_dir.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                    if name == "promote_model":
                        offenders.append(f"{pkg}/{path.name}")
    assert not offenders, (
        f"promote_model is called outside the operator endpoint: {offenders}"
    )
