"""S-1018 (SDET) — a reported clinical time carries no offset. RED first.

ADR-8's known failure is *fabricating* a clinical timestamp. This is the other one:
**relabelling** the timestamp she reported. It leaves no anomaly behind — 02:30 is a
perfectly plausible row — so it has to be refused at the door or it is never detectable.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.timestamps import require_naive

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def test_a_naive_datetime_passes_through_unchanged() -> None:
    value = dt.datetime(2026, 7, 30, 8, 0)
    assert require_naive(value, field="datetime") is value


def test_an_aware_utc_datetime_is_refused() -> None:
    with pytest.raises(ValueError, match="datetime"):
        require_naive(dt.datetime(2026, 7, 30, 2, 30, tzinfo=dt.UTC), field="datetime")


def test_an_aware_offset_datetime_is_refused() -> None:
    """★ +05:30 — the offset that actually applies to the person using this."""
    with pytest.raises(ValueError, match="post_bg_time"):
        require_naive(dt.datetime(2026, 7, 30, 8, 0, tzinfo=IST), field="post_bg_time")


def test_the_error_names_the_field_and_says_what_to_send() -> None:
    with pytest.raises(ValueError) as excinfo:
        require_naive(dt.datetime(2026, 7, 30, 8, 0, tzinfo=IST), field="pre_bg_time")
    message = str(excinfo.value)
    assert "pre_bg_time" in message, "a 422 that does not name the field is a puzzle"
    assert "local" in message.lower(), "the message must say what the right shape is"


def test_it_raises_rather_than_converting() -> None:
    """★ The adversarial case, and the one a reviewer will not notice.

    ``value.replace(tzinfo=None)`` is one character shorter than the correct fix, returns a
    naive datetime, satisfies every type checker, and returns **the wrong time** — 02:30 for
    a breakfast eaten at 08:00. Asserting "the result is naive" passes on it. So the
    assertion is on the *raise*, and there is no result to inspect.
    """
    aware = dt.datetime(2026, 7, 30, 8, 0, tzinfo=IST)
    with pytest.raises(ValueError):
        require_naive(aware, field="datetime")
    assert aware.tzinfo is IST, "the input must not be mutated on the way out"


def test_zero_offset_is_still_an_offset() -> None:
    """``+00:00`` is not the same statement as "no offset".

    A client that sends UTC has told us *an instant*. It has not told us the wall-clock
    time she read off her phone, and on a phone in UTC the two coincide by accident. The
    accident is exactly what made this bug invisible for the whole life of the project.
    """
    with pytest.raises(ValueError):
        require_naive(dt.datetime(2026, 7, 30, 2, 30, tzinfo=dt.timezone(dt.timedelta(0))),
                      field="datetime")
