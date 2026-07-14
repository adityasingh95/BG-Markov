"""Dish table: ingest, portion scaling, and free-text queueing (REQ-009).

A table hit auto-populates macros at `macro_confidence = 95`. An unknown dish is
accepted as free text at `macro_confidence = 60` and **queued** for the operator
to add properly (`needs_review = True`), so a guess is never laundered as a
confident value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.macros import FREE_TEXT_MACRO_CONFIDENCE, TABLE_MACRO_CONFIDENCE, Macros
from data.tables import Dish, DishSource

# Representative seed of her repertoire, macros per standard household portion.
# NOTE (DL-015): placeholder values pending the operator's real IFCT-2017
# dataset; S-204 delivers the ingest path, not the nutritional data.
_SEED_FIELDS = ("name", "portion_unit", "carbs_g", "protein_g", "fat_g", "fiber_g")
_SEED_ROWS: list[tuple[str, str, float, float, float, float]] = [
    ("roti", "roti", 15.0, 3.0, 3.0, 2.0),
    ("dal", "katori", 20.0, 9.0, 4.0, 5.0),
    ("rice", "katori", 45.0, 4.0, 0.5, 1.0),
    ("rajma", "katori", 30.0, 9.0, 3.0, 8.0),
    ("sabzi", "katori", 10.0, 3.0, 6.0, 4.0),
    ("idli", "piece", 12.0, 2.0, 0.3, 1.0),
]
IFCT_SEED: list[dict[str, Any]] = [
    dict(zip(_SEED_FIELDS, row, strict=True)) for row in _SEED_ROWS
]


class DishResolution(NamedTuple):
    dish: Dish
    macro_confidence: int
    needs_review: bool


def ingest_dishes(session: Session, rows: Iterable[Mapping[str, Any]]) -> int:
    """Bulk-load dish rows (IFCT 2017). Returns the number inserted."""
    dishes = [
        Dish(
            name=row["name"],
            portion_unit=row["portion_unit"],
            carbs_g=row["carbs_g"],
            protein_g=row["protein_g"],
            fat_g=row["fat_g"],
            fiber_g=row["fiber_g"],
            source=DishSource(row.get("source", DishSource.IFCT2017)),
        )
        for row in rows
    ]
    session.add_all(dishes)
    session.commit()
    return len(dishes)


def find_dish(session: Session, name: str) -> Dish | None:
    """Case-insensitive exact match on dish name."""
    stmt = select(Dish).where(func.lower(Dish.name) == name.lower())
    return session.scalars(stmt).first()


def dish_macros(dish: Dish, servings: float) -> Macros:
    """Per-portion macros scaled by the portion multiplier."""
    per_portion = Macros(
        carbs_g=dish.carbs_g,
        protein_g=dish.protein_g,
        fat_g=dish.fat_g,
        fiber_g=dish.fiber_g,
    )
    return per_portion.scaled(servings)


def resolve_dish(session: Session, name: str) -> DishResolution:
    """Resolve a dish by name.

    Table hit ⇒ high confidence (95), no review. Miss ⇒ a free-text dish is
    created, queued for the operator (needs_review), and stamped at the lower
    free-text confidence (60).
    """
    existing = find_dish(session, name)
    if existing is not None:
        return DishResolution(existing, TABLE_MACRO_CONFIDENCE, needs_review=False)

    free_text = Dish(
        name=name,
        portion_unit="serving",
        carbs_g=0.0,
        protein_g=0.0,
        fat_g=0.0,
        fiber_g=0.0,
        source=DishSource.estimated,
        needs_review=True,
    )
    session.add(free_text)
    session.commit()
    return DishResolution(free_text, FREE_TEXT_MACRO_CONFIDENCE, needs_review=True)
