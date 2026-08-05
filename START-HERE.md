# BG-Markov — start here

You need **Python 3.12**. Nothing else.

> Starting from scratch — no clone yet, or nothing installed? **`INSTALL.md`** is the full
> walkthrough: prerequisites, the branch you must check out, and what every failure message
> means. This page assumes you already have the repo.

```bash
./start.sh
```

That is the whole thing. It checks your machine, installs into a local `.venv`, seeds a
database of **synthetic** data, and serves it at <http://127.0.0.1:8000>.

Press **Ctrl-C** to stop.

---

## If it complains

```bash
./scripts/dev.sh doctor      # says, in a sentence, what is missing
```

Common answers:

| It says | Do |
|---|---|
| `no Python 3.12 found (tried python3.12, python3, python, py -3.12)` | macOS: `brew install python@3.12` · Ubuntu: `sudo apt install python3.12 python3.12-venv` · Windows: <https://www.python.org/downloads/> then **reopen the shell** |
| ...and you have it somewhere unusual | `PYTHON=/full/path/to/python3.12 ./start.sh` |
| `venv present but INCOMPLETE` | `rm -rf .venv && ./start.sh` |
| `port 8000 is already in use` | `BGAPP_PORT=8123 ./start.sh` |

**Windows:** this needs a POSIX shell — use **WSL** or **Git Bash**. Or run the three steps
by hand; they are in `docs/RUNBOOK.md §1`.

---

## What you are looking at

Everything on screen is **made up**. The database was built by the synthetic generator, and
every page carries a red **DEMO DATA** banner saying so. On screen, 658 synthetic meals
render exactly like 658 real ones — the banner exists because the dangerous failure here is
not a crash, it is *believing a number*.

To start an **empty** database instead — the real-capture path, no banner:

```bash
./scripts/dev.sh serve
```

`./scripts/dev.sh status` tells you which database is which without opening either.

---

## Then

**`docs/RUNBOOK.md`.**

- **§3** is a 24-step manual checklist with the expected values written down, so *"looks
  about right"* is not the test.
- **★ §4 is what is known NOT to work.** Read it before you start, so you do not spend the
  evening hunting a misconfiguration that is not there.

---

## Other commands

| | |
|---|---|
| `./scripts/dev.sh doctor` | is this machine ready? |
| `./scripts/dev.sh demo` | seed + serve synthetic data (what `start.sh` does) |
| `./scripts/dev.sh serve` | serve the empty database |
| `./scripts/dev.sh status` | what the local databases contain |
| `./scripts/dev.sh reset` | delete them (asks you to type `DELETE`) |
| `./scripts/dev.sh check` | the full CI gates: ruff, `mypy --strict`, pytest, coverage |
