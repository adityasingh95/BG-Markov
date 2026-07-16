"""S-403 — exercise encoding (one-hot + duration interactions). SDET, RED first.

Light exercise lowers BG; intense can raise it — the effect is non-monotone in
intensity. A numeric 0/1/2 column forces the intense response to be a scalar
multiple of the light one, which mathematically forbids the physiology. The
not-scalar-multiple test is the load-bearing guard. See docs/stories/S-403.md.

RED: `features.exercise` does not exist yet.
"""

from __future__ import annotations

import pytest

from features.exercise import encode_exercise

_KEYS = ["ex_light", "ex_intense", "ex_light_min", "ex_intense_min"]


def _vec(intensity: str, duration: int, prefix: str = "ex") -> list[float]:
    enc = encode_exercise(intensity, duration, prefix=prefix)
    return [enc[f"{prefix}_light"], enc[f"{prefix}_intense"],
            enc[f"{prefix}_light_min"], enc[f"{prefix}_intense_min"]]


def test_none_is_all_zero_baseline() -> None:
    enc = encode_exercise("none", 60)
    assert set(enc) == set(_KEYS)
    assert all(v == 0.0 for v in enc.values())


def test_light_sets_indicator_and_duration() -> None:
    enc = encode_exercise("light", 60)
    assert enc["ex_light"] == 1.0
    assert enc["ex_intense"] == 0.0
    assert enc["ex_light_min"] == 60.0
    assert enc["ex_intense_min"] == 0.0


def test_intense_sets_indicator_and_duration() -> None:
    enc = encode_exercise("intense", 45)
    assert enc["ex_intense"] == 1.0
    assert enc["ex_light"] == 0.0
    assert enc["ex_intense_min"] == 45.0
    assert enc["ex_light_min"] == 0.0


def test_duration_actually_enters_the_encoding() -> None:
    """light/30 and light/60 differ only in the duration-interaction term."""
    a = encode_exercise("light", 30)
    b = encode_exercise("light", 60)
    assert a["ex_light"] == b["ex_light"] == 1.0
    assert a["ex_light_min"] == 30.0
    assert b["ex_light_min"] == 60.0


def test_light_and_intense_are_not_scalar_multiples() -> None:
    """★ The physiology-preserving property: no scalar k makes intense == k·light.

    A numeric 0/1/2 encoding would make intense/60 exactly 2× light/60, forcing one
    sign for both. One-hot + duration interactions activate different dimensions, so
    the model can fit β_light < 0 (lowers) and β_intense > 0 (raises)."""
    light = _vec("light", 60)
    intense = _vec("intense", 60)

    # There is no k with intense == k * light (they occupy different dimensions).
    ks = {i / lt for lt, i in zip(light, intense, strict=True) if lt != 0.0}
    # For every non-zero component of `light`, intense is 0 there -> k would be 0,
    # but intense has non-zero components where light is 0 -> no single k works.
    assert ks == {0.0}
    assert any(
        i != 0.0 for lt, i in zip(light, intense, strict=True) if lt == 0.0
    ), "intense must be non-zero on a dimension where light is zero"


def test_prefix_supports_prior_exercise() -> None:
    enc = encode_exercise("intense", 20, prefix="pre_ex")
    assert enc["pre_ex_intense"] == 1.0
    assert enc["pre_ex_intense_min"] == 20.0
    assert "ex_light" not in enc


def test_unknown_intensity_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_exercise("sprinting", 10)
