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


_ENTRY_SCRIPTS = ("scripts/dev.sh", "start.sh", "bootstrap.sh")


@pytest.mark.parametrize("script", _ENTRY_SCRIPTS)
def test_no_hard_coded_venv_bin_directory(script: str) -> None:
    """★ A venv puts its executables in `bin` on POSIX and **`Scripts` on Windows** — which
    includes Git Bash, a POSIX shell driving a Windows Python.

    A hard-coded `.venv/bin` is the single thing that stops these scripts working on the
    operator's laptop, and it fails as `No such file or directory` for `activate` — which
    reads as a broken install rather than a wrong path.
    """
    path = pathlib.Path(__file__).resolve().parents[2] / script
    offenders = [
        line.strip()
        for raw in path.read_text(encoding="utf-8").splitlines()
        for line in [raw.strip()]
        if ".venv/bin" in line and not line.startswith("#")
    ]
    assert not offenders, f"{script} hard-codes .venv/bin: {offenders}"


def test_database_paths_are_relative() -> None:
    """★ Under Git Bash, `pwd` is `/c/Users/...`.

    Python's sqlite3 driver does not resolve that as a Windows path, so an absolute
    `sqlite:///${ROOT}/bgapp.db` would silently create or look for the database somewhere
    else — the worst kind of wrong, because the app still starts.
    """
    text = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev.sh").read_text()
    offenders = [
        line.strip()
        for raw in text.splitlines()
        for line in [raw.strip()]
        if not line.startswith("#") and "${ROOT}" in line and ".db" in line
    ]
    assert not offenders, f"absolute database paths: {offenders}"


def test_python_is_discovered_not_assumed() -> None:
    """`python3.12` exists on Linux, often not on macOS, and essentially never on Windows —
    where it is `python` or the `py -3.12` launcher."""
    text = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev.sh").read_text()
    assert "find_python" in text, "dev.sh assumes an interpreter name instead of finding one"
    for candidate in ("python3.12", "python3", "python", "py -3.12"):
        assert candidate in text, f"find_python does not try {candidate!r}"


def test_it_offers_a_preflight_check() -> None:
    """★ `doctor` exists so a missing prerequisite is a sentence, not a traceback.

    Everything else in this file is a grep. This one is the actual mitigation: nobody here
    can run a Mac, so the honest fallback is a command that tells the operator what is wrong
    on *his* machine, in his terms.
    """
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "cmd_doctor" in text, "dev.sh has no `doctor` preflight command"
    assert "doctor)" in text, "`doctor` is defined but not reachable from the command switch"
