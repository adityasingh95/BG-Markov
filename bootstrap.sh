#!/usr/bin/env bash
# BG-Markov — from a cold laptop to a running app, in one command (S-1025).
#
#   ./bootstrap.sh              check the machine, offer to install what is missing,
#                               update the checkout, then run it
#   ./bootstrap.sh --no-start   everything except serving
#
# ★ This script installs software. Every installer runs only after a typed confirmation,
# and the exact command is printed first. There is no --yes flag and there will not be one:
# consent you can pass on a command line is consent nobody read.
#
# ★ `06 §7` — whatever it starts binds to 127.0.0.1 only.
set -euo pipefail
cd "$(dirname "$0")"

NO_START=0
for arg in "$@"; do
  case "$arg" in
    --no-start) NO_START=1 ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^#//' | sed 's/^ //'
      exit 0
      ;;
    *) printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mxx\033[0m %s\n' "$*" >&2; exit 1; }

printf '\n\033[1mBG-Markov\033[0m — setting this machine up\n\n'

# --- 1. Python 3.12 --------------------------------------------------------------------
#
# Asked via `dev.sh python` rather than re-implemented here. Two copies of "which Python
# counts" is two copies that drift, and the one that drifts is the one nobody runs.

# The install command for THIS machine, or empty if we have no safe way to offer one.
# Printed to the operator verbatim and then run verbatim, so what he agreed to and what
# happens cannot differ.
install_command() {
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      if command -v winget >/dev/null 2>&1; then
        printf '%s' "winget install --id Python.Python.3.12 -e --source winget \
--accept-source-agreements --accept-package-agreements"
      fi
      ;;
    Darwin)
      if command -v brew >/dev/null 2>&1; then printf '%s' "brew install python@3.12"; fi
      ;;
    Linux)
      # python3.12-venv is a separate package on Debian-family systems and setup fails
      # without it, in a way that reads as a broken venv rather than a missing package.
      if command -v apt-get >/dev/null 2>&1; then
        printf '%s' "sudo apt-get install -y python3.12 python3.12-venv"
      fi
      ;;
  esac
}

if ! ./scripts/dev.sh python >/dev/null 2>&1; then
  warn "no Python 3.12 on this machine (or it is not on PATH)."
  warn "  3.11 is too old — pip refuses, and says something misleading about the project."

  cmd="$(install_command)"
  if [ -z "$cmd" ]; then
    printf '\n  Install Python 3.12, then run ./bootstrap.sh again:\n\n'
    printf '      https://www.python.org/downloads/\n\n'
    printf '  Already have it somewhere unusual?\n'
    printf '      PYTHON=/full/path/to/python3.12 ./start.sh\n\n'
    die "cannot offer to install it for you on this platform"
  fi

  printf '\n  I can install it for you, by running exactly this:\n\n'
  printf '      \033[1m%s\033[0m\n\n' "$cmd"
  printf '  This adds Python 3.12 alongside anything you already have. It does not\n'
  printf '  remove, replace or upgrade another Python.\n\n'
  printf '  Type YES to run it, or anything else to stop: '

  reply=""
  read -r reply || true
  if [ "$reply" != "YES" ]; then
    printf '\n'
    die "nothing was installed. Install Python 3.12 yourself, then re-run ./bootstrap.sh"
  fi

  printf '\n'
  log "running: $cmd"
  # `eval` so the command that runs is byte-for-byte the one shown above. The string is
  # built in this file from literals; nothing from the operator or the environment reaches it.
  eval "$cmd"

  printf '\n'
  log "installed."
  warn "★ Now reopen your shell — close this window, open a new one — and run"
  warn "  ./bootstrap.sh again."
  warn "  PATH is read when a shell starts, so THIS shell still cannot see the new Python."
  warn "  Carrying on here would fail in a way that looks like a broken install."
  exit 0
fi

log "python: $(./scripts/dev.sh python) — $(./scripts/dev.sh python >/dev/null && printf 'ok')"

# --- 2. Bring the checkout up to date ---------------------------------------------------
#
# ★ Never over uncommitted work. This is where the operator will have been poking at things,
# and a bootstrap script that pulls regardless can fail mid-merge and leave the tree in a
# state he did not ask for and cannot easily read. `--ff-only` for the same reason: no
# merge commits, no rebase, no conflict resolution he did not start.
if [ -d .git ] && command -v git >/dev/null 2>&1; then
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    warn "skipping the update — you have uncommitted local changes."
    warn "  commit or stash them first if you want the latest. Carrying on with what is here."
  else
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || printf 'HEAD')"
    if [ "$branch" = "HEAD" ]; then
      warn "detached HEAD — skipping the update."
    else
      log "updating ($branch)"
      git pull --ff-only origin "$branch" 2>/dev/null ||
        warn "could not update — carrying on with the code already here."
    fi
  fi
fi

# --- 3. Hand over ------------------------------------------------------------------------
if [ "$NO_START" -eq 1 ]; then
  printf '\n'
  ./scripts/dev.sh doctor
  printf '\n'
  log "--no-start given — stopping here. Run ./start.sh when you are ready."
  exit 0
fi

printf '\n'
exec ./start.sh
