# INSTALL — from nothing to a running app

Zero to the app open in a browser. **Around 5 minutes**, nearly all of it one download.

The install itself is quick — measured at **1m 28s** once the files are local. What you are
waiting on is **511 MB of dependencies** coming down the wire, so your connection sets the
pace: roughly a minute on fast broadband, five or more on a slow link.

What you end up with: BG-Markov at <http://127.0.0.1:8000>, loaded with **synthetic** data,
every page carrying a red DEMO DATA banner.

> Already cloned and just want to run it? Skip to [§4](#4-run-it). Something already broke?
> [§8](#8-when-it-goes-wrong) is organised by the exact message you saw.

---

## 1. What you need

| | |
|---|---|
| **git** | to clone |
| **Python 3.12** | exactly 3.12 — see the note below |
| **~2 GB free disk** | the venv is ~950 MB; numeric/stats libraries are large |
| **a POSIX shell** | Git Bash or WSL on Windows; Terminal on macOS/Linux |

**Why exactly 3.12.** 3.11 is too old — `pip` refuses to install and tells you the project
"does not appear to be a Python project", which is misleading but is what you get. 3.13 is
in fact fine (the full suite, `mypy --strict` and `ruff` are all green on 3.13.12) but the
setup script does not accept it yet, so it will tell you no Python was found while 3.13 sits
right there. Use 3.12 until that changes.

Installing 3.12 does **not** remove or disturb any other Python you already have. They sit
side by side.

---

## 2. Install the prerequisites

### Windows

1. **Git** — <https://git-scm.com/download/win>. The installer includes **Git Bash**, which
   is the shell you will use. Accept the defaults.
2. **Python 3.12** — <https://www.python.org/downloads/release/python-31211/> →
   *Windows installer (64-bit)*.
   **Tick "Add python.exe to PATH" on the first screen.** If you miss it, everything still
   works — the setup script falls back to the `py -3.12` launcher, which the installer always
   registers.
3. **Close and reopen Git Bash.** PATH is read when the shell starts, so a window opened
   before the install will not see the new Python.

Check it took:

```bash
python --version        # want: Python 3.12.x
py -3.12 --version      # fallback if the line above says 3.11 or errors
```

### macOS

```bash
brew install git python@3.12
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install git python3.12 python3.12-venv
```

`python3.12-venv` is a separate package on Debian-family systems and the setup **fails
without it**. Install both.

---

## 3. Clone it

### ★ You must name the branch

The repository's default branch is **not** the one you want. A plain `git clone` gives you a
tree with no `start.sh` in it, and nothing in this guide will work.

```bash
git clone -b claude/glycaemic-prediction-bolus-5sg02e-8pc62g \
  https://github.com/adityasingh95/BG-Markov.git

cd BG-Markov
```

Confirm you landed in the right place — **both** of these must succeed:

```bash
git branch --show-current      # claude/glycaemic-prediction-bolus-5sg02e-8pc62g
ls start.sh                    # start.sh
```

If `ls start.sh` says *No such file or directory*, you are on the default branch. Fix it
without re-cloning:

```bash
git checkout claude/glycaemic-prediction-bolus-5sg02e-8pc62g
```

### Where to put it (Windows)

Git Bash shows drives as `/c`, `/d`, `/f` … so `F:\BG-Markov` is `/f/BG-Markov`. To clone
onto your F: drive:

```bash
cd /f
git clone -b claude/glycaemic-prediction-bolus-5sg02e-8pc62g \
  https://github.com/adityasingh95/BG-Markov.git
cd BG-Markov
```

Avoid folders synced by OneDrive or Dropbox. The app writes a SQLite database continuously,
and file-sync tools lock and copy files mid-write — which corrupts databases.

---

## 4. Run it

```bash
./start.sh
```

That is the whole command. It checks the machine, creates `.venv`, installs the pinned
dependencies, builds the schema, seeds a synthetic database, and serves it.

If your shell refuses with *Permission denied*, use `bash start.sh` instead.

### What you should see

```
BG-Markov — checking this machine

  shell                  5.2.37(1)-release
  python 3.12            Python 3.12.11 (python)
  venv                   absent -- run: ./scripts/dev.sh setup
  port 8000              free

==> ready. next:  ./scripts/dev.sh demo

==> first run — installing (a few minutes)
==> creating .venv (python)
==> installing pinned deps (.[dev])
```

**`installing pinned deps` is the slow line.** It downloads 511 MB — `llvmlite` alone is
162 MB, `scipy` 108 MB, `pandas` 75 MB — and unpacks to a 953 MB `.venv`. There is no
progress bar and it prints nothing for the duration. **It has not hung.**

Then:

```
==> seeding bgapp-demo.db — 240 days of SYNTHETIC data
==> serving ./bgapp-demo.db on http://127.0.0.1:8000   (Ctrl-C to stop)
!! every screen will carry a DEMO DATA banner. That is the point.
```

---

## 5. Open it

<http://127.0.0.1:8000>

Every page carries a red **DEMO DATA — not her records** banner. That is deliberate and it
is a safety feature, not decoration: 658 synthetic meals render exactly like 658 real ones,
and the dangerous failure with this app is not a crash — it is *believing a number*.

**Stop the server** with **Ctrl-C** in the terminal.

**Start it again** with `./start.sh`. The second run takes seconds: the venv and the seeded
database are both reused.

---

## 6. The two databases

Two separate files, never mixed:

| File | Command | What it is |
|---|---|---|
| `bgapp-demo.db` | `./start.sh` or `./scripts/dev.sh demo` | 240 days of synthetic data. Banner on every page. |
| `bgapp-dev.db` | `./scripts/dev.sh serve` | Empty. **The real-capture path — no banner.** |

Both are git-ignored, so they never leave your machine. Anything you type into
`bgapp-dev.db` is treated as a real clinical record.

`./scripts/dev.sh status` tells you what each one holds without opening either.

---

## 7. Everyday commands

| Command | What it does |
|---|---|
| `./start.sh` | check machine → install if needed → seed → serve |
| `./scripts/dev.sh doctor` | is this machine ready? says what is missing, in a sentence |
| `./scripts/dev.sh demo` | seed + serve the synthetic database |
| `./scripts/dev.sh serve` | serve the empty database (real capture) |
| `./scripts/dev.sh status` | what the local databases contain |
| `./scripts/dev.sh reset` | delete both databases (asks you to type `DELETE`) |
| `./scripts/dev.sh check` | the full CI gates: ruff, `mypy --strict`, pytest, coverage |

Run on a different port when 8000 is taken:

```bash
BGAPP_PORT=8123 ./start.sh
```

---

## 8. When it goes wrong

Always start here — it reports on *your* machine rather than guessing:

```bash
./scripts/dev.sh doctor
```

| It says | What it means | Do |
|---|---|---|
| `no Python 3.12 found (tried python3.12, python3, python, py -3.12)` | 3.12 is not installed, or not on PATH | Install it ([§2](#2-install-the-prerequisites)), then **reopen the shell**. Installed somewhere unusual? `PYTHON=/full/path/to/python3.12 ./start.sh` |
| `venv present but INCOMPLETE` | install was interrupted part-way | `rm -rf .venv && ./start.sh` |
| `port 8000 is already in use` | something else has the port | `BGAPP_PORT=8123 ./start.sh` |
| `no .venv -- run: ./scripts/dev.sh setup` | nothing installed yet | `./start.sh` does this for you |
| `bash: ./start.sh: Permission denied` | exec bit lost (common on Windows) | `bash start.sh` |
| `does not appear to be a Python project` | wrong branch, or wrong directory | `ls start.sh` — if missing, see [§3](#-you-must-name-the-branch) |
| `ModuleNotFoundError: No module named 'scripts...'` | run from the wrong directory | `cd` to the repo root — the one containing `start.sh` |

**Out of disk part-way through the install.** The venv needs ~950 MB and pip needs roughly
as much again for its build cache. `rm -rf .venv ~/.cache/pip` and retry with room free.

---

## 9. Updating

```bash
git pull origin claude/glycaemic-prediction-bolus-5sg02e-8pc62g
./start.sh
```

`start.sh` re-installs if the dependencies changed and migrates the database schema forward
on every run. Your data is preserved — migrations alter the schema, never the rows.

---

## 10. Starting over

```bash
./scripts/dev.sh reset      # deletes both databases; asks you to type DELETE
rm -rf .venv                # deletes the installed dependencies
./start.sh                  # rebuilds everything
```

To remove it entirely, delete the cloned folder. Nothing is installed outside it — no system
packages, no registry entries, no services.

---

## 11. Next

**`docs/RUNBOOK.md`.**

- **§3** is a 24-step manual checklist with the expected values written down, so *"looks
  about right"* is not the test.
- **★ §4 is what is known NOT to work.** Read it before you start, so you do not spend an
  evening hunting a misconfiguration that was never there.

To run the full test suite yourself — 881 tests, `mypy --strict`, `ruff`, and the 90 %
coverage gate:

```bash
./scripts/dev.sh check
```

It takes about four minutes.
