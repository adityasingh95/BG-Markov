#!/usr/bin/env bash
# BG-Markov — one entry point for running this locally (S-1024).
#
#   ./scripts/dev.sh setup     # venv + pinned deps + schema (via Alembic)
#   ./scripts/dev.sh serve     # run against ./bgapp-dev.db  -> http://127.0.0.1:8000
#   ./scripts/dev.sh demo      # seed ./bgapp-demo.db with SYNTHETIC data, then serve it
#   ./scripts/dev.sh reset     # delete the local databases (asks first)
#   ./scripts/dev.sh check     # the CI gates: ruff + mypy --strict + pytest + coverage
#   ./scripts/dev.sh status    # which databases exist, what they hold
#
# ★ `06 §7` — this binds to 127.0.0.1 only. The app never leaves localhost in v1.
#
# ★ `demo` produces a database the app marks on screen as synthetic (S-1024). Nothing in
# the seeded data says anything about her, and every screen says so.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

DEV_DB="${ROOT}/bgapp-dev.db"
DEMO_DB="${ROOT}/bgapp-demo.db"
PORT="${BGAPP_PORT:-8000}"

log()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mxx\033[0m %s\n' "$*" >&2; exit 1; }

activate() {
  [ -d .venv ] || die "no .venv — run: ./scripts/dev.sh setup"
  # shellcheck disable=SC1091
  . .venv/bin/activate
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

cmd_setup() {
  local py="${PYTHON:-python3.12}"
  command -v "$py" >/dev/null || die "need Python 3.12 (set PYTHON=... to override)"
  [ -d .venv ] || { log "creating .venv ($py)"; "$py" -m venv .venv; }
  # shellcheck disable=SC1091
  . .venv/bin/activate
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
  local found=()
  [ -f "${DEV_DB}" ]  && found+=("${DEV_DB}")
  [ -f "${DEMO_DB}" ] && found+=("${DEMO_DB}")
  if [ ${#found[@]} -eq 0 ]; then log "nothing to delete"; return 0; fi
  warn "about to DELETE:"
  for f in "${found[@]}"; do printf '     %s (%s)\n' "$f" "$(du -h "$f" | cut -f1)"; done
  # ★ Confirmable, and never in one tap (05b §2). A local dev database is cheap; the habit
  # of deleting one without reading which is not.
  read -r -p "  type DELETE to confirm: " reply
  [ "$reply" = "DELETE" ] || die "not confirmed — nothing deleted"
  for f in "${found[@]}"; do rm -f "$f"; log "deleted $f"; done
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

cmd_check() { exec ./scripts/verify.sh; }

case "${1:-}" in
  setup)  shift; cmd_setup "$@" ;;
  serve)  shift; cmd_serve "$@" ;;
  demo)   shift; cmd_demo "$@" ;;
  reset)  shift; cmd_reset "$@" ;;
  status) shift; cmd_status "$@" ;;
  check)  shift; cmd_check "$@" ;;
  *)
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
