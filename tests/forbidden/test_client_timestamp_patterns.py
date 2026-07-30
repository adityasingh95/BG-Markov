"""S-1018 [SAFETY] (SDET) — the client must not convert a reported time through UTC.

Companion to the `datetime.now()` guard in `test_forbidden_patterns.py`. That one catches
a clinical timestamp being **fabricated**; this one catches it being **relabelled**.

★ The offending line is one of the most natural things anyone writes when handed a
`datetime-local` value:

    var reported = new Date(input.value).toISOString();

It is idiomatic, it looks like careful normalisation, and it silently shifts every
clinical timestamp by the browser's UTC offset. It was written once already. It will be
written again.

Like every guard in this directory: it scans the real tree, **and** it is proven to bite on
a planted snippet, because a guard nobody has watched fail is not a guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import core

_REPO_ROOT = Path(core.__file__).resolve().parents[1]
_STATIC = _REPO_ROOT / "api" / "static"
_TEMPLATES = _REPO_ROOT / "api" / "templates"

#: `new Date(...).toISOString()` in any spacing, and the `.toISOString()` of a variable
#: that was read out of a form field.
_UTC_ROUNDTRIP = re.compile(r"new\s+Date\s*\([^)]*\)\s*\.\s*toISOString\s*\(")
_BARE_TO_ISO = re.compile(r"\.toISOString\s*\(")


def _client_scripts() -> list[Path]:
    return sorted(_STATIC.glob("*.js"))


def _strip_line_comment(line: str) -> str:
    """Drop a trailing ``//`` comment.

    ★ Without this the guard fires on the **explanation of itself** — the comment in
    `reported-time.js` that says why `toISOString()` is wrong. A guard that flags prose is a
    guard people switch off, and the next real violation goes with it. Naive on strings
    containing ``//`` (a URL); there are none in these files, and a false *positive* here is
    loud rather than silent.
    """
    return line.split("//", 1)[0]


def _violations(source: str) -> list[str]:
    return [
        line.strip()
        for raw in source.splitlines()
        for line in [_strip_line_comment(raw)]
        if _UTC_ROUNDTRIP.search(line) or _BARE_TO_ISO.search(line)
    ]


@pytest.mark.parametrize("script", _client_scripts(), ids=lambda p: p.name)
def test_no_utc_roundtrip_of_a_reported_time(script: Path) -> None:
    """★ The real tree stays clean.

    A `datetime-local` input's `.value` is **already** a local wall-clock ISO string
    (`2026-07-30T11:20`). Round-tripping it through `Date` converts it to an instant and
    loses the only thing the server needed. The conversion is pure loss.
    """
    found = _violations(script.read_text(encoding="utf-8"))
    assert not found, (
        f"{script.name} converts a value through UTC: {found}. A reported clinical time is "
        "a naive local wall-clock string; see S-1018 and ADR-8."
    )


def test_the_guard_bites_on_the_line_that_caused_this() -> None:
    """The exact line from `app.js`, before the fix."""
    planted = 'var reported = new Date(iso).toISOString();'
    assert _violations(planted), "the guard does not fire on the line it exists to catch"


def test_the_guard_bites_on_the_indirect_form() -> None:
    """★ The obvious way around it: build the Date first, convert on the next line.

    A guard that only matches `new Date(x).toISOString()` as one expression is defeated by
    a newline, and the person defeating it will not know they did.
    """
    planted = "var d = new Date(input.value);\nbody.post_bg_time = d.toISOString();"
    assert _violations(planted), "splitting the expression across lines must not evade it"


def test_the_guard_does_not_fire_on_the_correct_form() -> None:
    """The fix must be *allowed* — a guard that also rejects the right answer is worse
    than no guard, because it teaches people to disable it."""
    clean = 'body.post_bg_time = localIso(timeInput);  // "2026-07-30T11:20"'
    assert not _violations(clean)


def test_every_reported_time_field_in_a_template_is_datetime_local() -> None:
    """★ The other half: the input type is what makes a local wall-clock value available.

    A `type="text"` field would put free text in the same place and the naive-vs-aware
    question would be replaced by a parsing question, which is not an improvement.
    """
    offenders: list[str] = []
    for template in sorted(_TEMPLATES.glob("*.html")):
        source = template.read_text(encoding="utf-8")
        for match in re.finditer(r"<input[^>]*>", source, flags=re.S):
            tag = match.group(0)
            named_time = re.search(r'name="(datetime|post_bg_time|bg_after_time)"', tag)
            if named_time and 'type="datetime-local"' not in tag:
                offenders.append(f"{template.name}: {named_time.group(1)}")
    assert not offenders, f"reported time fields that are not datetime-local: {offenders}"
