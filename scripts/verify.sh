#!/usr/bin/env bash
# One command to verify the whole build the way CI does.
#
#   ./scripts/verify.sh
#
# Creates/uses a local .venv, installs the pinned deps, and runs the exact gates
# CI runs: ruff (fresh cache), mypy --strict, and pytest with the 90%-on-core
# coverage gate. The accessibility suite needs a Chromium build; if one cannot be
# installed the a11y tests are skipped (and that is called out), everything else
# still runs.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "==> repo: $ROOT"

# --- Python 3.12 venv ------------------------------------------------------
PY="${PYTHON:-python3.12}"
if [ ! -d .venv ]; then
  echo "==> creating .venv ($PY)"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate

echo "==> installing pinned deps (.[dev])"
python -m pip install --upgrade pip >/dev/null
pip install -e ".[dev]" >/dev/null
echo "    done: $(python --version)"

# --- Lint + types (fresh, matches CI) --------------------------------------
echo "==> ruff check --no-cache ."
ruff check --no-cache .

echo "==> mypy --strict core api data"
mypy --strict --no-incremental core api data

# --- Tests + coverage ------------------------------------------------------
if python -m playwright install chromium >/dev/null 2>&1 \
   || [ -e "${PLAYWRIGHT_BROWSERS_PATH:-/nonexistent}/chromium" ]; then
  echo "==> pytest (full suite incl. a11y) + coverage gate"
  pytest --cov=core --cov-report=term-missing --cov-fail-under=90
else
  echo "==> Chromium unavailable — skipping a11y; running the rest + coverage"
  pytest -m "not a11y" --cov=core --cov-report=term-missing --cov-fail-under=90
fi

echo
echo "✅ verify complete — lint, types, tests, and the 90%-on-core gate all passed."
