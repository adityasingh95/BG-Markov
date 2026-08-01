#!/usr/bin/env bash
# BG-Markov — one command to run it on your laptop.
#
#   ./start.sh
#
# Checks the machine, installs into ./.venv, seeds a SYNTHETIC database, and serves it on
# http://127.0.0.1:8000. Ctrl-C to stop. See START-HERE.md.
#
# ★ `06 §7` — binds to 127.0.0.1 only. The app never leaves localhost in v1.
set -euo pipefail
cd "$(dirname "$0")"

printf '\n\033[1mBG-Markov\033[0m — checking this machine\n\n'
# ★ Preflight FIRST, always. A missing prerequisite should be a sentence, not a traceback
# forty lines deep — which is exactly how this project found its `sqlite3` dependency.
./scripts/dev.sh doctor || exit 1

VENV_BIN=bin
[ -d .venv/Scripts ] && VENV_BIN=Scripts   # Windows / Git Bash

if [ ! -d .venv ] || ! ".venv/${VENV_BIN}/python" -c "import fastapi" >/dev/null 2>&1; then
  printf '\n\033[1m==>\033[0m first run — installing (a few minutes)\n\n'
  ./scripts/dev.sh setup
fi

printf '\n\033[1m==>\033[0m starting\n'
printf '    open \033[1mhttp://127.0.0.1:%s\033[0m   (Ctrl-C to stop)\n\n' "${BGAPP_PORT:-8000}"
exec ./scripts/dev.sh demo
