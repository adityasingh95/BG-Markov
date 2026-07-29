"""S-1001a — the rendered operator report card (SDET, written RED first).

The screen a human reads before deciding whether she may see the model at all. What it
must never do: imply a dose exists, show a plain-accuracy figure, show a gate that was
retired, or crash on the state it will actually be in for months (no model, no data).

RED: `GET /operator/shadow` does not exist.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory

_TEMPLATE = pathlib.Path(__file__).resolve().parents[2] / "api/templates/operator_shadow.html"


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> Iterator[TestClient]:
    engine = make_engine(f"sqlite:///{tmp_path / 'shadow_ui.db'}")
    create_all(engine)
    maker = session_factory(engine)

    def _session() -> Iterator[Session]:
        with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- ★ the state it will actually be in for months ---------------------------


def test_renders_with_no_model_and_no_data(client: TestClient) -> None:
    """★ There is no fitted model and nothing has been predicted. That is today. The page
    must render a plain "nothing to show yet" — not a 500, and not a table of zeros that
    reads as a model scoring badly."""
    r = client.get("/operator/shadow")
    assert r.status_code == 200
    body = r.text.lower()
    assert "no model" in body or "nothing to show" in body or "not yet" in body


def test_the_empty_state_does_not_show_fabricated_metrics(client: TestClient) -> None:
    """A zeroed metric table would say "this model catches 0% of her lows", which is a
    statement about a model that does not exist."""
    body = client.get("/operator/shadow").text.lower()
    assert "0%" not in body, "the pre-data page must not render metric values"


# --- ★ what must never appear ------------------------------------------------


def test_no_plain_accuracy_figure_anywhere(client: TestClient) -> None:
    """★ 07 §9 — meaningless on an imbalanced 5-class problem, and it rewards a model that
    never catches a low. Asserted on the rendered page AND on the template source, so it
    cannot be reintroduced inside a branch this test happens not to hit."""
    assert "accuracy" not in client.get("/operator/shadow").text.lower()
    assert "accuracy" not in _TEMPLATE.read_text().lower()


def test_no_dose_field_anywhere_on_an_operator_screen(client: TestClient) -> None:
    """★ 05b §7.2 — "No dose ever appears on an operator screen." A dose must not be able
    to ride in on an evidence page."""
    source = _TEMPLATE.read_text().lower()
    for banned in ("bolus", "units of insulin", "inject", "recommended dose"):
        assert banned not in source, f"{banned!r} appears on the operator report card"


def test_gate_2_appears_nowhere(client: TestClient) -> None:
    """★ Gate 2 was retired (S-1011, DL-035). Rendering it would tell the operator a dose
    gate exists — and the natural next thought is to look for the control that opens it."""
    body = client.get("/operator/shadow").text.lower()
    for gone in ("gate 2", "gate2", "prescriptive"):
        assert gone not in body, f"{gone!r} survived the S-1011 retirement on the UI"


# --- gate 1 status ------------------------------------------------------------


def test_all_five_gate1_conditions_are_named(client: TestClient) -> None:
    """★ 03 §3 lists five. Showing four and calling it the list would put a
    complete-looking checklist in front of the person deciding to trust the model — which
    is exactly what DL-041 found in the code."""
    body = client.get("/operator/shadow").text.lower()
    assert "meal" in body                      # volume
    assert "simple method" in body or "baseline" in body
    assert "honest" in body or "percentages" in body
    assert "90" in body and "day" in body      # shadow clock
    assert "promot" in body or "turned on" in body


def test_gate1_is_shown_closed_today(client: TestClient) -> None:
    body = client.get("/operator/shadow").text.lower()
    assert "closed" in body or "not yet" in body
    assert "gate 1 open" not in body


# --- with a report ------------------------------------------------------------


def _with_evidence(monkeypatch: pytest.MonkeyPatch, **kw: object) -> None:
    """Point the route's data-loading seam at a synthetic report.

    `load_shadow_evidence` is the DB boundary — it answers "what evidence exists?", not
    "may she see it?". Patching it exercises RENDERING, which is what this story is. It is
    not a gate bypass: this page is operator-only and INV-2 governs patient output, which
    is a different surface entirely (S-1002).
    """
    import api.app as app_module
    from api.presenters import BaselineComparison
    from models.shadow import build_shadow_report

    def _fake(_session: object) -> object:
        rng = np.random.default_rng(3)
        n = 60
        is_hypo = np.array([1] * 20 + [0] * 40)
        score = np.where(is_hypo == 1, rng.uniform(0.5, 0.9, n), rng.uniform(0.0, 0.4, n))
        states = np.where(is_hypo == 1, 2, 3)
        bg = np.where(is_hypo == 1, 67.0, 130.0)
        report = build_shadow_report(
            hypo_score=score, is_hypo=is_hypo, predicted_bg=bg, reference_bg=bg,
            pred_states=states, actual_states=states,
            unconstrained_beta_insulin=float(kw.get("beta_insulin", 0.42)),
        )
        return (report, BaselineComparison(hypo_recall=0.30), None)

    monkeypatch.setattr(app_module, "load_shadow_evidence", _fake)


def test_a_confounding_alarm_is_visible_in_the_html(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ The `β_insulin < 0` case renders a VISIBLE alarm, not a silent pass. Confounding
    by indication is how a model comes to conclude that insulin raises blood sugar. A
    family member reading this page has no other way to find that out."""
    _with_evidence(monkeypatch, beta_insulin=-0.31)
    body = client.get("/operator/shadow").text.lower()
    assert "insulin" in body
    assert "check" in body or "alarm" in body or "does not make" in body or "warning" in body


def test_a_healthy_model_still_shows_the_insulin_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row exists whether or not it alarms — otherwise its absence could be mistaken
    for its being clear."""
    _with_evidence(monkeypatch, beta_insulin=0.42)
    assert "insulin" in client.get("/operator/shadow").text.lower()


def test_the_headline_metric_is_hypo_recall_not_something_gentler(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ 07 §9 — catching lows is what "good" means here. It must be the first thing on
    the page, not the fourth."""
    _with_evidence(monkeypatch)
    body = client.get("/operator/shadow").text.lower()
    assert "low" in body
    assert body.index("catches her lows") < body.index("typical miss")


def test_full_charts_sit_behind_a_disclosure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05b §7.2 — available, not the first thing."""
    _with_evidence(monkeypatch)
    body = client.get("/operator/shadow").text.lower()
    assert "<details" in body
    assert "detailed charts" in body


def test_the_operator_page_links_to_the_report_card(client: TestClient) -> None:
    """It must be reachable from the operator nav, or it does not exist in practice."""
    assert "/operator/shadow" in client.get("/operator").text


def test_the_patient_facing_pages_do_not_link_to_it(client: TestClient) -> None:
    """★ Operator-only (05b §7). The meal-log page is hers; the evidence screen is not."""
    assert "/operator/shadow" not in client.get("/").text
