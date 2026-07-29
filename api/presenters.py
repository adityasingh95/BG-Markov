"""View-model construction for the operator report card (S-1001a, REQ-055, `05b §7.2`).

Pure. No DB, no I/O, no model fitting — domain objects in, rows out. Everything here is
about *how a number is shown*, and the rules it follows are safety rules, not styling.

**Every metric appears three ways together** — value, plain-language interpretation,
technical term. The operator may be a family member, not a statistician: a bare
"Brier 0.13" tells them nothing, and hiding the number tells a clinician nothing.

**Badges are RELATIVE, never absolute (DL-042).** Only four measures have a bar defined
anywhere in this project: hypo recall (vs the clinical baseline — the Gate-1 condition
itself), false alarms (vs ``target_far``), the calibration verdict (the operator-approved
DL-042 rule), and ``β_insulin < 0`` (INV-8). For everything else there is no absolute
standard, so a row is scored *Better / About the same / Worse* against the arithmetic she
would use with no model at all — and a row with nothing to compare against shows **no
badge**. An invented "Good" on this screen would read as authority it has not earned and
would be indistinguishable from the four that are real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from models.metrics import CalibrationVerdict
from models.shadow import ShadowReport
from prescribe.gates import GATE1_MIN_VALID_MEALS, SHADOW_MIN_DAYS, Gate1Status


class Verdict(StrEnum):
    """What a badge may say. `NOT_COMPARED` is a real answer, not a fallback."""

    BETTER = "better"
    SAME = "same"
    WORSE = "worse"
    NOT_COMPARED = "not_compared"
    OK = "ok"
    ALARM = "alarm"


_LABELS: dict[Verdict, str] = {
    Verdict.BETTER: "Better than the simple method",
    Verdict.SAME: "The same as the simple method",
    Verdict.WORSE: "Worse than the simple method",
    Verdict.NOT_COMPARED: "",  # ← deliberately empty: no bar, so no badge
    Verdict.OK: "No concern",
    Verdict.ALARM: "Needs attention",
}


@dataclass(frozen=True)
class MetricRow:
    key: str
    heading: str          # the plain-language question this row answers
    value: str            # the number, formatted
    plain: str            # what it means, in a sentence
    technical: str        # the technical term + the raw figure
    verdict: Verdict
    verdict_label: str
    comparison: str | None  # what it was compared against, if anything


@dataclass(frozen=True)
class BaselineComparison:
    """The same measures computed for the clinical baseline. **Every field optional** —
    a missing figure yields `NOT_COMPARED`, never a flattering default."""

    hypo_recall: float | None = None
    brier: float | None = None
    mae_mgdl: float | None = None
    off_by_one: float | None = None
    severe_error: float | None = None
    clarke_danger: int | None = None


def _compare(model: float, baseline: float | None, *, higher_is_better: bool) -> Verdict:
    """Exact, with **no invented tolerance**.

    ``BETTER`` iff strictly better, ``WORSE`` iff strictly worse, ``SAME`` only on exact
    equality — mirroring the Gate-1 rule (``model_hypo_recall > baseline_hypo_recall``,
    strict) rather than introducing a second, looser notion of "beats the baseline". A
    tolerance here would be the one the operator reads while the gate used the other.
    ``SAME`` is therefore rare; the raw numbers are on the row for anyone judging a margin.

    ``higher_is_better`` is an explicit argument rather than an inline condition because
    getting one row's direction backwards would invert its badge while the page rendered
    perfectly.
    """
    if baseline is None:
        return Verdict.NOT_COMPARED
    if model == baseline:
        return Verdict.SAME
    model_wins = model > baseline if higher_is_better else model < baseline
    return Verdict.BETTER if model_wins else Verdict.WORSE


def _row(
    key: str, heading: str, value: str, plain: str, technical: str,
    *, verdict: Verdict, comparison: str | None = None,
) -> MetricRow:
    return MetricRow(
        key=key, heading=heading, value=value, plain=plain, technical=technical,
        verdict=verdict, verdict_label=_LABELS[verdict],
        comparison=comparison if verdict is not Verdict.NOT_COMPARED else None,
    )


def shadow_rows(
    *,
    report: ShadowReport | None,
    baseline: BaselineComparison,
    calibration: CalibrationVerdict | None,
) -> tuple[MetricRow, ...]:
    """The report card's rows, most important first.

    ``report is None`` is a **first-class state**, not an error: there is no fitted model
    and nothing has been predicted, which is where this system will sit for months. It
    returns no rows at all rather than rows full of zeros — "a model that catches 0% of her
    lows" is a statement about a model that does not exist.
    """
    if report is None:
        return ()

    hr = report.hypo_recall
    clarke_danger = report.clarke.get("D", 0) + report.clarke.get("E", 0)
    base_danger = baseline.clarke_danger

    rows: list[MetricRow] = [
        # ── the headline (07 §9). What "good" means for someone who cannot feel a low.
        _row(
            "hypo_recall", "Catches her lows", f"{hr.recall:.0%}",
            f"Out of every 10 real lows, it warns about {round(hr.recall * 10)} in advance."
            + (
                f" The simple method warns about {round(baseline.hypo_recall * 10)}."
                if baseline.hypo_recall is not None else ""
            ),
            f"Hypo recall @ FAR ≤ {hr.target_far:.0%} = {hr.recall:.2f}",
            verdict=_compare(hr.recall, baseline.hypo_recall, higher_is_better=True),
            comparison=(
                None if baseline.hypo_recall is None
                else f"simple method: {baseline.hypo_recall:.0%}"
            ),
        ),
        # ── the cost of that recall. Its bar is target_far, already in the metric.
        _row(
            "false_alarms", "How often it cries wolf", f"{hr.far:.0%}",
            f"About {round(hr.far * 100)} in 100 safe meals get a warning that was not "
            "needed. A system that warns too often gets ignored.",
            f"False-alarm rate = {hr.far:.2f} (held to ≤ {hr.target_far:.0%})",
            verdict=Verdict.OK if hr.far <= hr.target_far else Verdict.ALARM,
            comparison=f"the limit it is held to: {hr.target_far:.0%}",
        ),
    ]

    # ── are the percentages honest? (S-1012 / DL-042 — an operator-approved rule)
    if calibration is None:
        rows.append(_row(
            "calibration", "Are its percentages honest?", "Not assessed",
            "Nobody has checked yet whether a \"1 in 3 chance\" really happens about a "
            "third of the time.",
            "Hypo-probability calibration (S-1012) — not computed",
            verdict=Verdict.NOT_COMPARED,
        ))
    else:
        rows.append(_row(
            "calibration", "Are its percentages honest?",
            "Yes" if calibration.is_acceptable else "No",
            f"When it puts a number on the risk, is the number true? {calibration.reason}",
            f"Hypo-probability calibration, {calibration.n_judged} risk band(s) judged "
            "(rule: DL-042)",
            verdict=Verdict.OK if calibration.is_acceptable else Verdict.ALARM,
            comparison="the agreed rule for honest percentages",
        ))

    rows += [
        _row(
            "brier", "How sharp its percentages are", f"{report.brier:.3f}",
            "Lower is better. It rewards being both right and confident, and punishes "
            "being confidently wrong.",
            f"Brier score = {report.brier:.3f}",
            verdict=_compare(report.brier, baseline.brier, higher_is_better=False),
            comparison=None if baseline.brier is None else f"simple method: {baseline.brier:.3f}",
        ),
        _row(
            "mae", "Typical miss", f"{report.mae_mgdl:.0f} mg/dL",
            "How far out it usually is on a glucose number. A fingerstick itself carries "
            "about 15% error, so some of this is the meter, not the model.",
            f"Mean absolute error = {report.mae_mgdl:.1f} mg/dL",
            verdict=_compare(report.mae_mgdl, baseline.mae_mgdl, higher_is_better=False),
            comparison=(
                None if baseline.mae_mgdl is None
                else f"simple method: {baseline.mae_mgdl:.0f} mg/dL"
            ),
        ),
        _row(
            "off_by_one", "How wrong when it's wrong — mildly", f"{report.off_by_one:.0%}",
            "It landed one band away — said \"in range\" when she was a bit high, or "
            "similar. Not dangerous, but it is being wrong.",
            f"Off-by-one state rate = {report.off_by_one:.2f}",
            verdict=_compare(report.off_by_one, baseline.off_by_one, higher_is_better=False),
            comparison=(
                None if baseline.off_by_one is None
                else f"simple method: {baseline.off_by_one:.0%}"
            ),
        ),
        _row(
            "severe_error", "How wrong when it's wrong — badly", f"{report.severe_error:.0%}",
            "It landed two or more bands away — the kind of miss where it said \"fine\" "
            "and she was low, or the reverse.",
            f"Severe state-error rate = {report.severe_error:.2f}",
            verdict=_compare(
                report.severe_error, baseline.severe_error, higher_is_better=False
            ),
            comparison=(
                None if baseline.severe_error is None
                else f"simple method: {baseline.severe_error:.0%}"
            ),
        ),
        # ── the one sanctioned ABSOLUTE verdict. A Clarke D is "failed to detect a low":
        #    dangerous by the measure's own construction, not by a cut-off anyone picked.
        #    So it alarms even where the baseline made more of them.
        _row(
            "clarke_danger", "Dangerous mistakes", str(clarke_danger),
            "Mistakes that would lead to the wrong action — missing a low, or treating a "
            "low as a high. Any of these is worth looking at individually."
            if clarke_danger else "None of its mistakes would have led to the wrong action.",
            f"Clarke error grid, zones D + E = {clarke_danger} of {report.n_predictions}",
            verdict=Verdict.ALARM if clarke_danger else Verdict.OK,
            comparison=None if base_danger is None else f"simple method: {base_danger}",
        ),
        # ── INV-8 on the same screen, never buried in a log (05b §7.2).
        _row(
            "beta_insulin", "Does it make medical sense?",
            "No" if report.beta_insulin_confounding else "Yes",
            "Left to itself the model concluded that insulin RAISES her blood sugar. That "
            "is confounding, not biology — she doses more when she is already high. The "
            "fitted model is constrained so it cannot act on it, but the data is telling "
            "you something."
            if report.beta_insulin_confounding
            else "The model's view of insulin points the right way: more insulin, lower "
                 "blood sugar.",
            f"Unconstrained β_insulin = {report.unconstrained_beta_insulin:+.2f} "
            "(constrained ≥ 0 by INV-8)",
            verdict=Verdict.ALARM if report.beta_insulin_confounding else Verdict.OK,
            comparison="insulin must never appear to raise blood sugar (INV-8)",
        ),
    ]
    return tuple(rows)


@dataclass(frozen=True)
class GateCondition:
    """One line of the Gate-1 checklist. All **five** of `03 §3`, always."""

    key: str
    met: bool
    plain: str
    detail: str


def gate1_conditions(status: Gate1Status, *, has_model: bool) -> tuple[GateCondition, ...]:
    """The five Gate-1 conditions, in plain language, read off a live ``Gate1Status``.

    All five are always returned, met or not. Showing only the unmet ones — or only the
    four that were implemented before S-1012 — would put a complete-looking checklist in
    front of the person deciding whether she may see the model.

    ``has_model`` is required because with no fitted model the recall figures are zeros,
    and *"catches 0% vs 0%"* is a claim about a model that does not exist. With no model
    the row says so instead.
    """
    remaining = max(SHADOW_MIN_DAYS - status.shadow_days, 0)
    return (
        GateCondition(
            "volume", status.meets_volume, "Enough meals logged",
            f"{status.valid_meals} of {GATE1_MIN_VALID_MEALS}",
        ),
        GateCondition(
            "beats_baseline", status.beats_baseline, "Better than the simple method",
            (
                f"catches {status.model_hypo_recall:.0%} vs "
                f"{status.baseline_hypo_recall:.0%}"
                if has_model else "nothing has been scored yet"
            ),
        ),
        GateCondition(
            "calibration", status.calibration_ok, "Its percentages are honest",
            "a \"1 in 3 chance\" really happens about a third of the time",
        ),
        GateCondition(
            "shadow", status.meets_shadow_period, "Watched quietly for 90 days",
            f"day {status.shadow_days} of {SHADOW_MIN_DAYS}"
            + (f" — {remaining} to go" if remaining else ""),
        ),
        GateCondition(
            "promoted", status.is_promoted, "You have turned it on, on purpose",
            # Name the audited action ("promoted") alongside the plain wording, so the
            # screen and the audit_log row a reader finds later use the same word.
            "not promoted yet — good numbers are not permission"
            if not status.is_promoted else "promoted by an operator",
        ),
    )
