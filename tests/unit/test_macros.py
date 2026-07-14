"""S-204 — macro scaling + confidence constants (SDET, written RED first)."""

from __future__ import annotations

import pytest

from core.macros import (
    FREE_TEXT_MACRO_CONFIDENCE,
    TABLE_MACRO_CONFIDENCE,
    Macros,
)


def test_scaled_doubles_every_component() -> None:
    one = Macros(carbs_g=15.0, protein_g=3.0, fat_g=3.0, fiber_g=2.0)
    assert one.scaled(2) == Macros(carbs_g=30.0, protein_g=6.0, fat_g=6.0, fiber_g=4.0)


def test_scaled_is_linear() -> None:
    m = Macros(carbs_g=10.0, protein_g=2.0, fat_g=1.0, fiber_g=0.5)
    assert m.scaled(0) == Macros(0.0, 0.0, 0.0, 0.0)
    assert m.scaled(3) == Macros(30.0, 6.0, 3.0, 1.5)


def test_two_portions_equal_double_one_portion() -> None:
    m = Macros(carbs_g=45.0, protein_g=4.0, fat_g=0.5, fiber_g=1.0)
    two = m.scaled(2)
    one = m.scaled(1)
    assert two == Macros(
        carbs_g=one.carbs_g * 2,
        protein_g=one.protein_g * 2,
        fat_g=one.fat_g * 2,
        fiber_g=one.fiber_g * 2,
    )


@pytest.mark.parametrize(
    ("constant", "value"),
    [(TABLE_MACRO_CONFIDENCE, 95), (FREE_TEXT_MACRO_CONFIDENCE, 60)],
)
def test_confidence_constants(constant: int, value: int) -> None:
    assert constant == value


def test_free_text_is_less_confident_than_table() -> None:
    assert FREE_TEXT_MACRO_CONFIDENCE < TABLE_MACRO_CONFIDENCE
