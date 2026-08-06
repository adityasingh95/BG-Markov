"""Shared browser fixture and recording helpers for all Playwright suites (a11y + e2e).

The Playwright sync API cannot run two ``sync_playwright()`` contexts in one
process, so the browser is launched once here and shared across suites. Each
suite provides its own ``live_server`` and ``page``.

★ **S-1023 — recording.** Every browser assertion this project makes is reported as a
sentence. When `test_post_bg_form_asks_reported_time_and_saves` was green on the toast
*"Could not save"*, the run looked exactly like a passing run and there was nothing to go
back and watch. Setting ``BGAPP_BROWSER_ARTIFACTS`` to a directory makes every context in
both suites leave a **video** and a **Playwright trace** behind.

It is **opt-in**. Video and tracing cost real wall-clock and disk, and an always-on recorder
fills a directory nobody opens.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, sync_playwright

#: Set this to a directory to record. Absent ⇒ no video, no trace, no cost.
ARTIFACTS_ENV = "BGAPP_BROWSER_ARTIFACTS"


def uninstrumented_env(**overrides: str) -> dict[str, str]:
    """Environment for a subprocess that must NOT join pytest's coverage session.

    ★ `pytest-cov.pth` lives in site-packages, so **every** Python process started during a
    test run silently enrols itself and writes its own `.coverage.*` file. When that child
    runs with a `cwd` outside the repository — which any test driving a script in `tmp_path`
    does — coverage cannot find `pyproject.toml`, falls back to its default of *no branch
    tracking*, and the parent's `branch = true` data will not merge with it. The run then dies
    at report time with

        INTERNALERROR> coverage.exceptions.DataError:
            Can't combine statement coverage data with branch data

    **after every test has already passed**, so the failure reads as a broken coverage tool
    rather than as something a test did. It cost two red CI runs before it was recognised.

    Use this for any subprocess spawned for its *behaviour* rather than its coverage.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE", "COVERAGE_"))
    } | overrides

#: The video frame. Fixed at context creation, so a test that changes viewport mid-run
#: (the 200% zoom and 390px checks) is letterboxed rather than re-encoded.
VIDEO_SIZE = {"width": 1280, "height": 900}


def artifacts_dir() -> Path | None:
    """Where to write recordings, or ``None`` when recording is off."""
    raw = os.environ.get(ARTIFACTS_ENV)
    return Path(raw) if raw else None


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:120]


def new_recorded_context(browser: Browser, *, name: str, **kwargs: Any) -> BrowserContext:
    """A browser context that records itself when ``ARTIFACTS_ENV`` is set.

    Used by **both** suites' ``page`` fixtures from one implementation, so there cannot be
    a suite that is quietly "the one that isn't recorded".
    """
    out = artifacts_dir()
    if out is not None:
        kwargs.setdefault("record_video_dir", str(out / "video"))
        kwargs.setdefault("record_video_size", VIDEO_SIZE)
    context = browser.new_context(**kwargs)
    if out is not None:
        # `screenshots` is what makes the trace viewer show the page at each action; without
        # it a trace is a list of call names, which looks like evidence and answers nothing.
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    return context


def close_recorded_context(context: BrowserContext, *, name: str) -> None:
    """Close ``context``, saving its trace and giving its video a readable name.

    ★ The video handle is taken **before** the close: ``context.pages`` empties on close, and
    the file itself is only finalised afterwards — so the handle has to survive the gap.
    Playwright otherwise writes the video under a random hash, which is the difference
    between *"recording is configured"* and *"there is something to watch"*.
    """
    out = artifacts_dir()
    if out is None:
        context.close()
        return

    (out / "video").mkdir(parents=True, exist_ok=True)
    (out / "trace").mkdir(parents=True, exist_ok=True)
    context.tracing.stop(path=str(out / "trace" / f"{_safe(name)}.zip"))
    video = context.pages[0].video if context.pages else None
    context.close()
    if video is not None:
        video.save_as(str(out / "video" / f"{_safe(name)}.webm"))
        # ★ `save_as` COPIES. Without this the hash-named original stays behind, and a
        # directory holding `demo-walkthrough.webm` beside `2b487ebe518b47….webm` of
        # identical bytes is exactly the confusion the naming existed to prevent.
        video.delete()


def _chromium_executable() -> str | None:
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base:
        candidate = Path(base) / "chromium"
        if candidate.exists():
            return str(candidate)
    return None


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        launched = p.chromium.launch(executable_path=_chromium_executable())
        try:
            yield launched
        finally:
            launched.close()
