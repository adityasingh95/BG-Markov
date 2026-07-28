"""S-1008 — live per-meal prediction wiring (SDET, written RED first).

Every component here is already tested in isolation. These tests are about the **order**
they run in, because that is where INV-9 and INV-2 either hold or quietly stop holding —
a chain of individually-correct parts can still be unsafe.

The three cheap mistakes named in docs/stories/S-1008.md each have a test:
  (a) calling `require_gate1` here "to be safe", which silently stops shadow mode from
      ever accruing the evidence Gate 1 needs to open;
  (b) building a return value on a path that skipped `serve_prediction`, breaking INV-9
      while every unit test still passes;
  (c) falling back to the most RECENT artifact instead of the PROMOTED one.

RED: `prescribe.serving` and `data.repositories.get_promoted_artifact` do not exist.
"""

from __future__ import annotations

import ast
import datetime as dt
import inspect
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from core.safety import SafetyViolation
from data.db import create_all, make_engine, session_factory
from data.repositories import get_promoted_artifact
from data.tables import ModelArtifact, PredictionLog
from prescribe.serving import MealPrediction, serve_meal_prediction

_STATES = (1, 2, 3, 4, 5)
_CONFIDENT = [0.01, 0.04, 0.90, 0.04, 0.01]  # argmax = state 3, well above the 0.40 floor


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'serving.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


class _SpyModel:
    """A stand-in for the fitted ordinal model that RECORDS whether it was consulted.

    Asserting the *absence* of a call is the point: 'no promoted model ⇒ baseline' must be
    true because the model was never run, not merely because the output happened to look
    baseline-shaped.
    """

    states = _STATES

    def __init__(self, proba: list[float] | None = None) -> None:
        self.calls = 0
        self._proba = proba if proba is not None else _CONFIDENT

    def predict_proba(self, x: object) -> list[list[float]]:
        self.calls += 1
        return [self._proba]


def _artifact(version: str, *, promoted: bool) -> ModelArtifact:
    return ModelArtifact(
        version=version,
        fit_date=dt.datetime(2026, 1, 1, 12, 0),
        data_hash="deadbeef",
        n_rows=150,
        feature_list=["pre_bg"],
        metrics={"hypo_recall": 0.7},
        is_promoted=promoted,
    )


def _serve(session: Session, model: _SpyModel | None, **kw: object) -> MealPrediction:
    return serve_meal_prediction(  # type: ignore[call-arg]
        session,
        model=model,
        features=[[0.0]],
        baseline_state=3,
        predicted_bg=130.0,
        in_distribution=kw.pop("in_distribution", True),
        n_nearby_train=kw.pop("n_nearby_train", 50),
        input_features={"pre_bg": 120.0},
        **kw,
    )


# --- get_promoted_artifact ---------------------------------------------------


def test_no_artifacts_means_none(session: Session) -> None:
    assert get_promoted_artifact(session) is None


def test_unpromoted_artifacts_are_ignored(session: Session) -> None:
    """★ (c) Fails CLOSED. An unpromoted artifact must never be served just because it is
    the only one, or the newest."""
    session.add(_artifact("v1", promoted=False))
    session.flush()
    assert get_promoted_artifact(session) is None


def test_the_promoted_artifact_is_returned_even_if_not_the_newest(session: Session) -> None:
    """★ (c) 'Most recent' and 'promoted' are different questions. Promotion wins."""
    session.add(_artifact("v1-old", promoted=True))
    newer = _artifact("v2-new", promoted=False)
    newer.fit_date = dt.datetime(2026, 6, 1, 12, 0)
    session.add(newer)
    session.flush()
    got = get_promoted_artifact(session)
    assert got is not None and got.version == "v1-old"


# --- no promoted model ⇒ baseline only ---------------------------------------


def test_without_a_promoted_model_the_model_is_never_consulted(session: Session) -> None:
    """★ Asserts the absence of a call, not just the shape of the result."""
    spy = _SpyModel()
    out = _serve(session, spy)
    assert out.served is None
    assert out.model_version is None
    assert out.baseline_state == 3
    assert spy.calls == 0, "an unpromoted model was consulted"


def test_without_a_promoted_model_nothing_is_written_to_the_prediction_log(
    session: Session,
) -> None:
    _serve(session, _SpyModel())
    assert session.query(PredictionLog).count() == 0


# --- with a promoted model ---------------------------------------------------


def test_promoted_model_is_used_and_its_version_is_recorded(session: Session) -> None:
    """Proves get_promoted_artifact is wired, not decorative."""
    session.add(_artifact("v3-promoted", promoted=True))
    session.flush()
    spy = _SpyModel()
    out = _serve(session, spy)
    assert spy.calls == 1
    assert out.model_version == "v3-promoted"
    assert out.served is not None
    row = session.get(PredictionLog, out.served.prediction_id)
    assert row is not None and row.model_version == "v3-promoted"


def test_inv9_the_prediction_row_exists_before_the_value_is_usable(session: Session) -> None:
    """★ INV-9 through the wiring: the id handed back resolves to a real persisted row."""
    session.add(_artifact("v3", promoted=True))
    session.flush()
    out = _serve(session, _SpyModel())
    assert out.served is not None
    assert session.get(PredictionLog, out.served.prediction_id) is not None


def test_inv9_persistence_failure_serves_nothing(session: Session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """★ THE STRONGEST TEST HERE. Mock persistence to fail ⇒ nothing is served.

    S-802 proved this for `serve_prediction` in isolation. This re-asserts it *through the
    wiring*, because that is where a well-meaning try/except could downgrade a failed write
    into an unlogged prediction.
    """
    import prescribe.serving as serving

    session.add(_artifact("v3", promoted=True))
    session.flush()

    def _boom(*args: object, **kw: object) -> object:
        raise RuntimeError("prediction_log write failed")

    monkeypatch.setattr(serving, "serve_prediction", _boom)
    with pytest.raises(RuntimeError):
        _serve(session, _SpyModel())


# --- guardrails propagate as values ------------------------------------------


def test_guardrail_refusal_is_persisted_and_returned_not_raised(session: Session) -> None:
    """A refusal is a valid outcome: auditable, renderable, never a blank."""
    session.add(_artifact("v3", promoted=True))
    session.flush()
    out = _serve(session, _SpyModel(), in_distribution=False)
    assert out.served is not None
    assert out.served.guarded.refused is True
    row = session.get(PredictionLog, out.served.prediction_id)
    assert row is not None and row.guardrail_fired is not None


def test_inv6_absurd_bg_still_raises_through_the_chain(session: Session) -> None:
    """INV-6 must not be downgraded to a refusal by the wiring."""
    session.add(_artifact("v3", promoted=True))
    session.flush()
    with pytest.raises(SafetyViolation):
        serve_meal_prediction(  # type: ignore[call-arg]
            session,
            model=_SpyModel(),
            features=[[0.0]],
            baseline_state=3,
            predicted_bg=9_999.0,
            in_distribution=True,
            n_nearby_train=50,
            input_features={"pre_bg": 120.0},
        )


# --- prediction is NOT gated; display is -------------------------------------


def test_serving_predicts_and_logs_even_though_gate1_is_shut(session: Session) -> None:
    """★ (a) Shadow mode. Serving takes no gate argument and still logs, which is the ONLY
    way 90 days of evidence accrues. Gating prediction here would deadlock Gate 1 — and
    would look like caution."""
    session.add(_artifact("v3", promoted=True))
    session.flush()
    out = _serve(session, _SpyModel())
    assert out.served is not None
    assert session.query(PredictionLog).count() == 1

    params = set(inspect.signature(serve_meal_prediction).parameters)
    for gated in ("gate1", "gate1_status", "require_gate1", "gate"):
        assert gated not in params, f"serving takes a gate argument ({gated}) — it must not"


def test_serving_module_never_calls_require_gate1() -> None:
    """★ (a) AST guard: the gate must not drift from the readout into the predictor.

    If it ever does, shadow mode silently stops producing evidence and the failure looks
    like the system being careful.
    """
    src = pathlib.Path(inspect.getfile(serve_meal_prediction)).read_text()
    tree = ast.parse(src)
    called = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "require_gate1" not in called
    assert "build_patient_readout" not in called, (
        "serving must not render the patient readout — display is the readout's job (INV-2)"
    )
