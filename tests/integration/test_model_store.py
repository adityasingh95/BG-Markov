"""S-1014 — persisting the fitted model (SDET, written RED first).

`ModelArtifact` has stored a manifest and no coefficients since S-201, so promoting an
artifact promotes a *record of* a model. This is the last link in the DL-046/DL-049 chain:
components correct and unconnected.

Three adversarial directions:

1. **Pickle.** One line, round-trips everything, and puts an execution vector in the
   database that holds her clinical record — plus couples what a promoted model predicts to
   whatever library version happens to be installed.
2. **Storing the parameters but not the scaler.** A round-trip test on already-scaled inputs
   passes perfectly, and every real prediction is wrong.
3. **Comparing parameters instead of probabilities** in the round-trip test — the version
   that looks rigorous and proves nothing.

RED: `data.model_store` does not exist; `model_artifact.fitted_model` does not exist;
`OrdinalFit.to_params` does not exist.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
from collections.abc import Iterator

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory
from data.model_store import load_fitted_model, save_fitted_model
from data.tables import ModelArtifact
from models.ordinal import fit_ordinal

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_NOW = dt.datetime(2026, 7, 30, 12, 0)


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'store.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


def _training_matrix() -> tuple[np.ndarray, np.ndarray]:
    """A small, deterministic ordinal problem with a deliberately LARGE-SCALE column.

    The second feature is on a ~100x scale on purpose: with everything near unit scale a
    forgotten scaler is invisible, and the whole point of these tests is that it is not.
    """
    rng = np.random.default_rng(11)
    n = 90
    x0 = rng.normal(0.0, 1.0, n)
    x1 = rng.normal(300.0, 80.0, n)          # ← large scale, like carbs or BG
    latent = 1.2 * x0 + 0.01 * (x1 - 300.0) + rng.normal(0.0, 0.5, n)
    y = np.digitize(latent, [-1.2, -0.4, 0.4, 1.2]) + 1
    return np.column_stack([x0, x1]), y.astype(int)


def _artifact(session: Session, *, version: str = "v1") -> ModelArtifact:
    artifact = ModelArtifact(
        version=version, fit_date=_NOW, data_hash="h", n_rows=90,
        feature_list=["x0", "x1"], metrics={},
    )
    session.add(artifact)
    session.flush()
    return artifact


# --- ★ round-trip fidelity ----------------------------------------------------


def test_a_reloaded_model_gives_the_SAME_PROBABILITIES(session: Session) -> None:
    """★ THE ONE THAT MATTERS. Asserted on **probabilities**, not on parameters.

    Comparing stored parameter vectors would pass while a threshold-ordering or scaling
    mistake changed every prediction — the parameters are not the thing that gets served.
    A model reloaded incorrectly produces different probabilities from the one that was
    scored, and nothing downstream would notice.
    """
    x, y = _training_matrix()
    fit = fit_ordinal(x, y, confidence_weights=np.ones(len(y)))
    expected = fit.predict_proba(x)

    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"])
    session.flush()

    loaded = load_fitted_model(session, artifact)
    assert loaded is not None
    np.testing.assert_allclose(loaded.predict_proba(x), expected, atol=1e-9)


def test_the_probabilities_still_sum_to_one_after_a_round_trip(session: Session) -> None:
    x, y = _training_matrix()
    fit = fit_ordinal(x, y, confidence_weights=np.ones(len(y)))
    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"])
    session.flush()

    loaded = load_fitted_model(session, artifact)
    assert loaded is not None
    np.testing.assert_allclose(loaded.predict_proba(x).sum(axis=1), 1.0, atol=1e-9)


def test_the_reloaded_model_keeps_the_state_labels(session: Session) -> None:
    """A probability column is meaningless without knowing which state it is. Losing the
    labels would silently re-map every prediction — including which column is a low."""
    x, y = _training_matrix()
    fit = fit_ordinal(x, y, confidence_weights=np.ones(len(y)))
    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"])
    session.flush()

    loaded = load_fitted_model(session, artifact)
    assert loaded is not None
    assert loaded.states == fit.states


# --- ★ the scaler travels with the model --------------------------------------


def test_a_scaler_is_stored_and_applied_on_reload(session: Session) -> None:
    """★ THE ONE THAT CATCHES 'PARAMETERS BUT NOT THE SCALER'.

    Fit on SCALED features, then predict through the loaded model on RAW rows. If the scaler
    is not stored, or is stored and ignored, or applied twice, this is where it shows — and
    only here. A round trip that feeds already-scaled inputs back in passes either way.
    """
    from features.pipeline import make_scaler

    x, y = _training_matrix()
    scaler = make_scaler().fit(x)
    x_scaled = np.asarray(scaler.transform(x), dtype=float)
    fit = fit_ordinal(x_scaled, y, confidence_weights=np.ones(len(y)))
    expected = fit.predict_proba(x_scaled)

    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"], scaler=scaler)
    session.flush()

    loaded = load_fitted_model(session, artifact)
    assert loaded is not None
    # RAW rows in — the loaded model must scale them itself.
    np.testing.assert_allclose(loaded.predict_proba(x), expected, atol=1e-9)


def test_an_unscaled_model_round_trips_too(session: Session) -> None:
    """No scaler stored ⇒ raw features in, unchanged. The identity case must not be special-
    cased into applying a scaler that does not exist."""
    x, y = _training_matrix()
    fit = fit_ordinal(x, y, confidence_weights=np.ones(len(y)))
    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"])
    session.flush()

    loaded = load_fitted_model(session, artifact)
    assert loaded is not None
    np.testing.assert_allclose(loaded.predict_proba(x), fit.predict_proba(x), atol=1e-9)


# --- ★ old artifacts are real history -----------------------------------------


def test_an_artifact_from_before_this_story_loads_as_none(session: Session) -> None:
    """★ Every artifact written before S-1014 has no stored model. That is a real historical
    row, not a corruption: the caller serves the clinical baseline, exactly as it already
    does when nothing is promoted. Raising here would turn old history into an outage."""
    artifact = _artifact(session, version="pre-s1014")
    session.flush()
    assert load_fitted_model(session, artifact) is None


def test_a_stored_model_naming_different_features_is_refused(session: Session) -> None:
    """★ The feature ORDER is load-bearing — the coefficient vector is positional. A model
    stored against one feature list and served against another produces confident,
    well-formed, completely wrong probabilities."""
    x, y = _training_matrix()
    fit = fit_ordinal(x, y, confidence_weights=np.ones(len(y)))
    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"])
    session.flush()

    loaded = load_fitted_model(session, artifact)
    assert loaded is not None
    with pytest.raises(ValueError):
        loaded.predict_proba_for(x, feature_names=["x1", "x0"])


# --- ★ no pickle, ever (DL-052) -----------------------------------------------


def test_no_serialisation_module_is_imported_in_models_or_data() -> None:
    """★ Unpickling EXECUTES CODE, on the machine holding her clinical record — and it ties
    what a promoted model predicts to whichever library version happens to be installed, so
    an upgrade can change a prediction silently, months after the operator promoted it on
    different behaviour.

    Settled by DL-052. This guard is what keeps it settled when someone reaches for the
    one-line version.
    """
    banned = {"pickle", "cPickle", "dill", "joblib", "marshal", "shelve"}
    offenders: list[str] = []
    for pkg in ("models", "data", "prescribe", "api"):
        for path in (_REPO_ROOT / pkg).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    offenders += [
                        f"{path.name}: import {a.name}"
                        for a in node.names
                        if a.name.split(".")[0] in banned
                    ]
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.split(".")[0] in banned
                ):
                    offenders.append(f"{path.name}: from {node.module}")
    assert not offenders, f"serialisation-by-code-execution reached production: {offenders}"


def test_what_is_stored_is_readable_json_a_human_can_check(session: Session) -> None:
    """The operator, or a maintainer a year from now, has to be able to answer "what does
    this model actually do?" A coefficient vector beside its feature names answers it; a
    binary blob does not."""
    x, y = _training_matrix()
    fit = fit_ordinal(x, y, confidence_weights=np.ones(len(y)))
    artifact = _artifact(session)
    save_fitted_model(session, artifact, fit=fit, feature_names=["x0", "x1"])
    session.flush()

    stored = session.scalars(
        select(ModelArtifact).where(ModelArtifact.version == "v1")
    ).one().fitted_model
    assert isinstance(stored, dict)
    assert stored["feature_names"] == ["x0", "x1"]
    assert isinstance(stored["params"], list)
    assert all(isinstance(v, float) for v in stored["params"])


# --- ★ the refit stores one, on the same representation it scored -------------


def test_a_refit_stores_a_model_whose_features_match_the_manifest(
    tmp_path: pathlib.Path,
) -> None:
    """★ And it must be the FITTED subset, not all 23 — the coefficient vector is positional,
    so a manifest that over-claims is a mis-indexed prediction waiting to happen."""
    from tests.integration.test_refit import _basal_series, _spread_meals  # noqa: PLC0415

    engine = make_engine(f"sqlite:///{tmp_path / 'refit.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        _basal_series(s, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
        _spread_meals(s, n=30, end=_NOW - dt.timedelta(days=1))

        from models.refit import run_refit

        artifact = run_refit(s, as_of=_NOW)
        s.flush()

        assert artifact.fitted_model is not None, "the refit stored no model"
        assert artifact.fitted_model["feature_names"] == artifact.feature_list

        loaded = load_fitted_model(s, artifact)
        assert loaded is not None
        assert loaded.states


def test_the_refit_scores_and_stores_the_SAME_representation(
    tmp_path: pathlib.Path,
) -> None:
    """★ THE ONE THAT CATCHES THE SCALING MISMATCH.

    `temporal_cv` scales each fold (train-rows-only, per S-404 — that is correct and stays).
    The final full-window fit was on RAW features, so the coefficients came from one
    representation and the `hypo_recall` beside them on the same row was measured on another.
    The manifest reads as one coherent object and was not one.

    Harmless only while nothing loaded the model. The moment it is served, the number the
    operator reads on the shadow dashboard is about a model that was never served.
    """
    from tests.integration.test_refit import _basal_series, _spread_meals  # noqa: PLC0415

    engine = make_engine(f"sqlite:///{tmp_path / 'scale.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        _basal_series(s, start=(_NOW - dt.timedelta(days=200)).date(), days=200, units=24.0)
        _spread_meals(s, n=30, end=_NOW - dt.timedelta(days=1))

        from models.refit import run_refit

        artifact = run_refit(s, as_of=_NOW)
        s.flush()

        stored = artifact.fitted_model
        assert stored is not None
        assert stored.get("scaler_scale"), "no scaler was stored — the final fit was raw"
        scale = np.asarray(stored["scaler_scale"], dtype=float)
        assert not np.allclose(scale, 1.0), (
            "the stored scaler is the identity; features on wildly different scales "
            "(pre_bg ~140, ex_light 0/1) cannot both have scale 1"
        )
