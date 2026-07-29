"""S-1001a — the operator report card's view model (SDET, written RED first).

`05b §7.2` asks for every metric three ways together — value, plain language, technical
term — plus a verdict badge. The operator may be a family member, not a statistician: a
bare "Brier 0.13" tells them nothing, and hiding the number tells a clinician nothing.

**The rule these tests defend (DL-042).** Only four measures have a bar defined anywhere:
hypo recall (vs the clinical baseline — the Gate-1 condition), false alarms (vs
`target_far`), the calibration verdict (the operator-approved DL-042 rule), and
`β_insulin < 0` (INV-8). For everything else there is **no absolute standard**, so badges
are **relative to the baseline** — the arithmetic she would use with no model at all.

The temptation here is a reassuring default: a badge that renders neutral-positive when the
data is missing, or a row quietly dropped when it cannot be computed. On the screen where a
human decides whether to put someone who cannot feel a low in front of a model, an invented
`[Good]` reads as authority it has not earned.

RED: `api.presenters` does not exist.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from api.presenters import BaselineComparison, MetricRow, Verdict, shadow_rows
from models.metrics import hypo_calibration
from models.shadow import build_shadow_report

_STATES = (1, 2, 3, 4, 5)


def _report(*, beta_insulin: float = 0.42, clarke_danger: bool = False):  # type: ignore[no-untyped-def]
    """A small but real ShadowReport built through the actual S-805 code path."""
    rng = np.random.default_rng(7)
    n = 60
    is_hypo = np.array([1] * 20 + [0] * 40)
    score = np.where(is_hypo == 1, rng.uniform(0.5, 0.9, n), rng.uniform(0.0, 0.4, n))
    pred_states = np.where(is_hypo == 1, 2, 3)
    actual_states = np.where(is_hypo == 1, 2, 3)
    reference_bg = np.where(is_hypo == 1, 67.0, 130.0)
    # A small non-zero miss on purpose: with MAE exactly 0 no baseline can be strictly
    # worse, and the lower-is-better direction test would silently degrade to SAME.
    predicted_bg = reference_bg + 8.0
    if clarke_danger:
        # a genuine "failed to detect a low": truth 50, predicted 120 → Clarke D
        reference_bg = reference_bg.copy()
        predicted_bg = predicted_bg.copy()
        reference_bg[0], predicted_bg[0] = 50.0, 120.0
    return build_shadow_report(
        hypo_score=score, is_hypo=is_hypo, predicted_bg=predicted_bg,
        reference_bg=reference_bg, pred_states=pred_states, actual_states=actual_states,
        unconstrained_beta_insulin=beta_insulin,
    )


def _rows(**kw: object) -> dict[str, MetricRow]:
    kwargs: dict[str, object] = dict(
        report=_report(), baseline=BaselineComparison(), calibration=None
    )
    kwargs.update(kw)
    return {r.key: r for r in shadow_rows(**kwargs)}  # type: ignore[arg-type]


# --- ★ never a verdict it cannot justify -------------------------------------


def test_no_baseline_figure_means_no_verdict_at_all() -> None:
    """★ THE RULE (DL-042). With nothing to compare against, the row shows the number and
    what it means — and **no badge**. Not a neutral-looking one, not a hopeful one. An
    invented verdict on this screen is indistinguishable from a real one."""
    rows = _rows(baseline=BaselineComparison())  # every field None
    for key in ("brier", "mae", "off_by_one", "severe_error"):
        row = rows[key]
        assert row.verdict is Verdict.NOT_COMPARED, f"{key} invented a verdict"
        assert row.verdict_label == "", f"{key} rendered a badge with nothing behind it"
        assert row.comparison is None
        # ...but the row is still THERE, with its number and its meaning
        assert row.value and row.plain and row.technical


def test_a_row_never_borrows_a_neighbours_comparison() -> None:
    """Supplying one baseline figure must not give the others a verdict."""
    rows = _rows(baseline=BaselineComparison(mae_mgdl=40.0))
    assert rows["mae"].verdict is not Verdict.NOT_COMPARED
    assert rows["brier"].verdict is Verdict.NOT_COMPARED
    assert rows["off_by_one"].verdict is Verdict.NOT_COMPARED


# --- ★ direction ---------------------------------------------------------------


def test_higher_is_better_and_lower_is_better_rows_go_opposite_ways() -> None:
    """★ Recall: higher is better. MAE: lower is better. A single inverted comparison
    would flip every badge on the page, and the page would still render perfectly."""
    report = _report()
    worse_recall_baseline = report.hypo_recall.recall - 0.10
    worse_mae_baseline = report.mae_mgdl + 10.0        # baseline misses by MORE
    rows = _rows(
        report=report,
        baseline=BaselineComparison(
            hypo_recall=worse_recall_baseline, mae_mgdl=worse_mae_baseline
        ),
    )
    assert rows["hypo_recall"].verdict is Verdict.BETTER, "beating baseline recall is BETTER"
    assert rows["mae"].verdict is Verdict.BETTER, "a SMALLER miss than baseline is BETTER"

    flipped = _rows(
        report=report,
        baseline=BaselineComparison(
            hypo_recall=report.hypo_recall.recall + 0.10,
            mae_mgdl=max(report.mae_mgdl - 10.0, 0.0),
        ),
    )
    assert flipped["hypo_recall"].verdict is Verdict.WORSE
    assert flipped["mae"].verdict is Verdict.WORSE


def test_comparison_is_exact_with_no_invented_tolerance() -> None:
    """★ A hair better is BETTER, not "about the same". Introducing a tolerance here would
    be a second, looser notion of "beats the baseline" sitting beside the strict one the
    gate uses — and the looser one would be the one the operator reads."""
    report = _report()
    rows = _rows(
        report=report,
        baseline=BaselineComparison(hypo_recall=report.hypo_recall.recall - 1e-4),
    )
    assert rows["hypo_recall"].verdict is Verdict.BETTER

    same = _rows(
        report=report, baseline=BaselineComparison(hypo_recall=report.hypo_recall.recall)
    )
    assert same["hypo_recall"].verdict is Verdict.SAME


# --- ★ the two alarms ----------------------------------------------------------


def test_negative_beta_insulin_is_an_alarm_and_is_always_present() -> None:
    """★ INV-8 on the same screen, never buried in a log (05b §7.2). Present as a row even
    when it is fine, so its absence can never be mistaken for its being clear."""
    confounded = _rows(report=_report(beta_insulin=-0.31))
    assert confounded["beta_insulin"].verdict is Verdict.ALARM
    assert confounded["beta_insulin"].verdict_label != ""

    healthy = _rows(report=_report(beta_insulin=0.42))
    assert "beta_insulin" in healthy, "the row must exist even when there is no alarm"
    assert healthy["beta_insulin"].verdict is Verdict.OK


def test_any_clarke_danger_zone_is_an_alarm_regardless_of_baseline() -> None:
    """★ The one sanctioned ABSOLUTE verdict. A Clarke D is "failed to detect a low" — it
    is dangerous by the measure's own construction, not by a cut-off anyone here picked.
    So it alarms even if the baseline made more of them."""
    rows = _rows(
        report=_report(clarke_danger=True),
        baseline=BaselineComparison(clarke_danger=99),  # baseline is far worse
    )
    assert rows["clarke_danger"].verdict is Verdict.ALARM

    clean = _rows(report=_report(clarke_danger=False), baseline=BaselineComparison())
    assert clean["clarke_danger"].verdict is not Verdict.ALARM


# --- calibration (S-1012) ------------------------------------------------------


def test_calibration_row_carries_the_s1012_verdict_and_its_reason() -> None:
    dishonest = hypo_calibration(
        np.array([0.20] * 40), np.array([1] * 16 + [0] * 24)  # claims 20%, 40% happen
    )
    assert dishonest.is_acceptable is False
    rows = _rows(calibration=dishonest)
    assert rows["calibration"].verdict is Verdict.ALARM
    assert dishonest.reason in rows["calibration"].plain

    honest = hypo_calibration(np.array([0.20] * 40), np.array([1] * 8 + [0] * 32))
    assert honest.is_acceptable is True
    assert _rows(calibration=honest)["calibration"].verdict is Verdict.OK


def test_calibration_row_without_a_verdict_is_not_compared() -> None:
    """No calibration computed yet ⇒ shown as not assessed, never as passing."""
    row = _rows(calibration=None)["calibration"]
    assert row.verdict is Verdict.NOT_COMPARED
    assert row.verdict_label == ""


# --- every row is complete, and honest about what it is ------------------------


def test_every_row_shows_all_three_of_value_plain_and_technical() -> None:
    """05b §7.2: not one INSTEAD of another. A bare number tells a family member nothing;
    dropping it tells a clinician nothing."""
    for key, row in _rows().items():
        assert row.heading.strip(), f"{key}: no heading"
        assert row.value.strip(), f"{key}: no value"
        assert row.plain.strip(), f"{key}: no plain-language interpretation"
        assert row.technical.strip(), f"{key}: no technical term"


def test_hypo_recall_is_the_first_row() -> None:
    """The headline metric (07 §9). It is what "good" means for someone who cannot feel a
    low, and it must not be the fourth thing on the page."""
    rows = shadow_rows(report=_report(), baseline=BaselineComparison(), calibration=None)
    assert rows[0].key == "hypo_recall"


def test_the_word_accuracy_appears_in_no_field_of_any_row() -> None:
    """★ Plain accuracy is forbidden (07 §9) — on an imbalanced 5-class problem it rewards
    a model that never catches a low. It must not leak in as *wording* either."""
    for row in _rows(baseline=BaselineComparison(hypo_recall=0.4, mae_mgdl=50.0)).values():
        for field in dataclasses.fields(row):
            value = getattr(row, field.name)
            if isinstance(value, str):
                assert "accuracy" not in value.lower(), f"{row.key}.{field.name}"


# --- ★ the pre-data state ------------------------------------------------------


def test_no_report_yields_an_empty_state_not_an_exception() -> None:
    """★ TODAY'S ACTUAL STATE: no model has been fitted and nothing has been predicted.
    The most likely thing to crash, and the state the operator will see for months."""
    rows = shadow_rows(report=None, baseline=BaselineComparison(), calibration=None)
    assert rows == ()


def test_no_report_never_implies_a_fitted_model() -> None:
    """Belt and braces: an empty report must not produce rows with zeroed numbers, which
    would read as "a model that scores 0" rather than "no model"."""
    for row in shadow_rows(report=None, baseline=BaselineComparison(), calibration=None):
        pytest.fail(f"row {row.key!r} rendered with no report")
