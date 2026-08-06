"""S-1025 (SDET) — `bootstrap.sh` installs software, so it is guilty until proven innocent.

RED first. Every test here drives the real script in a subprocess with a stubbed `PATH`; none
of them inspect it with a grep. A grep proves a string is present, not that the code path is
unreachable, and the property under test — *nothing gets installed unless the operator said
so* — is exactly the kind that greps miss.

★ The stubs write a **sentinel file** when invoked. Assertions are on the sentinel, not on the
exit code, because a script that installs and then fails for an unrelated reason produces the
same non-zero exit as one that correctly refused to install. Those two must not be confused.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "bootstrap.sh"

#: Every name `find_python` tries. A stub for each is what makes the machine look bare.
_INTERPRETERS = ("python3.12", "python3", "python", "py")

#: Anything that can install software. `sudo` is included deliberately: it is the one that
#: turns a stubbed `apt-get` back into a real one if the script reaches for it directly.
_INSTALLERS = ("winget", "brew", "apt-get", "apt", "sudo")


def _stub_dir(tmp_path: pathlib.Path, sentinel: pathlib.Path) -> pathlib.Path:
    """A directory to put FIRST on PATH: no working 3.12, and installers that only tattle."""
    d = tmp_path / "stubs"
    d.mkdir()

    for name in _INTERPRETERS:
        # Present on PATH but never 3.12 — the shape of the operator's actual laptop, which
        # had a working `python` that happened to be 3.11.
        p = d / name
        p.write_text("#!/bin/sh\nexit 1\n")
        p.chmod(0o755)

    for name in _INSTALLERS:
        p = d / name
        p.write_text(
            "#!/bin/sh\n"
            f'printf "%s %s\\n" "{name}" "$*" >> "{sentinel}"\n'
            "exit 0\n"
        )
        p.chmod(0o755)

    return d


def _run(
    cwd: pathlib.Path,
    stub: pathlib.Path,
    stdin: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{stub}{os.pathsep}{env['PATH']}"
    # Keep the test off the operator's port even if a stray code path tries to serve.
    env["BGAPP_PORT"] = "8987"
    return subprocess.run(
        ["bash", str(cwd / "bootstrap.sh"), *args],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_the_script_exists_and_is_executable() -> None:
    assert _SCRIPT.exists(), "bootstrap.sh does not exist"
    assert os.access(_SCRIPT, os.X_OK), "bootstrap.sh is not executable — `chmod +x`"
    assert _SCRIPT.read_text(encoding="utf-8").startswith("#!"), "no shebang"


def test_declining_the_offer_installs_nothing(tmp_path: pathlib.Path) -> None:
    """★ The one that matters.

    Assert on the SENTINEL, not the exit code. A script that installed Python and then died
    on the next line exits non-zero too — and would pass a test that only checked the code.
    """
    sentinel = tmp_path / "installed.log"
    stub = _stub_dir(tmp_path, sentinel)

    result = _run(_ROOT, stub, "n\n")

    assert not sentinel.exists(), (
        "bootstrap.sh ran an installer after the operator declined:\n"
        f"{sentinel.read_text() if sentinel.exists() else ''}"
    )
    assert result.returncode != 0, "declining must not report success"
    combined = result.stdout + result.stderr
    assert "3.12" in combined, "it never said what was missing"


def test_it_offers_before_it_installs(tmp_path: pathlib.Path) -> None:
    """The offer must name the command. An operator cannot consent to `[y/N]` alone."""
    sentinel = tmp_path / "installed.log"
    stub = _stub_dir(tmp_path, sentinel)

    result = _run(_ROOT, stub, "n\n")
    combined = result.stdout + result.stderr

    assert any(tool in combined for tool in ("winget", "brew", "apt")), (
        "the prompt does not show which install command it intends to run"
    )


def test_accepting_installs_then_stops_and_says_to_reopen(tmp_path: pathlib.Path) -> None:
    """★ A new interpreter is invisible to the shell that installed it.

    `PATH` is read at shell start. Pressing on here fails in a way that reads as a broken
    install rather than a stale `PATH`, sending the operator to debug the wrong thing.
    """
    sentinel = tmp_path / "installed.log"
    stub = _stub_dir(tmp_path, sentinel)

    result = _run(_ROOT, stub, "YES\n")
    combined = (result.stdout + result.stderr).lower()

    assert sentinel.exists(), "confirmed, but no installer was invoked"
    assert "reopen" in combined or "restart" in combined, (
        "installed without telling the operator the running shell cannot see the new Python"
    )
    assert "serving" not in combined, "carried on into the app in a shell with a stale PATH"


@pytest.fixture
def dirty_clone(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real clone of this repo with an uncommitted change in it."""
    dest = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--no-hardlinks", str(_ROOT), str(dest)],
        capture_output=True,
        check=True,
        timeout=180,
    )
    (dest / "START-HERE.md").write_text("locally edited, not committed\n", encoding="utf-8")
    return dest


def test_a_dirty_tree_is_reported_and_skipped_not_pulled_over(
    dirty_clone: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """★ The operator's uncommitted work is his. Skip the pull; never resolve it for him."""
    sentinel = tmp_path / "installed.log"
    stub = tmp_path / "empty"
    stub.mkdir()

    result = _run(dirty_clone, stub, "", "--no-start")
    combined = (result.stdout + result.stderr).lower()

    assert result.returncode == 0, f"a dirty tree must not be fatal:\n{combined}"
    assert "uncommitted" in combined or "local changes" in combined, (
        "skipped the update silently — the operator cannot tell it did not happen"
    )
    edited = (dirty_clone / "START-HERE.md").read_text(encoding="utf-8")
    assert edited == "locally edited, not committed\n", "it overwrote uncommitted work"
    assert not sentinel.exists()


def test_it_never_force_pulls(tmp_path: pathlib.Path) -> None:
    """The tempting fix for the test above is to make the dirty case 'just work'.

    `reset --hard`, `checkout --force` and `clean -fd` all silently destroy exactly the local
    work the previous test protects. This is the guard on the fix, not on the feature.
    """
    text = _SCRIPT.read_text(encoding="utf-8")
    code = [
        line.strip()
        for raw in text.splitlines()
        for line in [raw.strip()]
        if line and not line.startswith("#")
    ]
    for forbidden in ("reset --hard", "checkout --force", "checkout -f", "clean -fd", "-X theirs"):
        offenders = [line for line in code if forbidden in line]
        assert not offenders, f"bootstrap.sh destroys local work with `{forbidden}`: {offenders}"
