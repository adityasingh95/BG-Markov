#!/usr/bin/env bash
# BG-Markov — one entry point for running this locally (S-1024).
#
#   ./scripts/dev.sh setup     # venv + pinned deps + schema (via Alembic)
#   ./scripts/dev.sh serve     # run against ./bgapp-dev.db  -> http://127.0.0.1:8000
#   ./scripts/dev.sh demo      # seed ./bgapp-demo.db with SYNTHETIC data, then serve it
#   ./scripts/dev.sh reset     # delete the local databases (asks first)
#   ./scripts/dev.sh check     # the CI gates: ruff + mypy --strict + pytest + coverage
#   ./scripts/dev.sh status    # which databases exist, what they hold
#   ./scripts/dev.sh doctor    # preflight: is this machine ready?
#
# ★ `06 §7` — this binds to 127.0.0.1 only. The app never leaves localhost in v1.
#
# ★ `demo` produces a database the app marks on screen as synthetic (S-1024). Nothing in
# the seeded data says anything about her, and every screen says so.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# * RELATIVE, not "${ROOT}/...". Under Git Bash on Windows `pwd` is /c/Users/..., which
# Python's sqlite3 driver does not resolve as a Windows path -- it would silently create or
# look for the database somewhere else entirely. The script cd's to the repo root above, so
# a bare filename is both correct and portable.
DEV_DB="bgapp-dev.db"
DEMO_DB="bgapp-demo.db"
PORT="${BGAPP_PORT:-8000}"

# * Where a venv puts its executables: `bin` on POSIX, `Scripts` on Windows -- including
# under Git Bash, which is a POSIX shell driving a Windows Python. Resolved once, here,
# because a hard-coded `.venv/bin` is the single thing that stops this script working on the
# operator's laptop.
venv_bin() {
  if [ -d .venv/Scripts ]; then printf 'Scripts'; else printf 'bin'; fi
}

log()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mxx\033[0m %s\n' "$*" >&2; exit 1; }

activate() {
  [ -d .venv ] || die "no .venv -- run: ./scripts/dev.sh setup"
  # shellcheck disable=SC1091
  . ".venv/$(venv_bin)/activate"
}

# Bring a database to the current schema.
#
# ★ This delegates to Python and does NOT reason about the database in bash. The first
# version shelled out to the `sqlite3` CLI to check for migration history; that binary is not
# installed everywhere, the check silently answered "no", and `alembic upgrade` then died
# with "table audit_log already exists" — the operator's FIRST command failing with a wall of
# SQL. The venv's Python is already a hard requirement; sqlite3 never was.
migrate() {
  python -m scripts.migrate_db "$1"
}

# Find a Python 3.12. `python3.12` on Linux, often `python3` on macOS/Homebrew, and on
# Windows usually just `python` or the `py -3.12` launcher -- so the name is discovered, not
# assumed. PYTHON=... always wins.
find_python() {
  if [ -n "${PYTHON:-}" ]; then printf '%s' "$PYTHON"; return 0; fi
  local candidate
  for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)' \
       >/dev/null 2>&1; then
      printf '%s' "$candidate"; return 0
    fi
  done
  # The Windows launcher is not on PATH as an interpreter name.
  if command -v py >/dev/null 2>&1 && py -3.12 -c "pass" >/dev/null 2>&1; then
    printf 'py -3.12'; return 0
  fi
  return 1
}

cmd_setup() {
  local py
  py="$(find_python)" || die "need Python 3.12 -- run ./scripts/dev.sh doctor for how to get it"
  # shellcheck disable=SC2086
  [ -d .venv ] || { log "creating .venv ($py)"; $py -m venv .venv; }
  # shellcheck disable=SC1091
  . ".venv/$(venv_bin)/activate"
  log "installing pinned deps (.[dev])"
  python -m pip install --upgrade pip >/dev/null
  pip install -e ".[dev]" >/dev/null
  log "python: $(python --version)"
  log "creating the schema at ${DEV_DB}"
  migrate "sqlite:///${DEV_DB}"
  log "done. next:  ./scripts/dev.sh serve      (empty database, real capture)"
  log "        or:  ./scripts/dev.sh demo       (synthetic data, banner on every screen)"
}

cmd_serve() {
  activate
  migrate "sqlite:///${DEV_DB}"
  log "serving ./bgapp-dev.db on http://127.0.0.1:${PORT}   (Ctrl-C to stop)"
  BGAPP_DB_URL="sqlite:///${DEV_DB}" exec uvicorn api.app:app \
    --host 127.0.0.1 --port "${PORT}" "$@"
}

cmd_demo() {
  activate
  if [ ! -f "${DEMO_DB}" ]; then
    log "seeding ${DEMO_DB} — 240 days of SYNTHETIC data"
    python -m scripts.seed_demo_db --db "${DEMO_DB}" --days 240 --seed 7
  else
    log "using existing ${DEMO_DB}  (./scripts/dev.sh reset to start over)"
  fi
  migrate "sqlite:///${DEMO_DB}"
  log "serving ./bgapp-demo.db on http://127.0.0.1:${PORT}   (Ctrl-C to stop)"
  warn "every screen will carry a DEMO DATA banner. That is the point."
  BGAPP_DB_URL="sqlite:///${DEMO_DB}" exec uvicorn api.app:app \
    --host 127.0.0.1 --port "${PORT}" "$@"
}

cmd_reset() {
  # * No arrays. bash 3.2 -- which is what a stock macOS ships, frozen in 2007 -- treats
  # ${arr[@]} on an EMPTY array as an unbound variable under `set -u`, so the array version
  # aborted on a laptop with nothing to delete: the one case where it should say so calmly.
  local any=0
  for f in "${DEV_DB}" "${DEMO_DB}"; do
    [ -f "$f" ] || continue
    if [ "$any" -eq 0 ]; then warn "about to DELETE:"; any=1; fi
    printf '     %s (%s)\n' "$f" "$(du -h "$f" | cut -f1)"
  done
  if [ "$any" -eq 0 ]; then log "nothing to delete"; return 0; fi

  # Confirmable, and never in one tap (05b section 2). A local dev database is cheap; the
  # habit of deleting one without reading which is not.
  printf '  type DELETE to confirm: '
  local reply=""
  read -r reply || true
  [ "$reply" = "DELETE" ] || die "not confirmed -- nothing deleted"
  for f in "${DEV_DB}" "${DEMO_DB}"; do
    if [ -f "$f" ]; then rm -f "$f"; log "deleted $f"; fi
  done
  return 0
}

cmd_status() {
  activate
  for f in "${DEV_DB}" "${DEMO_DB}"; do
    if [ ! -f "$f" ]; then printf '  %-28s absent\n' "$(basename "$f")"; continue; fi
    BGAPP_DB_URL="sqlite:///${f}" python - "$f" <<'PY'
import sys
from sqlalchemy import func, select
from data.db import make_engine, session_factory
from data.provenance import is_demo_database
from data.tables import BolusLog, MealEvent, PredictionLog

path = sys.argv[1]
with session_factory(make_engine(f"sqlite:///{path}"))() as s:
    try:
        demo = is_demo_database(s)
        meals = s.scalar(select(func.count()).select_from(MealEvent)) or 0
        boluses = s.scalar(select(func.count()).select_from(BolusLog)) or 0
        preds = s.scalar(select(func.count()).select_from(PredictionLog)) or 0
    except Exception as exc:  # noqa: BLE001 - status must never fail on a stale file
        print(f"  {path.split('/')[-1]:<28} unreadable: {exc}")
        raise SystemExit(0)
kind = "SYNTHETIC (demo)" if demo else "not marked — treat as real capture"
print(f"  {path.split('/')[-1]:<28} {kind}")
print(f"  {'':<28} meals={meals} boluses={boluses} predictions={preds}")
PY
  done
}

# Is a TCP port already taken? Asked in Python, not with lsof/netstat/ss, because which of
# those exists depends on the machine -- the sqlite3 lesson again.
port_in_use() {
  "${1}" - "${2}" <<'PORTCHECK' 2>/dev/null
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(0)   # in use
else:
    sys.exit(1)   # free
finally:
    s.close()
PORTCHECK
}

cmd_doctor() {
  # * Everything else in this script assumes the machine is ready. This is the command that
  # says otherwise IN A SENTENCE, rather than letting a missing prerequisite surface as a
  # traceback forty lines deep -- which is how the sqlite3 dependency was found.
  local ok=1
  printf '  %-22s %s\n' "shell" "${BASH_VERSION:-unknown}"
  case "${BASH_VERSION:-}" in
    3.*)
      warn "bash 3.2 (stock macOS). Supported -- but if anything here misbehaves,"
      warn "  'brew install bash' and re-run with the newer one."
      ;;
  esac

  local py=""
  if py="$(find_python)"; then
    # shellcheck disable=SC2086
    printf '  %-22s %s (%s)\n' "python 3.12" "$($py --version 2>&1)" "$py"
  else
    ok=0
    warn "no Python 3.12 found (tried python3.12, python3, python, py -3.12)."
    warn "  macOS:    brew install python@3.12"
    warn "  Ubuntu:   sudo apt install python3.12 python3.12-venv"
    warn "  Windows:  https://www.python.org/downloads/  then use Git Bash or WSL"
    warn "  elsewhere?  PYTHON=/full/path/to/python3.12 ./scripts/dev.sh setup"
  fi

  if [ -d .venv ]; then
    printf '  %-22s %s\n' "venv layout" ".venv/$(venv_bin)"
    if ".venv/$(venv_bin)/python" -c "import fastapi, sqlalchemy, alembic" >/dev/null 2>&1; then
      printf '  %-22s %s\n' "venv" "present, deps installed"
    else
      ok=0
      printf '  %-22s %s\n' "venv" "present but INCOMPLETE"
      warn "run: ./scripts/dev.sh setup"
    fi
  else
    printf '  %-22s %s\n' "venv" "absent -- run: ./scripts/dev.sh setup"
  fi

  # A port already in use looks exactly like a broken app, and is not.
  local pyprobe="python3"
  command -v "$pyprobe" >/dev/null 2>&1 || pyprobe="python"
  if command -v "$pyprobe" >/dev/null 2>&1 && port_in_use "$pyprobe" "$PORT"; then
    ok=0
    warn "port ${PORT} is already in use -- try: BGAPP_PORT=8123 ./scripts/dev.sh demo"
  else
    printf '  %-22s %s\n' "port ${PORT}" "free"
  fi

  echo
  if [ "$ok" -eq 1 ]; then
    log "ready. next:  ./scripts/dev.sh demo"
  else
    die "not ready -- see the notes above"
  fi
}

cmd_check() { exec ./scripts/verify.sh; }

case "${1:-}" in
  setup)  shift; cmd_setup "$@" ;;
  serve)  shift; cmd_serve "$@" ;;
  demo)   shift; cmd_demo "$@" ;;
  reset)  shift; cmd_reset "$@" ;;
  status) shift; cmd_status "$@" ;;
  check)  shift; cmd_check "$@" ;;
  doctor) shift; cmd_doctor "$@" ;;
  *)
    sed -n '2,15p' "$0" | sed 's/^#//' | sed 's/^ //'
    exit 1
    ;;
esac
