"""S-1024 (SDET) — `dev.sh` runs on the operator's laptop, not just on CI. RED first.

The container this was written in has **bash 5.2**, GNU coreutils and GNU sed. A stock macOS
laptop has **bash 3.2** (frozen in 2007 for licensing reasons), BSD sed and BSD coreutils —
and `/usr/bin/env bash` finds 3.2 first unless the operator has installed a newer one.

★ The pattern is the one that already bit once, in the same file: `dev.sh` shelled out to the
`sqlite3` CLI, which does not exist everywhere, and the operator's **first command** died with
a wall of SQL. Assuming the local shell is the shell everyone has is the same mistake with a
different binary.

These are cheap greps. The real proof is running it on a Mac, which nobody here can do — so
each guard names the construct AND why it breaks, rather than asserting a style rule.
"""

from __future__ import annotations

import pathlib
import re

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev.sh"


def _code_lines() -> list[str]:
    """Script lines with comments and blanks removed."""
    return [
        line
        for raw in _SCRIPT.read_text(encoding="utf-8").splitlines()
        for line in [raw.strip()]
        if line and not line.startswith("#")
    ]


def test_it_does_not_shell_out_to_sqlite3() -> None:
    """The one that already broke. Kept as a permanent guard (see `migrate_db.py`)."""
    offenders = [line for line in _code_lines() if "sqlite3 " in line]
    assert not offenders, f"dev.sh shells out to the sqlite3 CLI: {offenders}"


@pytest.mark.parametrize(
    ("construct", "pattern", "why"),
    [
        (
            "empty array under set -u",
            r"\blocal\s+\w+=\(\)",
            "bash 3.2 treats ${arr[@]} on an EMPTY array as an unbound variable under "
            "`set -u`, so `dev.sh reset` would abort on a laptop with nothing to delete — "
            "the exact case where it should say 'nothing to delete'",
        ),
        (
            "mapfile / readarray",
            r"\b(mapfile|readarray)\b",
            "bash 4 only; absent on macOS",
        ),
        (
            "associative arrays",
            r"\bdeclare\s+-A\b",
            "bash 4 only; absent on macOS",
        ),
        (
            "case conversion ${v^^} / ${v,,}",
            r"\$\{\w+(\^\^|,,)",
            "bash 4 only; absent on macOS",
        ),
        (
            "&>> redirection",
            r"&>>",
            "bash 4 only; absent on macOS",
        ),
        (
            "GNU sed -i without a suffix",
            r"sed\s+-i\s+(?!['\"])",
            "BSD sed requires an explicit backup suffix, so `sed -i` silently means "
            "something different on macOS",
        ),
    ],
)
def test_no_construct_that_breaks_on_a_stock_mac(
    construct: str, pattern: str, why: str
) -> None:
    rx = re.compile(pattern)
    offenders = [line for line in _code_lines() if rx.search(line)]
    assert not offenders, f"{construct}: {why}\n  {offenders}"


def test_it_offers_a_preflight_check() -> None:
    """★ `doctor` exists so a missing prerequisite is a sentence, not a traceback.

    Everything else in this file is a grep. This one is the actual mitigation: nobody here
    can run a Mac, so the honest fallback is a command that tells the operator what is wrong
    on *his* machine, in his terms.
    """
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "cmd_doctor" in text, "dev.sh has no `doctor` preflight command"
    assert "doctor)" in text, "`doctor` is defined but not reachable from the command switch"
