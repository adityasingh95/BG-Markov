"""Persisting a fitted model on its artifact (S-1014, REQ-059/REQ-060).

`ModelArtifact` has carried a manifest and no coefficients since S-201, so promoting an
artifact promoted a *record of* a model. This is the DB boundary that makes promotion mean
something — the last link in the DL-046/DL-049 chain of components that were correct and
unconnected.

★ **Parameters as JSON, never a pickle** (DL-052). Unpickling executes code on the machine
holding her clinical record; a pickle couples what a promoted model predicts to whichever
library version is installed, so an upgrade can change a prediction silently months after the
operator promoted it on different behaviour; and a blob cannot answer *"what does this model
actually do?"*. A coefficient vector beside its feature names can. A grep/AST guard keeps it
that way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from data.tables import ModelArtifact
from models.ordinal import OrdinalFit, ordinal_from_params


@dataclass(frozen=True)
class LoadedModel:
    """A model reloaded from an artifact, ready to serve.

    Satisfies the ``predict_proba`` contract `prescribe.serving` expects (S-1008), so a
    promoted artifact can finally be handed to the serving path.
    """

    fit: OrdinalFit
    feature_names: list[str]
    scaler_mean: npt.NDArray[np.float64] | None
    scaler_scale: npt.NDArray[np.float64] | None

    @property
    def states(self) -> tuple[int, ...]:
        return self.fit.states

    def _scaled(self, x: npt.ArrayLike) -> npt.NDArray[np.float64]:
        """Apply the **stored** scaling, so the served representation is the fitted one.

        The scaler travels with the model rather than being re-derived: a scaler re-fitted at
        serving time would be fitted on one meal, and the model would then see features
        centred on that meal rather than on its training window.
        """
        arr = np.asarray(x, dtype=float)
        if self.scaler_mean is None or self.scaler_scale is None:
            return arr
        return np.asarray((arr - self.scaler_mean) / self.scaler_scale, dtype=float)

    def predict_proba(self, x: npt.ArrayLike) -> npt.NDArray[np.float64]:
        """Per-state probabilities from **raw** feature rows, in ``feature_names`` order."""
        return self.fit.predict_proba(self._scaled(x))

    def predict_proba_for(
        self, x: npt.ArrayLike, *, feature_names: list[str]
    ) -> npt.NDArray[np.float64]:
        """As :meth:`predict_proba`, but refusing a caller whose feature order differs.

        ★ The coefficient vector is **positional**. A model stored against one feature list
        and served against another produces confident, well-formed, completely wrong
        probabilities — there is no error, no warning, and nothing downstream that could
        notice. So the caller states the order it is passing, and a mismatch is refused.
        """
        if list(feature_names) != self.feature_names:
            raise ValueError(
                "feature order does not match the stored model; "
                f"stored {self.feature_names}, got {list(feature_names)}"
            )
        return self.predict_proba(x)


def save_fitted_model(
    session: Session,
    artifact: ModelArtifact,
    *,
    fit: OrdinalFit,
    feature_names: list[str],
    scaler: StandardScaler | None = None,
) -> None:
    """Store ``fit`` on ``artifact`` as plain JSON, with the scaler it was fitted under."""
    stored: dict[str, Any] = dict(fit.to_params())
    stored["feature_names"] = list(feature_names)
    if scaler is not None:
        stored["scaler_mean"] = [float(v) for v in scaler.mean_]
        stored["scaler_scale"] = [float(v) for v in scaler.scale_]
    artifact.fitted_model = stored
    session.add(artifact)


def load_fitted_model(session: Session, artifact: ModelArtifact) -> LoadedModel | None:
    """The model stored on ``artifact``, or ``None`` if it carries none.

    ★ ``None``, not an exception. **Every artifact written before S-1014 has no stored
    model**, and those are real historical rows rather than corruption. The caller does what
    it already does when nothing is promoted: serves the clinical baseline. Raising here would
    turn old history into an outage.
    """
    stored = artifact.fitted_model
    if not stored:
        return None
    mean = stored.get("scaler_mean")
    scale = stored.get("scaler_scale")
    return LoadedModel(
        fit=ordinal_from_params(stored),
        feature_names=list(stored.get("feature_names", [])),
        scaler_mean=None if mean is None else np.asarray(mean, dtype=float),
        scaler_scale=None if scale is None else np.asarray(scale, dtype=float),
    )
