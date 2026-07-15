---
name: audit
description: >-
  Run the Independent Auditor over the delivered work. Invoke when the user
  wants a fresh, independent review of the Glycaemic Prediction & Bolus system —
  auditing fitment to the product objective and the quality/honesty of the
  output, from primary sources, WITHOUT trusting the SDET/Dev/BA agents'
  self-reported status. Optional argument scopes the audit to a story (e.g.
  "S-203"), an epic (e.g. "EPIC 3"), a path, or "since <ref>"; with no argument
  it audits everything delivered so far. Triggers: "audit", "independent
  review", "sanity-check the work", "grade what's been done", "are they building
  the right thing".
---

# /audit — dispatch the Independent Auditor

This skill runs a **fourth role** that sits outside the SDET/Dev/BA build loop and
does not trust their self-reported status. It exists because the most likely
failure of this project is silent: a model that looks good on retrospective data,
gets trusted, and is quietly wrong about a low. The auditor's job is to find where
that failure could still hide.

## What to do

1. **Determine scope** from the argument (`$ARGUMENTS`):
   - a story id (`S-203`), an epic (`EPIC 3`), a path (`core/safety.py`), or
     `since <git-ref>` → audit that.
   - empty → audit everything delivered so far. Do **not** derive "what's
     delivered" from the backlog checkboxes; derive it from `git log` and the
     file tree.

2. **Dispatch the `independent-auditor` subagent** (via the Agent tool,
   `subagent_type: "independent-auditor"`) in a **fresh context** so it genuinely
   does not carry the build session's assumptions. Pass it a prompt like:

   > Audit scope: `<scope>`. Follow your charter. Verify from primary sources
   > (spec pack for intent; code + tests + git history + the running toolchain
   > for reality) — treat every story/traceability/decision-log claim as an
   > unverified hypothesis. Produce BOTH output files per your charter — the
   > evidence report (`audits/AUDIT-…`) and the remediation brief for the build
   > agents (`audits/HANDOFF-…`) — and return both paths plus the Verdict block.

   Run it synchronously (`run_in_background: false`) — the user is waiting for the
   verdict.

3. **Relay the result to the user.** The subagent's files are not shown to the
   user automatically. When it returns, surface: the **overall verdict**, the
   **one-question answer** (could a silently-wrong-about-a-low defect survive?),
   the **blocker/major/minor finding counts**, the **top 1–3 findings**, and the
   **paths to both files** — the evidence report AND the remediation brief
   (`HANDOFF-…`), noting that the brief is the one to hand to the SDET/Dev/BA
   agents. Keep it tight; the detail lives in the files.

4. **Do not fix anything.** The auditor reports; it never edits `core/`, `tests/`,
   or `docs/`. If the user then wants fixes, that is follow-up work for the build
   agents, not for this skill.

## Guardrails for this skill

- The audit is **read-only** over the codebase. The only file created is the
  report under `audits/`.
- If the toolchain cannot be fully run in this environment (e.g. PyPI egress is
  blocked, per `docs/decision-log.md` DL-002), the auditor must say so and state
  what it therefore could not verify. Relay that caveat to the user rather than
  implying a clean bill of health.
- Independence is the whole point: if the auditor's findings contradict a ticked
  box in `docs/traceability.md` or a "Done" in a story file, that contradiction
  is a headline finding, not something to smooth over.
