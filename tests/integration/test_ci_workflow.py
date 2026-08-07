"""SDET — the CI workflow must fail *legibly*.

Runs #105 and #106 both stopped at 15m00s with conclusion `cancelled` and no retained logs.
`cancelled` is not something a failing test produces, and with no `timeout-minutes` set there
was nothing in the workflow to attribute it to. The build had no way to say why it stopped.

These are two lines of YAML, so the point is not the assertions — it is that a green build is
the only signal this project has that a **safety** test still passes, and one was silently red
for four days (the shadow clock, 2026-08-04 → 2026-08-05) because nobody was watching. A CI
run that stops without saying why is the same failure with extra steps.

★ **Parsed with the standard library, not PyYAML.** The first version opened with
`pytest.importorskip("yaml")`; PyYAML is not a dependency of this project, so all four tests
skipped — and a skipped test asserts nothing while reporting no failure. That is the precise
shape of the defect this file exists to guard against, reproduced inside the guard itself.
Adding a dependency to check two lines of a file we control is the wrong trade, so the
parsing is done here, deliberately narrow, and `test_the_parser_sees_what_is_actually_there`
keeps it honest.
"""

from __future__ import annotations

import pathlib
import re

_WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _job_names() -> list[str]:
    """Top-level keys under `jobs:` — two-space indented, and the only such block."""
    lines = _text().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "jobs:")
    except StopIteration:  # pragma: no cover - a workflow with no jobs is caught below
        return []
    names = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith(" "):
            break  # a new top-level key; the jobs block is over
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            names.append(match.group(1))
    return names


def _job_block(name: str) -> str:
    """Everything indented under one job."""
    lines = _text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"  {name}:")
    block = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line)
    return "\n".join(block)


def test_the_parser_sees_what_is_actually_there() -> None:
    """★ Guard on the guard.

    Every other test here rests on `_job_names()` finding the jobs. If a reformat broke the
    parser it would return an empty list, and *every* assertion below would pass vacuously —
    the same silent-green failure as the `importorskip` version. Pin the known job.
    """
    assert _WORKFLOW.exists(), "no CI workflow file"
    names = _job_names()
    assert names, "the parser found no jobs — it has stopped matching the file's shape"
    assert "quality" in names, f"expected a 'quality' job, found {names}"


def test_every_job_has_a_timeout() -> None:
    """★ Without this, a hung job runs to GitHub's 6-hour default.

    Six hours is indistinguishable from "CI is broken", and it burns the runner minutes the
    next push needs.
    """
    missing = [name for name in _job_names() if "timeout-minutes:" not in _job_block(name)]
    assert not missing, (
        f"jobs without `timeout-minutes`: {missing}. A hang then runs for six hours and "
        "reports as a mystery rather than as a timeout."
    )


def test_the_timeout_is_generous_but_finite() -> None:
    """A timeout tight enough to clip a slow-but-healthy run is worse than none: it teaches
    the reader that red means nothing. The suite takes about five minutes on CI; the ceiling
    is a hang detector, not a performance budget."""
    for name in _job_names():
        match = re.search(r"timeout-minutes:\s*(\d+)", _job_block(name))
        assert match, f"job {name!r} has no timeout-minutes"
        minutes = int(match.group(1))
        assert 10 <= minutes <= 60, (
            f"job {name!r} has timeout-minutes={minutes}; expected 10-60. Below 10 clips "
            "healthy runs; above 60 is not a hang detector."
        )


def test_superseded_runs_are_cancelled_deliberately() -> None:
    """★ So that a cancellation has a *known* cause.

    Without a concurrency group, every push leaves its predecessor running and two runs
    compete for runners. With one, a cancelled run is explained by the newer run that
    replaced it — exactly the attribution missing from #105 and #106.
    """
    text = _text()
    assert re.search(r"^concurrency:", text, re.MULTILINE), (
        "no `concurrency:` block — a cancelled run has no attributable cause"
    )
    assert "${{ github.ref }}" in text, (
        "the concurrency group is not per-ref, so a push to one branch would cancel "
        "another branch's run"
    )
    assert re.search(r"cancel-in-progress:\s*true", text), "cancel-in-progress is not enabled"


def test_ci_still_runs_the_gates_it_is_supposed_to() -> None:
    """Adding a timeout must not quietly drop a gate. Every command in the definition of
    done has to still be here."""
    text = _text()
    for gate in ("ruff check", "mypy --strict", "pytest", "--cov-fail-under=90"):
        assert gate in text, f"CI no longer runs {gate!r}"
