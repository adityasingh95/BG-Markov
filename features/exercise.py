"""Exercise encoding — one-hot + duration interactions (S-403, REQ-024).

Light exercise lowers BG; intense exercise can raise it (adrenaline). The effect is
**non-monotone in intensity**, so intensity must NOT be a numeric 0/1/2 column — in
a linear model that forces the intense response to be a scalar multiple of the light
one, which cannot represent the physiology (07 §5). Instead: one-hot indicators for
light/intense (none is the reference level) plus a duration-interaction term for
each, so the model can fit opposite-signed effects.

Pure function; takes the intensity as a ``str`` (the ``ExIntensity`` StrEnum value)
so this module imports nothing from ``data``.
"""

from __future__ import annotations

_INTENSITIES = ("none", "light", "intense")


def encode_exercise(intensity: str, duration_min: int, prefix: str = "ex") -> dict[str, float]:
    """One-hot intensity + duration interactions.

    Returns ``{prefix}_light``, ``{prefix}_intense`` (indicators) and
    ``{prefix}_light_min``, ``{prefix}_intense_min`` (duration interactions).
    ``none`` yields all zeros (the reference level). ``prefix`` lets the pipeline
    reuse this for in-window exercise (``ex``) and prior exercise (``pre_ex``).
    """
    if intensity not in _INTENSITIES:
        raise ValueError(f"unknown exercise intensity: {intensity!r} (expected {_INTENSITIES})")
    is_light = 1.0 if intensity == "light" else 0.0
    is_intense = 1.0 if intensity == "intense" else 0.0
    return {
        f"{prefix}_light": is_light,
        f"{prefix}_intense": is_intense,
        f"{prefix}_light_min": is_light * float(duration_min),
        f"{prefix}_intense_min": is_intense * float(duration_min),
    }
