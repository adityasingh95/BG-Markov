"""S-104 [SAFETY] — static guarantees that keep the invariants un-weakenable.

- No ``assert`` in ``core/safety.py`` (asserts vanish under ``python -O``).
- Zero internal project imports (ADR-6) — no import cycle can weaken it.
- ``SafetyViolation`` / ``GateNotPassed`` / ``inv<n>`` defined ONLY here — no
  second copy to drift.
- A negative case still raises under ``python -O`` — proving the mechanism is a
  raise, not an assert.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from core import safety

_SAFETY_PATH = Path(safety.__file__).resolve()
_REPO_ROOT = _SAFETY_PATH.parents[1]

# Project top-level packages that core/safety.py must never import (ADR-6).
_PROJECT_PACKAGES = {"core", "features", "models", "prescribe", "data", "api", "cli", "tests"}
# Source packages to scan for re-implementations (never the tests themselves).
_SOURCE_PACKAGES = ["core", "features", "models", "prescribe", "data", "api", "cli"]


def _safety_ast() -> ast.Module:
    return ast.parse(_SAFETY_PATH.read_text(encoding="utf-8"))


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for pkg in _SOURCE_PACKAGES:
        pkg_dir = _REPO_ROOT / pkg
        if pkg_dir.is_dir():
            files.extend(pkg_dir.rglob("*.py"))
    return files


def test_no_assert_in_safety_module() -> None:
    """Static: not a single `assert` — it would be stripped under python -O."""
    asserts = [n for n in ast.walk(_safety_ast()) if isinstance(n, ast.Assert)]
    assert not asserts, f"core/safety.py contains {len(asserts)} assert(s)"


def test_safety_module_has_zero_internal_imports() -> None:
    """ADR-6: imports only stdlib/typing; nothing from the project."""
    offenders: list[str] = []
    for node in ast.walk(_safety_ast()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _PROJECT_PACKAGES:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level > 0 or root in _PROJECT_PACKAGES:
                offenders.append(node.module or f"(relative level {node.level})")
    assert not offenders, f"core/safety.py imports internal modules: {offenders}"


def test_safetyviolation_defined_only_in_safety_module() -> None:
    """The exception types have exactly one definition — no drifting copy."""
    for exc_name in ("SafetyViolation", "GateNotPassed"):
        definers = [
            f
            for f in _iter_source_files()
            if f != _SAFETY_PATH
            and any(
                isinstance(n, ast.ClassDef) and n.name == exc_name
                for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
            )
        ]
        assert not definers, f"{exc_name} re-defined outside core/safety.py: {definers}"


def _is_invariant_name(name: str) -> bool:
    """True for `inv<digit>...` — the invariant-function naming convention."""
    return len(name) > 3 and name.startswith("inv") and name[3].isdigit()


def test_no_invariant_reimplemented_outside_safety_module() -> None:
    """No `inv<n>...` function lives anywhere but core/safety.py (rule 1)."""
    offenders: list[str] = []
    for f in _iter_source_files():
        if f == _SAFETY_PATH:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and _is_invariant_name(n.name):
                offenders.append(f"{f.name}:{n.name}")
    assert not offenders, f"invariant re-implemented outside core/safety.py: {offenders}"


def test_negative_case_still_raises_under_dash_O() -> None:
    """python -O strips asserts. A negative invariant case must STILL raise —
    proving the mechanism is a raise, not an assert."""
    code = (
        "from core import safety\n"
        "try:\n"
        "    safety.inv6_predicted_bg_in_range(999.0)\n"
        "except safety.SafetyViolation:\n"
        "    print('RAISED'); raise SystemExit(0)\n"
        "raise SystemExit('NO RAISE UNDER -O')\n"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, f"invariant did not raise under -O: {result.stderr}"
    assert "RAISED" in result.stdout
