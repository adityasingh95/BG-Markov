"""Model promotion — the moment a human decides she may see the model (S-1006, REQ-058).

`07 §Retraining`: **"Promotion is manual, on hypo recall."** Good metrics are a
precondition, never permission. This module is the **only** place
`model_artifact.is_promoted` is written; an AST test asserts no other production module
touches it, so "a human decides" is a guarantee rather than a convention.

Every change is **audited**. `is_promoted` alone answers *what*; the `audit_log` row
answers *who, when, and from what*. If she is ever shown something wrong, that must be
answerable from the database, not from anyone's memory.

Exactly one artifact may be promoted at a time, enforced in the same transaction as the
promotion — two promoted rows would be an ambiguous state in which the served model
depends on row order.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.tables import AuditLog, LoggedBy, ModelArtifact


def _audit(
    session: Session, *, version: str, old: bool, new: bool, changed_by: LoggedBy
) -> None:
    session.add(
        AuditLog(
            table_name="model_artifact",
            record_id=0,  # model_artifact is keyed by version (text), not an int id
            field="is_promoted",
            old_value=str(old),
            new_value=str(new),
            changed_by=changed_by,
        )
    )


def _get(session: Session, version: str) -> ModelArtifact:
    art = session.get(ModelArtifact, version)
    if art is None:
        # Fail closed: refuse, never create. A typo must not mint an artifact.
        raise ValueError(f"no model artifact with version {version!r}")
    return art


def promote_model(
    session: Session, version: str, *, confirmed_by: LoggedBy
) -> ModelArtifact:
    """Promote ``version`` so it may be shown to the patient — an explicit human act.

    Demotes any incumbent **in the same transaction**, so ``get_promoted_artifact`` can
    never face two promoted rows. Both the demotion and the promotion are audited.

    Raises ``ValueError`` for an unknown version.
    """
    art = _get(session, version)

    for incumbent in session.scalars(
        select(ModelArtifact).where(ModelArtifact.is_promoted.is_(True))
    ).all():
        if incumbent.version == version:
            continue
        incumbent.is_promoted = False
        _audit(
            session, version=incumbent.version, old=True, new=False,
            changed_by=confirmed_by,
        )

    was = art.is_promoted
    art.is_promoted = True
    _audit(session, version=version, old=was, new=True, changed_by=confirmed_by)
    session.flush()
    return art


def revoke_promotion(
    session: Session, version: str, *, confirmed_by: LoggedBy
) -> ModelArtifact:
    """Un-promote ``version``. A gate that cannot be shut is not a gate.

    Takes effect on the next call — gates are evaluated live, never cached (ADR-7).
    """
    art = _get(session, version)
    was = art.is_promoted
    art.is_promoted = False
    _audit(session, version=version, old=was, new=False, changed_by=confirmed_by)
    session.flush()
    return art
