"""Macronutrients and their portion scaling (pure).

`macro_confidence` is used downstream as a **sample weight**, so free-text
guesses must be marked less confident than table lookups — never laundered as a
confident value.
"""

from __future__ import annotations

from typing import NamedTuple

# `macro_confidence` (0–100) stamped on a meal by dish source (02 §F-1.1).
TABLE_MACRO_CONFIDENCE: int = 95
FREE_TEXT_MACRO_CONFIDENCE: int = 60


class Macros(NamedTuple):
    """Macronutrients for a quantity of food, in grams."""

    carbs_g: float
    protein_g: float
    fat_g: float
    fiber_g: float

    def scaled(self, servings: float) -> Macros:
        """Linear scaling by a portion multiplier (`2 × roti` = double)."""
        return Macros(
            carbs_g=self.carbs_g * servings,
            protein_g=self.protein_g * servings,
            fat_g=self.fat_g * servings,
            fiber_g=self.fiber_g * servings,
        )
