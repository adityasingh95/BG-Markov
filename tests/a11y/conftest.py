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

import httpx
import pytest
from playwright.sync_api import Browser, Page

from tests.conftest import close_recorded_context, new_recorded_context


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Run the FastAPI app on a background uvicorn thread; yield its base URL.

    ★ **Its database is a fresh per-session temp file.** Without the override the app
    falls back to `api.deps`' default `./bgapp-dev.db` — a persistent file in the repo
    root that every run appends to. That is not a tidiness issue: on an accumulated
    database these tests grade a page in a state nobody asked for, and the verdict depends
    on what happened to run earlier. It was found exactly that way — the calculator's
    implausible-input a11y test failed against 34 accumulated profile rows and passed
    immediately on a clean file, having tested nothing about the code either time.

    `_engine` is reset because it is a module-level cache: a run that touched
    `api.deps` before this fixture would otherwise keep serving the old database.
    """
    import uvicorn

    import api.deps as deps
    from api.app import app  # imported lazily: absent app ⇒ clear RED, not a collect error

    db = tmp_path_factory.mktemp("a11y") / "live.db"
    os.environ["BGAPP_DB_URL"] = f"sqlite:///{db}"
    deps._engine = None

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


@pytest.fixture
def page(  # browser: tests/conftest.py
    browser: Browser, live_server: str, request: pytest.FixtureRequest
) -> Iterator[Page]:
    # S-1023: one recording implementation, shared with the e2e suite, so there cannot be a
    # suite that is quietly "the one that isn't recorded".
    name = f"a11y-{request.node.name}"
    context = new_recorded_context(browser, name=name)
    pg = context.new_page()
    pg.goto(live_server + "/", wait_until="networkidle")
    try:
        yield pg
    finally:
        close_recorded_context(context, name=name)
