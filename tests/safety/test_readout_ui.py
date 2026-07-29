"""S-1002 [SAFETY] — the patient readout page (SDET, written RED first).

**The first patient-reachable model surface.** She may be reading it while low, on a phone,
in bad light. INV-2 governs it: no patient-visible model output before Gate 1.

These tests are adversarial in two directions:

1. **Catching `GateNotPassed` in the route and rendering "the best we have".** That looks
   helpful and turns an invariant into a formatting concern.
2. **Reintroducing a dose in prose** — "about 4 units would cover this" — on a screen whose
   dataclass was carefully built (S-804) to make a dose impossible to pass.

RED: `GET /meals/{id}/readout` does not exist.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.tables import LoggedBy, MealEvent, MealType

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "api/templates/readout.html"
_BASE = dt.datetime(2026, 1, 1, 8, 0)


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'readout_ui.db'}")
    create_all(engine)
    maker = session_factory(engine)
    with maker() as session:

        def _session() -> Iterator[Session]:
            yield session

        app.dependency_overrides[get_session] = _session
        yield session
        app.dependency_overrides.clear()


@pytest.fixture()
def meal_id(db: Session) -> int:
    meal = MealEvent(
        datetime=_BASE, logged_at=_BASE + dt.timedelta(minutes=30),
        logged_by=LoggedBy.patient, meal_type=MealType.lunch,
        pre_bg=120, pre_bg_time=_BASE, meal_bolus_units=4.0,
        correction_bolus_units=0.0, bolus_offset_min=-10,
        carbs_g=40.0, protein_g=10.0, fat_g=8.0, fiber_g=5.0,
        macro_confidence=95, ex_duration_min=0, pre_ex_duration_min=0,
        hypo_treatment=False, snack_during_window=False, is_valid=False,
    )
    db.add(meal)
    db.flush()
    return int(meal.meal_id)


@pytest.fixture()
def client(db: Session) -> TestClient:
    return TestClient(app)


def _body(client: TestClient, meal_id: int, url: str | None = None,
          headers: dict[str, str] | None = None) -> str:
    """The rendered page, lowercased — **after asserting it actually rendered**.

    Every "X must not appear" assertion below goes through here. Without the status check
    they pass trivially against a 404 page, which means they cannot be seen to fail and
    prove nothing about the real screen. A test that is green before the code exists is
    not a test.
    """
    r = client.get(url or f"/meals/{meal_id}/readout", headers=headers or {})
    assert r.status_code == 200, f"the readout did not render: {r.status_code}"
    return r.text.lower()


# --- ★ before Gate 1 -----------------------------------------------------------


def test_gate1_closed_renders_a_plain_nothing_yet_state(
    client: TestClient, meal_id: int
) -> None:
    """★ Today, and for months. 200 with an honest explanation — never a 500, never a
    blank page, and never a prediction."""
    r = client.get(f"/meals/{meal_id}/readout")
    assert r.status_code == 200, r.text
    body = r.text.lower()
    assert "not yet" in body or "nothing to tell you yet" in body or "still learning" in body


def test_the_closed_page_makes_no_risk_claim_and_shows_no_number(
    client: TestClient, meal_id: int
) -> None:
    """★ 03 §3 — "Logging only. No model. No output." No predicted state, no risk level,
    and no baseline projection (DL-045): a number she has every reason to trust, about
    which no evidence has been gathered for her yet, is exactly the failure mode."""
    body = _body(client, meal_id)
    for claim in ("higher chance of a low", "lower chance", "in range", "elevated", "mg/dl"):
        assert claim not in body, f"the pre-Gate-1 page made a claim: {claim!r}"


def test_the_closed_path_does_not_even_load_a_readout(
    client: TestClient, meal_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ The closed branch must not reach the readout path at all.

    `raising=True` on purpose: patching a name the route never calls would make this pass
    for free. This binds to the seam the open path actually uses, so if the closed branch
    ever starts going through it, the page 500s instead of quietly rendering something.
    """
    import api.app as app_module

    def _explode(*_a: object, **_kw: object) -> None:
        raise AssertionError("the readout path was entered with Gate 1 closed")

    monkeypatch.setattr(app_module, "load_patient_readout", _explode)
    assert client.get(f"/meals/{meal_id}/readout").status_code == 200


def test_the_route_never_catches_a_safety_exception() -> None:
    """★ THE ADVERSARIAL ONE, tested where it can actually be seen.

    The route must **branch**, not catch. Catching `GateNotPassed` would put the rendering
    decision downstream of a safety exception, and the natural next refactor catches it
    somewhere broader and renders "the best we have". A monkeypatch cannot prove this — a
    route that never enters the path passes either way — so it is asserted on the source.
    """
    import ast

    source = (_REPO_ROOT / "api/app.py").read_text()
    caught: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            names = ast.walk(node.type)
            for sub in names:
                if isinstance(sub, ast.Name) and sub.id in (
                    "GateNotPassed", "SafetyViolation", "BaseException", "Exception"
                ):
                    caught.append(sub.id)
    assert not caught, (
        f"api/app.py catches {caught} — a safety exception must never become a "
        "formatting decision"
    )


def test_no_query_param_or_header_opens_the_readout(
    client: TestClient, meal_id: int
) -> None:
    """★ No bypass exists (03 §3) — not by fixture, mock, config flag or env var."""
    for url in (
        f"/meals/{meal_id}/readout?force=1",
        f"/meals/{meal_id}/readout?gate1=open",
        f"/meals/{meal_id}/readout?show_prediction=true",
    ):
        body = _body(client, meal_id, url=url)
        assert "higher chance of a low" not in body, f"{url} produced model output"
    body = _body(client, meal_id, headers={"X-Force-Readout": "1", "X-Gate1": "open"})
    assert "higher chance of a low" not in body


def test_no_env_var_opens_the_readout(
    client: TestClient, meal_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("BGMARKOV_FORCE_READOUT", "SKIP_GATE", "GATE1_PASSED", "DEBUG"):
        monkeypatch.setenv(var, "1")
    body = _body(client, meal_id)
    assert "higher chance of a low" not in body


def test_an_unknown_meal_is_a_404_not_a_readout(client: TestClient, meal_id: int) -> None:
    # the known meal renders, so the 404 below is about the unknown id and not about the
    # route being absent entirely
    assert client.get(f"/meals/{meal_id}/readout").status_code == 200
    assert client.get("/meals/99999/readout").status_code == 404


# --- ★ no dose, ever ----------------------------------------------------------


def test_no_dose_like_token_appears_in_the_template_source() -> None:
    """★ S-804 made a dose impossible to *pass* — `PatientReadout` has no such field.
    Nothing stops a template writing "about 4 units would cover this" into a sentence, so
    the check has to be where the text is."""
    source = _TEMPLATE.read_text().lower()
    for banned in ("dose", "bolus", "units", "inject", "how much insulin"):
        assert banned not in source, f"{banned!r} appears on the patient readout template"


def test_no_dose_like_token_appears_in_the_rendered_page(
    client: TestClient, meal_id: int
) -> None:
    body = _body(client, meal_id)
    for banned in ("dose", "bolus", "units", "inject"):
        assert banned not in body, f"{banned!r} rendered on the patient readout"


# --- ★ never scold ------------------------------------------------------------


def test_the_page_never_scolds(client: TestClient, meal_id: int) -> None:
    """★ 05b §8 — "Never scold. Not for a late reading, not for a missed meal, not for a
    high." If it feels like a machine grading her, she stops using it, and then it has done
    nothing but make her feel watched."""
    body = _body(client, meal_id)
    for scold in ("you should have", "you failed", "you forgot", "too late", "missed",
                  "you didn't", "you did not", "overdue"):
        assert scold not in body, f"the readout scolds: {scold!r}"


def test_the_page_never_suggests_testing_less(client: TestClient, meal_id: int) -> None:
    """★ INV-5 — the system never recommends reducing fingerstick frequency."""
    body = _body(client, meal_id)
    for phrase in ("test less", "fewer tests", "no need to test", "skip the test",
                   "you can stop testing"):
        assert phrase not in body, f"the readout suggested testing less: {phrase!r}"


# --- after Gate 1 (rendering, exercised through the readout builder) ----------


def _open_gate(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, **kw: object
) -> None:
    """Open Gate 1 **for real**, then point the readout seam at a built `PatientReadout`.

    Deliberately NOT a patched gate. The five conditions are satisfied with real rows —
    200 valid meals, 120 days of shadow history, a scored model, and a promotion that goes
    through `POST /api/operator/promote` — so these rendering tests also prove the readout
    appears **only after a genuine promotion**. Patching `_live_gate1` would have tested
    the template against a gate that never opened.

    `load_patient_readout` is the data seam (S-1008 wiring lands later); patching it
    exercises RENDERING. `build_patient_readout` still runs `require_gate1` as its first
    line (S-804), and the closed-path tests above prove it is never reached.
    """
    import numpy as np

    import api.app as app_module
    from api.presenters import BaselineComparison
    from models.guardrails import guard_prediction
    from models.shadow import build_shadow_report
    from prescribe.readout import build_patient_readout

    class _Cal:
        is_acceptable = True
        n_judged = 3
        reason = "its percentages match what happened"

    def _evidence(_session: object) -> object:
        is_hypo = np.array([1] * 20 + [0] * 40)
        score = np.where(is_hypo == 1, 0.9, 0.1)
        states = np.where(is_hypo == 1, 2, 3)
        bg = np.where(is_hypo == 1, 67.0, 130.0)
        report = build_shadow_report(
            hypo_score=score, is_hypo=is_hypo, predicted_bg=bg, reference_bg=bg,
            pred_states=states, actual_states=states, unconstrained_beta_insulin=0.4,
        )
        return (report, BaselineComparison(hypo_recall=0.5), _Cal())

    monkeypatch.setattr(app_module, "load_shadow_evidence", _evidence)
    _seed_gate1_evidence(db)
    promoted = client.post(
        "/api/operator/promote", json={"model_version": "v1", "confirmed": True}
    )
    assert promoted.status_code == 200, f"the gate did not open for real: {promoted.text}"

    gate = _live_gate1_for_test(db)
    state = int(kw.get("state", 2))
    peak = float(kw.get("peak", 0.8))
    probs = np.full(5, (1.0 - peak) / 4.0)
    probs[state - 1] = peak
    guarded = guard_prediction(
        proba=probs, states=(1, 2, 3, 4, 5), predicted_bg=float(kw.get("predicted_bg", 67.0)),
        baseline_state=int(kw.get("baseline_state", state)),
        in_distribution=bool(kw.get("in_distribution", True)),
        n_nearby_train=int(kw.get("n_nearby_train", 50)),
    )
    readout = build_patient_readout(
        gate1=gate, guarded=guarded,
        kill_switch_tripped=bool(kw.get("kill_switch", False)),
        baseline_state=int(kw.get("baseline_state", state)),
    )
    monkeypatch.setattr(app_module, "load_patient_readout", lambda *_a, **_k: readout)


def _seed_gate1_evidence(session: Session) -> None:
    """200 valid meals, 120 days of shadow history, and one unpromoted artifact."""
    from data.tables import ModelArtifact, PredictionLog

    session.add(ModelArtifact(
        version="v1", fit_date=_BASE, data_hash="h", n_rows=200,
        feature_list=["pre_bg"], metrics={}, is_promoted=False,
    ))
    session.add(PredictionLog(
        created_at=dt.datetime.now() - dt.timedelta(days=120),
        model_version="v1", gate_state="shadow", input_features={},
        predicted_distribution={}, baseline_state=3,
    ))
    for i in range(200):
        when = _BASE + dt.timedelta(days=i // 3, hours=i % 3 * 5)
        session.add(MealEvent(
            datetime=when, logged_at=when + dt.timedelta(minutes=30),
            logged_by=LoggedBy.patient, meal_type=MealType.lunch,
            pre_bg=120, pre_bg_time=when, post_bg=140,
            post_bg_time=when + dt.timedelta(minutes=120), elapsed_min=120,
            meal_bolus_units=4.0, correction_bolus_units=0.0, bolus_offset_min=-10,
            carbs_g=40.0, protein_g=10.0, fat_g=8.0, fiber_g=5.0,
            macro_confidence=95, ex_duration_min=0, pre_ex_duration_min=0,
            hypo_treatment=False, snack_during_window=False, is_valid=True,
        ))
    session.flush()


def _live_gate1_for_test(session: Session):  # type: ignore[no-untyped-def]
    import api.app as app_module

    return app_module._live_gate1(session)


def test_hypo_risk_is_the_headline_in_text(
    client: TestClient, db: Session, meal_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ 05b §5.1 — hypo risk leads, and it is WORDS. She may be reading this while low."""
    _open_gate(client, db, monkeypatch, state=2)
    body = _body(client, meal_id)
    assert "low" in body
    assert "elevated" in body, "the text risk label must be rendered, not just a colour"


def test_a_refusal_renders_as_words_not_a_blank(
    client: TestClient, db: Session, meal_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ 05b §5.3 — "Never fill the silence with a number." But do not leave a silence
    either: a refusal is a rendered answer."""
    _open_gate(client, db, monkeypatch, state=3, in_distribution=False)
    body = _body(client, meal_id)
    assert "not confident" in body or "unlike" in body
    assert "test as usual" in body


def test_a_conflict_shows_both_and_picks_no_winner(
    client: TestClient, db: Session, meal_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ 05b §5.4 — "The system does not pick a winner.\""""
    _open_gate(client, db, monkeypatch, state=5, baseline_state=3)
    body = _body(client, meal_id)
    assert "both" in body or ("standard" in body and "model" in body)
    assert "test as usual" in body


def test_a_tripped_kill_switch_shows_the_baseline_and_still_no_dose(
    client: TestClient, db: Session, meal_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_gate(client, db, monkeypatch, state=2, kill_switch=True)
    body = _body(client, meal_id)
    assert "paused" in body or "baseline" in body
    for banned in ("dose", "bolus", "units", "inject"):
        assert banned not in body
