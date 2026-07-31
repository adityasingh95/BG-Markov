"""S-1023 (SDET) — the browser run leaves a video and a trace. RED first.

★ The assertion is on the **file**, not on the option being set. "Configured" and "produced"
have already diverged twice in this codebase — `idempotency_key` was required and read by
nothing (S-1016), and `serve_meal_prediction` was written and called by nothing (S-1015).
A recorder that sets `record_video_dir` and never calls `save_as` leaves the video under a
random hash filename, or leaves nothing at all, and a test that checks the option passes.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from playwright.sync_api import Browser

from tests.conftest import (
    ARTIFACTS_ENV,
    close_recorded_context,
    new_recorded_context,
)

pytestmark = pytest.mark.e2e


def test_recording_off_by_default_leaves_nothing(
    browser: Browser, live_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ The reverse guard.

    An always-on recorder triples CI wall-clock and fills the disk with artifacts nobody
    opens. "Off" has to be genuinely off, and the only way to know is to look.
    """
    monkeypatch.delenv(ARTIFACTS_ENV, raising=False)
    context = new_recorded_context(browser, name="off")
    page = context.new_page()
    page.goto(live_server + "/", wait_until="networkidle")
    assert page.video is None, "a video is being recorded with recording switched off"
    close_recorded_context(context, name="off")
    assert not list(tmp_path.rglob("*.webm"))
    assert not list(tmp_path.rglob("*.zip"))


def test_recording_on_writes_a_video_and_a_trace(
    browser: Browser, live_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ARTIFACTS_ENV, str(tmp_path))
    context = new_recorded_context(browser, name="on")
    page = context.new_page()
    page.goto(live_server + "/", wait_until="networkidle")
    page.locator(".chip.favourite").first.click()
    close_recorded_context(context, name="on")

    video = tmp_path / "video" / "on.webm"
    trace = tmp_path / "trace" / "on.zip"
    assert video.exists(), (
        f"no video at {video}. Files present: {sorted(p.name for p in tmp_path.rglob('*'))}"
    )
    assert video.stat().st_size > 0, "the video is a zero-byte placeholder"
    assert trace.exists(), f"no trace at {trace}"

    # ★ Only the NAMED video survives. `save_as` COPIES, so the hash-named original Playwright
    # wrote stays behind unless it is removed — and a directory holding
    # `on.webm` beside `2b487ebe518b47…webm` of identical bytes is the confusion the naming
    # existed to prevent. Observed on the first real recording run, not reasoned about.
    videos = sorted(pth.name for pth in (tmp_path / "video").glob("*.webm"))
    assert videos == ["on.webm"], f"stray unnamed recordings left behind: {videos}"


def test_the_trace_actually_contains_the_run(
    browser: Browser, live_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ A trace that opens to an empty timeline is worse than no trace: it looks like
    evidence and answers nothing."""
    monkeypatch.setenv(ARTIFACTS_ENV, str(tmp_path))
    context = new_recorded_context(browser, name="content")
    page = context.new_page()
    page.goto(live_server + "/", wait_until="networkidle")
    page.fill("#f-pre_bg", "142")
    close_recorded_context(context, name="content")

    trace = tmp_path / "trace" / "content.zip"
    with zipfile.ZipFile(trace) as zf:
        names = zf.namelist()
    assert any(n.endswith(".trace") for n in names), f"no trace stream in {names}"
    # `screenshots=True` is what makes the trace viewer show the page at each action; a
    # trace without them is a list of call names.
    assert any("resources/" in n or n.endswith(".jpeg") for n in names), (
        f"the trace carries no screenshots: {names[:20]}"
    )
