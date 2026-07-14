"""S-101 toolchain gate tests (SDET, written first).

The AC for S-101 is that ``ruff``, ``mypy --strict`` and ``pytest`` are wired
up and *clean*, and that CI fails on a deliberate lint error and on a
deliberate type error.

Every forbidden-pattern and safety test downstream (S-104, S-105, and every
``[SAFETY]`` story) is worthless if these gates do not actually bite. So the
honest test here is the adversarial one: introduce the defect the gate exists
to catch and assert the gate reports failure.

These tests shell out to the real tools so they exercise the *configured*
toolchain, not a stubbed approximation.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tool(name: str) -> str:
    """Resolve a toolchain executable or fail the test loudly if it is absent.

    A missing gate is not a passing gate: if ``ruff`` or ``mypy`` cannot be
    found the build must be red, not silently green.
    """
    path = shutil.which(name)
    assert path is not None, (
        f"{name!r} is required for the S-101 toolchain gate but was not found "
        "on PATH; the lint/type gates cannot be enforced without it."
    )
    return path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# --- The gate must BITE on a deliberate defect -----------------------------


def test_ruff_fails_on_deliberate_lint_error(tmp_path: Path) -> None:
    """A file with an unused import (F401) must make ``ruff check`` non-zero."""
    bad = tmp_path / "bad_lint.py"
    bad.write_text("import os\n")  # F401: imported but unused

    result = _run([_tool("ruff"), "check", "--isolated", "--select", "F", str(bad)])

    assert result.returncode != 0, (
        "ruff must fail on an unused import; a lint gate that passes dirty code "
        "cannot enforce the forbidden-pattern suite.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_mypy_fails_on_deliberate_type_error(tmp_path: Path) -> None:
    """A file with a type error must make ``mypy --strict`` non-zero."""
    bad = tmp_path / "bad_type.py"
    bad.write_text(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n"
        'result: int = add("not", "ints")\n'
    )

    result = _run([_tool("mypy"), "--strict", "--no-incremental", str(bad)])

    assert result.returncode != 0, (
        "mypy --strict must fail on a type error.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# --- The clean skeleton must PASS both gates -------------------------------


def test_ruff_clean_on_project() -> None:
    # --no-cache so this matches CI's fresh checkout exactly. A cached "clean"
    # once let non-canonical import ordering pass locally while CI (no cache)
    # failed the same commit; a gate that can be masked by a stale cache is not
    # a gate.
    result = _run([_tool("ruff"), "check", "--no-cache", "."])
    assert result.returncode == 0, (
        "The committed project must be ruff-clean (fresh, no cache).\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_mypy_strict_clean_on_core() -> None:
    # --no-incremental for the same reason: match CI, never a warm-cache pass.
    result = _run([_tool("mypy"), "--strict", "--no-incremental", "core"])
    assert result.returncode == 0, (
        "core/ must be mypy --strict clean.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
