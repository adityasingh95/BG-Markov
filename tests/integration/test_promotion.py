"""S-1006 [SAFETY] — the audited promotion action (SDET, written RED first).

Promotion is the moment a human decides she may see the model. `is_promoted` answers
*what*; the audit row answers *who, when, and from what* — if she is ever shown something
wrong, that must be answerable from the database rather than from memory.

RED: `data.promotion` does not exist.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from data.db import create_all, make_engine, session_factory
from data.promotion import promote_model, revoke_promotion
from data.repositories import get_promoted_artifact
from data.tables import AuditLog, LoggedBy, ModelArtifact

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PRODUCTION_PKGS = ["core", "features", "models", "prescribe", "api", "cli"]


@pytest.fixture()
def session(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'promo.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


def _add(session: Session, version: str, *, promoted: bool = False) -> ModelArtifact:
    art = ModelArtifact(
        version=version,
        fit_date=dt.datetime(2026, 1, 1, 12, 0),
        data_hash="h",
        n_rows=150,
        feature_list=["pre_bg"],
        metrics={},
        is_promoted=promoted,
    )
    session.add(art)
    session.flush()
    return art


# --- promote -----------------------------------------------------------------


def test_promote_sets_the_flag_and_writes_an_audit_row(session: Session) -> None:
    _add(session, "v1")
    promote_model(session, "v1", confirmed_by=LoggedBy.operator)

    got = get_promoted_artifact(session)
    assert got is not None and got.version == "v1"

    rows = session.query(AuditLog).filter_by(table_name="model_artifact").all()
    assert rows, "promotion was not audited"
    row = rows[-1]
    assert row.field == "is_promoted"
    assert row.old_value == "False" and row.new_value == "True"
    assert row.changed_by == LoggedBy.operator


def test_promoting_a_second_model_demotes_the_first_atomically(session: Session) -> None:
    """★ Two promoted artifacts is an ambiguous state with no correct answer — the served
    model would depend on row order. The demotion happens in the same transaction, so the
    state cannot exist rather than merely being unlikely. Both changes are audited."""
    _add(session, "v1")
    _add(session, "v2")
    promote_model(session, "v1", confirmed_by=LoggedBy.operator)
    promote_model(session, "v2", confirmed_by=LoggedBy.operator)

    promoted = session.query(ModelArtifact).filter_by(is_promoted=True).all()
    assert [a.version for a in promoted] == ["v2"], "more than one artifact is promoted"

    audited = [
        (r.record_id, r.old_value, r.new_value)
        for r in session.query(AuditLog).filter_by(table_name="model_artifact").all()
    ]
    assert any(o == "True" and n == "False" for _, o, n in audited), "demotion not audited"


def test_promoting_an_unknown_version_raises_and_creates_nothing(session: Session) -> None:
    """Fails closed: refuse, never create."""
    with pytest.raises(ValueError):
        promote_model(session, "does-not-exist", confirmed_by=LoggedBy.operator)
    assert session.query(ModelArtifact).count() == 0
    assert get_promoted_artifact(session) is None


# --- revoke ------------------------------------------------------------------


def test_revoke_clears_the_flag_and_audits(session: Session) -> None:
    """A gate you cannot shut is not a gate."""
    _add(session, "v1")
    promote_model(session, "v1", confirmed_by=LoggedBy.operator)
    revoke_promotion(session, "v1", confirmed_by=LoggedBy.operator)

    assert get_promoted_artifact(session) is None
    last = session.query(AuditLog).filter_by(table_name="model_artifact").all()[-1]
    assert last.old_value == "True" and last.new_value == "False"


def test_revoking_takes_effect_on_the_next_call_not_a_cached_answer(session: Session) -> None:
    """Gates are live (ADR-7): the answer flips within one process."""
    _add(session, "v1")
    promote_model(session, "v1", confirmed_by=LoggedBy.operator)
    assert get_promoted_artifact(session) is not None
    revoke_promotion(session, "v1", confirmed_by=LoggedBy.operator)
    assert get_promoted_artifact(session) is None


# --- nothing else may promote ------------------------------------------------


def test_no_production_module_sets_is_promoted_outside_data_promotion() -> None:
    """★ The "auto-promote once metrics pass" temptation.

    A human must put her in front of the model on purpose (`07 §Retraining`). If any other
    module can write this flag, that guarantee is only a convention.
    """
    offenders: list[str] = []
    for pkg in _PRODUCTION_PKGS:
        pkg_dir = _REPO_ROOT / pkg
        if not pkg_dir.is_dir():
            continue
        for path in pkg_dir.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                # `<anything>.is_promoted = ...` — writing the flag on an ORM object.
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Attribute) and tgt.attr == "is_promoted":
                            offenders.append(f"{pkg}/{path.name}: .is_promoted = ...")
                # `ModelArtifact(is_promoted=...)` — minting an already-promoted artifact.
                # Narrow to ModelArtifact deliberately: passing/reporting `is_promoted` is
                # REQUIRED elsewhere (gate1_status takes it; Gate1Status reports it so the
                # dashboard can name the blocking condition). Only writes to the persisted
                # flag are forbidden.
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "ModelArtifact"
                    and any(kw.arg == "is_promoted" for kw in node.keywords)
                ):
                    offenders.append(f"{pkg}/{path.name}: ModelArtifact(is_promoted=...)")
    assert not offenders, f"is_promoted is written outside data/promotion.py: {offenders}"
