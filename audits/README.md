# audits/

Home of the **Independent Auditor** — a fourth role, outside the SDET/Dev/BA
build loop, invoked on demand via `/audit`.

## Why this directory exists separately from `docs/`

`docs/` is owned by **BA**, one of the three build agents. Audit reports must not
live inside the artifacts they audit, and the auditor must not touch a build
agent's files. So the auditor owns `audits/` and nothing else. Reports here are
the auditor's record; they are not maintained by BA and are not part of the
traceability matrix.

## What the auditor does

- Reviews delivered work on two axes: **fitment to the product objective** and
  **quality/honesty of the output**.
- Verifies from **primary sources** — the spec pack (intent), the code and tests
  (reality), git history (was the test red before the code went green?), and the
  running toolchain — **not** from the build agents' self-reported status. Every
  ticked checkbox and "✅ Done" is treated as a hypothesis to confirm or refute.
- Is **read-only** over the codebase. It never edits `core/`, `tests/`, or
  `docs/`. It writes only reports here.

The auditor's full charter is `.claude/agents/independent-auditor.md`; the
invocation entry point is `.claude/skills/audit/SKILL.md`.

## The question every report answers

> Could a model that is quietly wrong about a low survive the work as built?

## Reports

One file per run: `AUDIT-<YYYY-MM-DD>-<nn>.md`.
