"""``python -m cli refit`` — the monthly refit (S-1009, REQ-060).

★ **This command cannot promote, and that is enforced elsewhere on purpose.** An AST guard
from S-1001b asserts nothing under `cli/` calls `promote_model`; the artifact is right here
and one line would "finish the job", which is exactly why the guard exists. Promotion is a
deliberate, audited operator act on the shadow dashboard, taken after looking at the
evidence — not a flag on the command that produced the model.

The output says *not promoted* in words, because a command that prints a version and stops
reads like a deployment.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.clock import Clock, SystemClock
from data.db import make_engine, session_factory
from models.refit import run_refit


@dataclass(frozen=True)
class RefitOutcome:
    version: str
    n_rows: int
    hypo_recall: float | None
    dropped_features: list[str]


def refit(db_url: str, *, clock: Clock | None = None) -> RefitOutcome:
    """Run a refit against ``db_url`` and commit the new **unpromoted** artifact.

    The clock is injected and read **once**, so the trailing window and the recency weights
    come from a single instant rather than drifting across a long fit. This is the sanctioned
    wall-clock read (ADR-8) — it stamps the refit, never a clinical timestamp.
    """
    as_of = (clock or SystemClock()).now()
    engine = make_engine(db_url)
    with session_factory(engine)() as session:
        artifact = run_refit(session, as_of=as_of)
        outcome = RefitOutcome(
            version=artifact.version,
            n_rows=artifact.n_rows,
            hypo_recall=artifact.metrics.get("hypo_recall"),
            dropped_features=list(artifact.metrics.get("dropped_constant_features", [])),
        )
        session.commit()
    return outcome
