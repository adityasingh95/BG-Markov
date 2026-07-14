#!/usr/bin/env bash
# Launch the accessible logging shell (S-102) locally.
#
#   ./scripts/run_app.sh      # then open http://127.0.0.1:8000
#
# Binds to 127.0.0.1 only (06 §7 — the app never leaves localhost in v1).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi
echo "==> serving on http://127.0.0.1:8000  (Ctrl-C to stop)"
exec uvicorn api.app:app --host 127.0.0.1 --port 8000 "$@"
