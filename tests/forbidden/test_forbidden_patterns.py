"""S-105 [SAFETY] — forbidden-pattern guards (09-test-plan.md §6).

Cheap AST guards that fire on violation. Each guard both (a) scans the real
source tree, which must stay clean, and (b) is proven to bite by feeding it a
deliberately-planted violation snippet. **Do not delete these** — each is the
guardrail for a specific silent-corruption refactor.

The `datetime.now()` → clinical-timestamp guard (pattern 7) is the most
important: it corrupts the two most predictive features with no error and no way
to detect it afterwards (ADR-8).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import core

_REPO_ROOT = Path(core.__file__).resolve().parents[1]
_SOURCE_PACKAGES = ["core", "features", "models", "prescribe", "data", "api", "cli"]

# Clinical timestamp targets that must NEVER be populated by now(). `logged_at`
# is deliberately absent — it IS the system clock (ADR-8).
_CLINICAL_TS = {
    "datetime", "pre_bg_time", "post_bg_time", "bolus_time", "bolus_datetime", "time_taken",
}
# User-input sources; assigning IOB from any of these is forbidden (IOB is derived).
_INPUT_SOURCES = {"request", "req", "form", "payload", "body", "user_input", "params", "args"}
# Known/expected names for the shared state-binning function. Extend at S-404/S-501.
_BINNER_NAMES = {
    "bin_state", "state_bin", "to_state", "bin_bg", "bin_to_state",
    "glycaemic_state", "state_for_bg", "bg_to_state",
}


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for pkg in _SOURCE_PACKAGES:
        pkg_dir = _REPO_ROOT / pkg
        if pkg_dir.is_dir():
            files.extend(pkg_dir.rglob("*.py"))
    return files


# --- shared AST helpers ----------------------------------------------------


def _is_now_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in {"now", "utcnow", "today"}:
        return True
    return isinstance(func, ast.Name) and func.id in {"now", "utcnow"}


def _is_fit_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "fit"
    )


def _is_range_1_6(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not (isinstance(node.func, ast.Name) and node.func.id == "range"):
        return False
    args = [a for a in node.args if isinstance(a, ast.Constant)]
    values = [a.value for a in args]
    return values == [1, 6] or values == [1, 6, 1]


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_target_names(elt))
        return names
    return []


def _references_input_source(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in _INPUT_SOURCES:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in _INPUT_SOURCES:
            return True
    return False


# --- detectors: each returns a list of human-readable findings -------------


def detect_multi_class(tree: ast.AST) -> list[str]:
    return [
        "multi_class keyword"
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword) and node.arg == "multi_class"
    ]


def detect_per_state_fit_loop(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.For)
            and _is_range_1_6(node.iter)
            and any(_is_fit_call(c) for c in ast.walk(node))
        ):
            hits.append("per-state fit loop over range(1, 6)")
    return hits


def detect_shuffle_true(tree: ast.AST) -> list[str]:
    return [
        "shuffle=True"
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword)
        and node.arg == "shuffle"
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
    ]


def detect_accuracy_score(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "accuracy_score":
            hits.append("accuracy_score reference")
        elif isinstance(node, ast.Attribute) and node.attr == "accuracy_score":
            hits.append("accuracy_score attribute")
        elif isinstance(node, ast.ImportFrom):
            hits.extend(
                "accuracy_score import" for a in node.names if a.name == "accuracy_score"
            )
    return hits


def detect_assert(tree: ast.AST) -> list[str]:
    return ["assert statement" for node in ast.walk(tree) if isinstance(node, ast.Assert)]


def detect_manual_iob(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        names = [n for t in targets for n in _target_names(t)]
        if any("iob" in n.lower() for n in names) and _references_input_source(value):
            hits.append("IOB assigned from user input")
    return hits


def detect_datetime_now_on_clinical_ts(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        # Assignment: <clinical ts> = now()
        if isinstance(node, ast.Assign) and _is_now_call(node.value):
            names = [n for t in node.targets for n in _target_names(t)]
            hits.extend(f"{n} = now()" for n in names if n in _CLINICAL_TS)
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _is_now_call(node.value)
        ):
            hits.extend(n for n in _target_names(node.target) if n in _CLINICAL_TS)
        # Keyword call: Model(datetime=now())
        elif isinstance(node, ast.Call):
            hits.extend(
                f"{kw.arg}=now()"
                for kw in node.keywords
                if kw.arg in _CLINICAL_TS and _is_now_call(kw.value)
            )
    return hits


def detect_pre_bg_to_binner(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in _BINNER_NAMES:
            continue
        arg_names = [a.id for a in node.args if isinstance(a, ast.Name)]
        arg_names += [kw.value.id for kw in node.keywords if isinstance(kw.value, ast.Name)]
        if "pre_bg" in arg_names:
            hits.append(f"pre_bg passed to binner {node.func.id}()")
    return hits


# Registry: (id, detector, violating snippet, filename-context).
_PATTERNS: list[tuple[str, object, str]] = [
    ("multi_class", detect_multi_class, "m = LogisticRegression(multi_class='multinomial')\n"),
    (
        "per_state_fit_loop",
        detect_per_state_fit_loop,
        "for state in range(1, 6):\n    model.fit(X[state], y[state])\n",
    ),
    ("shuffle_true", detect_shuffle_true, "train_test_split(X, y, shuffle=True)\n"),
    ("accuracy_score", detect_accuracy_score, "from sklearn.metrics import accuracy_score\n"),
    ("assert_in_safety", detect_assert, "def inv(x):\n    assert x > 0\n"),
    ("manual_iob", detect_manual_iob, "iob = request.form['iob']\n"),
    (
        "datetime_now_clinical_ts",
        detect_datetime_now_on_clinical_ts,
        "meal.datetime = datetime.now()\n",
    ),
    ("pre_bg_to_binner", detect_pre_bg_to_binner, "state = bin_state(pre_bg)\n"),
]

_ALL_DETECTORS = [(pid, det) for pid, det, _ in _PATTERNS]


def _files_for_pattern(pid: str) -> list[Path]:
    """Scope. `assert` is forbidden only in core/safety.py (asserts are fine
    elsewhere); every other pattern is forbidden across the whole source tree."""
    if pid == "assert_in_safety":
        return [_REPO_ROOT / "core" / "safety.py"]
    return _iter_source_files()


@pytest.mark.parametrize("pid,detector", _ALL_DETECTORS)
def test_source_tree_is_free_of_pattern(pid: str, detector: object) -> None:
    """The in-scope source files are clean of this forbidden pattern."""
    offenders: list[str] = []
    for path in _files_for_pattern(pid):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        findings = detector(tree)  # type: ignore[operator]
        offenders += [f"{path.relative_to(_REPO_ROOT)}: {f}" for f in findings]
    assert not offenders, f"forbidden pattern '{pid}' present: {offenders}"


@pytest.mark.parametrize("pid,detector,snippet", _PATTERNS)
def test_detector_fires_on_violation(pid: str, detector: object, snippet: str) -> None:
    """The guard actually bites when the pattern is deliberately introduced."""
    tree = ast.parse(snippet)
    findings = detector(tree)  # type: ignore[operator]
    assert findings, f"detector for '{pid}' did not fire on a deliberate violation"


def test_datetime_now_clinical_ts_is_the_most_important_guard() -> None:
    """Fires for each clinical timestamp target populated by now()."""
    for target in ("datetime", "pre_bg_time", "post_bg_time", "bolus_time"):
        tree = ast.parse(f"obj.{target} = datetime.now()\n")
        assert detect_datetime_now_on_clinical_ts(tree), f"missed now() on {target}"
    # keyword-argument form is caught too
    assert detect_datetime_now_on_clinical_ts(ast.parse("MealEvent(pre_bg_time=datetime.now())\n"))


def test_logged_at_now_is_not_flagged() -> None:
    """ADR-8 negative control: logged_at IS the system clock — now() is correct."""
    for snippet in (
        "row.logged_at = datetime.now()\n",
        "MealEvent(logged_at=datetime.now(), datetime=reported_dt)\n",
        "created_at = datetime.utcnow()\n",
    ):
        assert not detect_datetime_now_on_clinical_ts(ast.parse(snippet)), snippet
