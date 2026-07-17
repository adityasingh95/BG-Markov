"""The kill switch — trip on drift, never silently re-arm (S-803, REQ-047).

When the model drifts below the baseline it was supposed to beat, it must stop speaking
and stay stopped. The dangerous failure is the quiet un-trip: a degraded model that got
switched off, produced one lucky good prediction, and turned itself back on. Here, the
evaluation path can only ever **trip**; the sole clear is a manual operator action behind
an explicit confirmation. A machine cannot re-arm it.

State lives on ``model_artifact.kill_switch_tripped`` (persisted, so a restart cannot come
up armed after a trip).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from data.tables import ModelArtifact


class ManualReArmRequired(Exception):
    """Raised on any attempt to re-arm the kill switch without explicit operator
    confirmation (REQ-047: re-arming is manual only)."""


def should_trip(*, rolling_recall: float, baseline_recall: float) -> bool:
    """Drift ⇒ the model has fallen **below** the clinical baseline on hypo recall. It
    must keep beating the baseline to keep speaking; a tie is not (yet) drift."""
    return rolling_recall < baseline_recall


def _artifact(session: Session, model_version: str) -> ModelArtifact:
    artifact = session.get(ModelArtifact, model_version)
    if artifact is None:
        raise ValueError(f"unknown model version: {model_version!r}")
    return artifact


def is_tripped(session: Session, model_version: str) -> bool:
    """Read the persisted kill-switch state live from ``model_artifact``."""
    return bool(_artifact(session, model_version).kill_switch_tripped)


def evaluate_kill_switch(
    session: Session,
    model_version: str,
    *,
    rolling_recall: float,
    baseline_recall: float,
) -> bool:
    """Evaluate drift and **trip** if the model has fallen below the baseline. This path
    only ever *sets* the flag — it never clears it — so a good evaluation on an
    already-tripped model leaves it tripped. Returns the current tripped state."""
    if should_trip(rolling_recall=rolling_recall, baseline_recall=baseline_recall):
        _artifact(session, model_version).kill_switch_tripped = True
        session.flush()
    return is_tripped(session, model_version)


def rearm(session: Session, model_version: str, *, operator_confirmed: bool) -> None:
    """Clear the kill switch — the **only** path that does, and manual-only (REQ-047).

    Raises ``ManualReArmRequired`` unless ``operator_confirmed is True``; the
    prediction/serving pipeline never calls this.
    """
    if operator_confirmed is not True:
        raise ManualReArmRequired(
            "kill switch re-arm is a manual operator action; operator_confirmed must be True"
        )
    _artifact(session, model_version).kill_switch_tripped = False
    session.flush()
