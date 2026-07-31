"""S-1024 [SAFETY] (SDET) — a synthetic database says so, on every screen. RED first.

`scripts/seed_demo_db.py` produces 658 meals, 1034 boluses, 29 hypo rescues and a fitted
model, and **every screen renders it exactly as it renders real capture.** The failure that
enables is not a crash; it is *believing a number*. An operator who reads the shadow report
on a seeded database and sees a plausible hypo recall has learned nothing about her, and
nothing on the page says so.

★ The marker lives in the **database**, not the environment. An env var can be forgotten,
inherited, or left over from the previous run, and the mistake is silent in both directions.
Provenance belongs to the data: move the file, reopen it in a month, hand it to someone else,
and it still says what it is.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse
from starlette.routing import Route

from api.app import app
from api.deps import get_session
from data.db import create_all, make_engine, session_factory
from data.provenance import DEMO_BANNER_MARK, is_demo_database, mark_demo_database

_API_DIR = pathlib.Path(__file__).resolve().parents[2] / "api"


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'banner.db'}")
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _html_get_paths() -> list[str]:
    """Every HTML GET route, **enumerated from the app**.

    ★ A hand-written list is a list someone forgets to extend, and the page they forget is
    the page the next reader happens to open.
    """
    paths: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute | Route):
            continue
        methods = route.methods or set()
        if "GET" not in methods:
            continue
        # ★ HTML pages only, decided by the route's DECLARED response class — not by a
        # hand-written exclusion list, which is the same forgettable list this enumeration
        # exists to avoid. `/openapi.json` and `/docs` are routes and are not pages.
        if not (isinstance(route, APIRoute) and route.response_class is HTMLResponse):
            continue
        path = route.path
        if path.startswith(("/api/", "/static")):
            continue
        if "{" in path:
            continue  # parameterised pages need a row; covered separately below
        paths.append(path)
    return sorted(set(paths))


def test_there_is_at_least_one_html_page_to_check() -> None:
    """If the enumeration silently returns nothing, every test below passes vacuously."""
    assert len(_html_get_paths()) >= 5, _html_get_paths()


@pytest.mark.parametrize("path", _html_get_paths())
def test_a_demo_database_says_so_on_every_page(
    client: TestClient, db: Session, path: str
) -> None:
    mark_demo_database(db, note="test seed")
    db.commit()
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    assert DEMO_BANNER_MARK in resp.text, f"{path} renders no demo banner"


@pytest.mark.parametrize("path", _html_get_paths())
def test_an_unmarked_database_shows_no_banner(client: TestClient, path: str) -> None:
    """★ A banner that is always on is a banner nobody reads — and it would then be sitting
    on top of her real records, telling her they are fake."""
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    assert DEMO_BANNER_MARK not in resp.text, f"{path} shows a demo banner on real data"


def test_the_parameterised_pages_carry_it_too(client: TestClient, db: Session) -> None:
    """`/meals/{id}/…` are the pages she actually looks at."""
    import datetime as dt

    from data.tables import LoggedBy, MealEvent, MealType

    mark_demo_database(db, note="test seed")
    meal = MealEvent(
        datetime=dt.datetime(2026, 7, 30, 8, 0),
        logged_at=dt.datetime(2026, 7, 30, 8, 40),
        meal_type=MealType.breakfast,
        pre_bg=140,
        pre_bg_time=dt.datetime(2026, 7, 30, 8, 0),
        carbs_g=45.0,
        meal_bolus_units=5.0,
        bolus_offset_min=-10,
        logged_by=LoggedBy.patient,
    )
    db.add(meal)
    db.commit()

    for path in (f"/meals/{meal.meal_id}/post-bg", f"/meals/{meal.meal_id}/readout"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert DEMO_BANNER_MARK in resp.text, f"{path} renders no demo banner"


def test_exactly_one_templates_instance_under_api() -> None:
    """★ Two `Jinja2Templates` objects is how the first gap gets in.

    The banner is a context processor on **one** object. A second instance renders pages
    that never see it, and it is invisible until someone opens that page on demo data and
    believes it.
    """
    constructions: list[str] = []
    for path in sorted(_API_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Jinja2Templates"
            ):
                constructions.append(f"{path.name}:{node.lineno}")
    assert len(constructions) == 1, (
        f"expected one Jinja2Templates instance under api/, found {constructions}. "
        "The banner is a context processor on one object; a second instance renders pages "
        "that never see it."
    )


def test_the_seeder_always_marks_what_it_makes(tmp_path: pathlib.Path) -> None:
    """★ The seeder is the only thing that makes synthetic data, so it is the only place
    the mark can be forgotten. A seeder that can produce an unmarked demo database is the
    whole defect."""
    import datetime as dt

    from scripts.seed_demo_db import seed

    db_path = tmp_path / "seeded.db"
    seed(str(db_path), days=3, seed_value=1, end=dt.date(2026, 7, 30))

    engine = make_engine(f"sqlite:///{db_path}")
    with session_factory(engine)() as session:
        assert is_demo_database(session), "the seeder produced an UNMARKED demo database"
