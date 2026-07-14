"""S-204 — dish ingest, portion scaling, free-text queueing (SDET, RED first)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.macros import FREE_TEXT_MACRO_CONFIDENCE, TABLE_MACRO_CONFIDENCE
from data.dishes import (
    IFCT_SEED,
    dish_macros,
    find_dish,
    ingest_dishes,
    resolve_dish,
)
from data.tables import Dish, DishSource


def test_ingest_seed_populates_the_table(session: Session) -> None:
    n = ingest_dishes(session, IFCT_SEED)
    assert n == len(IFCT_SEED) > 0
    roti = find_dish(session, "roti")
    assert roti is not None
    assert roti.source == DishSource.IFCT2017


def test_find_dish_is_case_insensitive(session: Session) -> None:
    ingest_dishes(session, IFCT_SEED)
    assert find_dish(session, "ROTI") is not None
    assert find_dish(session, "Roti") is not None


def test_two_roti_is_exactly_double_one_roti(session: Session) -> None:
    ingest_dishes(session, IFCT_SEED)
    roti = find_dish(session, "roti")
    assert roti is not None
    one = dish_macros(roti, 1)
    two = dish_macros(roti, 2)
    assert two.carbs_g == one.carbs_g * 2
    assert two.protein_g == one.protein_g * 2
    assert two.fat_g == one.fat_g * 2
    assert two.fiber_g == one.fiber_g * 2


def test_resolve_known_dish_is_high_confidence(session: Session) -> None:
    ingest_dishes(session, IFCT_SEED)
    res = resolve_dish(session, "dal")
    assert res.macro_confidence == TABLE_MACRO_CONFIDENCE == 95
    assert res.needs_review is False
    assert res.dish.source == DishSource.IFCT2017


def test_resolve_free_text_lowers_confidence_and_queues(session: Session) -> None:
    ingest_dishes(session, IFCT_SEED)
    res = resolve_dish(session, "aunty's special khichdi")
    assert res.macro_confidence == FREE_TEXT_MACRO_CONFIDENCE == 60  # not 95
    assert res.needs_review is True

    queued = session.query(Dish).filter(Dish.needs_review.is_(True)).all()
    assert any(d.name == "aunty's special khichdi" for d in queued)
    assert res.dish.source == DishSource.estimated
