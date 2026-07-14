"""Fixtures for browser end-to-end flow tests (S-301).

Like the a11y fixtures, but the live server is pointed at a throwaway SQLite DB
(via ``BGAPP_DB_URL``) so ``POST /api/meals`` actually persists.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, Page


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    import uvicorn

    tmpdir = tempfile.mkdtemp(prefix="bge2e-")
    os.environ["BGAPP_DB_URL"] = f"sqlite:///{Path(tmpdir) / 'e2e.db'}"

    import api.deps as deps

    deps._engine = None  # force re-init against the temp DB
    from api.app import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
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
    else:  # pragma: no cover
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("e2e live server did not start")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def page(browser: Browser, live_server: str) -> Iterator[Page]:  # browser: tests/conftest.py
    context = browser.new_context()
    pg = context.new_page()
    pg.goto(live_server + "/", wait_until="networkidle")
    try:
        yield pg
    finally:
        context.close()
