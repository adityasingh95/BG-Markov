"""Fixtures for browser-driven accessibility tests (S-102).

These tests drive a **real Chromium** against a **live FastAPI server** so that
computed styles, contrast and zoom behaviour are genuine — asserting them from
template source text would prove nothing. See docs/stories/S-102.md.

The FastAPI app is served by uvicorn in a background thread (in-process, so it
can be torn down cleanly). Chromium is resolved from the pre-installed browser
at ``$PLAYWRIGHT_BROWSERS_PATH/chromium`` when present, else Playwright's own
managed browser (CI installs it via ``playwright install --with-deps chromium``).
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, Page, sync_playwright


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _chromium_executable() -> str | None:
    """Prefer the pre-installed Chromium; fall back to Playwright's managed one."""
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base:
        candidate = Path(base) / "chromium"
        if candidate.exists():
            return str(candidate)
    return None


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    """Run the FastAPI app on a background uvicorn thread; yield its base URL."""
    import uvicorn

    from api.app import app  # imported lazily: absent app ⇒ clear RED, not a collect error

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if server.started:
            try:
                httpx.get(base_url + "/", timeout=1.0)
                break
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    else:  # pragma: no cover - only hit if the server never comes up
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("live server did not start within 15s")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        launched = p.chromium.launch(executable_path=_chromium_executable())
        try:
            yield launched
        finally:
            launched.close()


@pytest.fixture
def page(browser: Browser, live_server: str) -> Iterator[Page]:
    context = browser.new_context()
    pg = context.new_page()
    pg.goto(live_server + "/", wait_until="networkidle")
    try:
        yield pg
    finally:
        context.close()
