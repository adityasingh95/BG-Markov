"""S-1003 [SAFETY] — the bolus calculator screen (SDET, written RED first).

**The most dangerous screen in the system.** Everything else here describes; this one
suggests putting insulin into a person who cannot feel the result.

Three adversarial directions, all of them things a reasonable person would add:

1. **An IOB input field** — "sometimes you know it better than the log". It is subtracted,
   so an underestimate silently *increases* the dose, and unlike carbs or BG there is
   nothing to check it against.
2. **The cap without the flag** — because 15 U "is the safe answer anyway". It is not an
   answer; it is a 900 g typo wearing one.
3. **A "log this dose" button** — convenient, and it quietly turns `bolus_log` into a
   record of suggestions rather than injections, corrupting every future IOB.

RED: `GET /bolus` 404s; `api/bolus.py` does not exist.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.deps import get_session
from core.safety import BOLUS_BG_FLOOR, MAX_BOLUS_U
from data.db import create_all, make_engine, session_factory
from data.tables import PatientProfile

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "api/templates/bolus.html"
_MODULE = _REPO_ROOT / "api/bolus.py"

_ICR, _ISF, _TARGET = 9.0, 30.0, 135  # DL-032, clinician-confirmed
_AT = "2026-01-01T12:30:00"


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'bolus_ui.db'}")
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


def _profile(session: Session, *, icr: float | None = _ICR) -> None:
    session.add(PatientProfile(
        effective_from=dt.date(2026, 1, 1), icr=icr, isf=_ISF, target_bg=_TARGET,
    ))
    session.flush()


def _page(client: TestClient, **params: object) -> str:
    """The rendered calculator, lowercased — **after asserting it rendered**.

    Absence assertions against an error page are free and prove nothing (the S-1002
    lesson). Everything below goes through here.
    """
    query = {"at": _AT, "carbs_g": "40", "current_bg": "180", **params}
    r = client.get("/bolus", params=query)
    assert r.status_code == 200, f"the calculator did not render: {r.status_code} {r.text}"
    return r.text.lower()


def _doses(body: str) -> list[str]:
    """Every "N.NN u" looking figure on the page — used to assert none is present."""
    return re.findall(r"\d+\.\d{2}\s*u\b", body)


# --- ★ state 1: the profile is incomplete (Gate 2 is retired) ----------------


@pytest.mark.parametrize("icr", [None, 0.0, -3.0])
def test_a_missing_or_nonsensical_icr_gives_the_profile_incomplete_state(
    client: TestClient, db: Session, icr: float | None
) -> None:
    """★ S-1011/DL-035 — this is an **input error**, not a gate refusal. The page says
    "set the ICR", and there is no dose anywhere on it."""
    _profile(db, icr=icr)
    body = _page(client)
    assert "icr" in body
    assert not _doses(body), f"a dose was rendered with icr={icr!r}: {_doses(body)}"


def test_no_profile_at_all_gives_the_profile_incomplete_state(
    client: TestClient, db: Session
) -> None:
    """Day one. No row at all is the same answer as a null ICR."""
    body = _page(client)
    assert "icr" in body or "profile" in body
    assert not _doses(body)


def test_the_incomplete_state_does_not_read_as_a_gate(
    client: TestClient, db: Session
) -> None:
    """★ Gate 2 was retired (S-1011). Calling this a locked gate would tell the reader a
    dose gate exists and send them looking for the control that opens it."""
    _profile(db, icr=None)
    body = _page(client)
    for gone in ("gate 2", "gate2", "not passed", "locked", "gatenotpassed"):
        assert gone not in body, f"the profile-incomplete state reads as a gate: {gone!r}"


# --- ★ state 2: she is already low (INV-4) -----------------------------------


def test_bg_79_refuses_and_bg_80_computes(client: TestClient, db: Session) -> None:
    """★ THE INV-4 BOUNDARY, ON THE SCREEN. 80 is the floor (03 §1 / DL-043 — the same
    number the warning band uses, so "below 80" means one thing everywhere)."""
    _profile(db)
    assert BOLUS_BG_FLOOR == 80.0

    low = _page(client, current_bg="79")
    assert "treat the low" in low or "low first" in low
    assert not _doses(low), f"a dose was offered at BG 79: {_doses(low)}"

    ok = _page(client, current_bg="80")
    assert _doses(ok), "BG 80 must compute"


def test_a_very_low_reading_still_refuses(client: TestClient, db: Session) -> None:
    _profile(db)
    body = _page(client, current_bg="45")
    assert not _doses(body)


# --- ★ state 3: the implausible input is FLAGGED, not silently capped --------


def _outside_the_working(body: str) -> str:
    """The page with every `<code>` block removed.

    ★ `recommend_bolus` puts "(CAPPED — input looks implausible, please re-check)" inside
    its `arithmetic` string, which the page renders in a `<code>` block. So asserting the
    warning words appear *somewhere* in the body passes even when no visible flag is
    rendered at all — the words ride in on the working. This strips that, so the assertion
    is about what she would actually see above the number.
    """
    return re.sub(r"<code[^>]*>.*?</code>", " ", body, flags=re.DOTALL)


def test_a_carbs_typo_shows_the_flag_not_a_confident_fifteen_units(
    client: TestClient, db: Session
) -> None:
    """★ INV-3, AND THE MOST IMPORTANT ASSERTION ON THIS SCREEN.

    Capping alone hands back a plausible-looking 15 U for a 900 g typo — a number that
    reads as a decision rather than an error. The words are the safety margin, and they
    have to be **visible**, not buried in the arithmetic line.
    """
    _profile(db)
    body = _page(client, carbs_g="900")
    assert f"{MAX_BOLUS_U:.2f}" in body or "15" in body

    visible = _outside_the_working(body)
    assert "looks wrong" in visible or "implausible" in visible, (
        "the cap was rendered without a visible flag — a typo wearing an answer"
    )
    assert "re-check" in visible


def test_the_flag_is_its_own_element_not_a_phrase_in_the_working(
    client: TestClient, db: Session
) -> None:
    """★ It must be a rendered cue she cannot read past, not a clause inside the
    `<code>` line she is least likely to read."""
    _profile(db)
    body = _page(client, carbs_g="900")
    cues = re.findall(r"<section[^>]*data-risk-cue[^>]*>.*?</section>", body, re.DOTALL)
    assert cues, "no risk cue element was rendered for an implausible input"
    assert any("looks wrong" in c or "implausible" in c for c in cues)


def test_a_normal_meal_is_not_flagged(client: TestClient, db: Session) -> None:
    _profile(db)
    visible = _outside_the_working(_page(client, carbs_g="40"))
    assert "implausible" not in visible and "looks wrong" not in visible


# --- ★ the arithmetic is shown, and it is the arithmetic the tests compute ----


@pytest.mark.parametrize(
    ("carbs", "bg", "expected"),
    [
        (40.0, 180.0, 5.94),   # 40/9 = 4.444; (180-135)/30 = 1.5
        (0.0, 180.0, 1.50),    # correction only
        (60.0, 135.0, 6.67),   # carbs only, at target
        (30.0, 210.0, 5.83),   # 3.333 + 2.5
        (90.0, 90.0, 8.50),    # 10.0 - 1.5 → a negative correction, still positive total
    ],
)
def test_golden_doses_render_to_two_decimal_places(
    client: TestClient, db: Session, carbs: float, bg: float, expected: float
) -> None:
    """★ Hand-computed against the clinical formula (07 §11) with ICR 9 / ISF 30 /
    target 135 (DL-032), IOB 0. The number on the screen is the number in the test."""
    _profile(db)
    body = _page(client, carbs_g=str(carbs), current_bg=str(bg))
    assert f"{expected:.2f}" in body, f"expected {expected:.2f} U on the page"


def test_the_full_arithmetic_is_shown(client: TestClient, db: Session) -> None:
    """REQ-043 — she can check it. A number with no working is something to obey."""
    _profile(db)
    body = _page(client)
    assert "carb dose" in body and "correction" in body


def test_the_framing_line_is_present(client: TestClient, db: Session) -> None:
    """★ "A suggestion for review… Not an instruction." (S-901). The framing is not
    decoration; it is the difference between a tool and an authority."""
    _profile(db)
    body = _page(client)
    assert "suggestion" in body and "not an instruction" in body


# --- ★ IOB is displayed, never typed (REQ-020) -------------------------------


def test_no_iob_input_element_exists_in_the_template() -> None:
    """★ THE ONE THAT MATTERS MOST.

    IOB is *subtracted*, so an underestimate silently increases the dose. Carbs are
    checkable against the plate and BG against the meter; a half-remembered IOB is
    checkable against nothing. A typed IOB is a forbidden pattern (`detect_manual_iob`).
    """
    source = _TEMPLATE.read_text().lower()
    for element in re.findall(r"<input[^>]*>", source):
        assert "iob" not in element, f"an IOB input exists: {element}"
        assert "insulin_on_board" not in element
    assert "<select" not in source or "iob" not in source.split("<select")[1][:200]


def test_iob_is_displayed_with_its_provenance(client: TestClient, db: Session) -> None:
    """Shown, and shown to come from the log — so a wrong-looking IOB is traceable rather
    than merely doubted."""
    _profile(db)
    body = _page(client)
    assert "iob" in body or "insulin on board" in body
    assert "log" in body or "from your" in body or "derived" in body


# --- ★ no ML in the dose path, structurally ----------------------------------


def test_the_bolus_module_imports_nothing_from_models() -> None:
    """★ REQ-042 — no ML in the dose path, made a grep-able fact rather than a promise.

    This is why the calculator lives in its own module: `api/app.py` imports
    `models.metrics` and `models.shadow` for the operator dashboard, so the property would
    be untestable by inspection if the dose routes lived there.
    """
    tree = ast.parse(_MODULE.read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("models"):
            imported.append(node.module or "")
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names if a.name.startswith("models")]
    assert not imported, f"the dose path imports from models/: {imported}"


def test_the_bolus_module_never_catches_a_safety_exception() -> None:
    """★ Branch, do not catch — the S-1002 discipline applied to the dose path.

    `recommend_bolus` raises `SafetyViolation` below BG 80 and `ValueError` on a bad ICR.
    A route that caught them would be one refactor from rendering "we couldn't calculate —
    here's an estimate".
    """
    caught: list[str] = []
    for node in ast.walk(ast.parse(_MODULE.read_text())):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            for sub in ast.walk(node.type):
                if isinstance(sub, ast.Name) and sub.id in (
                    "SafetyViolation", "GateNotPassed", "ValueError",
                    "Exception", "BaseException",
                ):
                    caught.append(sub.id)
    assert not caught, f"the dose path catches {caught} instead of branching"


# --- ★ nothing is logged, nothing is autofilled ------------------------------


def test_no_form_carries_the_dose_into_a_log_or_an_action(
    client: TestClient, db: Session
) -> None:
    """★ `bolus_log` is the source of truth for IOB (04 §2). A dose written there because
    the calculator *suggested* it — rather than because she injected it — corrupts every
    future IOB, and therefore every future suggestion, with no error and no way to tell.
    """
    _profile(db)
    body = _page(client)
    for banned in ("log this", "save this dose", "record dose", 'action="/api/boluses'):
        assert banned not in body, f"the calculator offers to log its own output: {banned!r}"
    source = _TEMPLATE.read_text().lower()
    assert "method=\"post\"" not in source, "the calculator posts something somewhere"
