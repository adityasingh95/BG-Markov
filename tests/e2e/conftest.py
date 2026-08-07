"""Fixtures for browser end-to-end flow tests (S-301, hardened by S-1021).

Like the a11y fixtures, but the live server is pointed at a throwaway SQLite DB
(via ``BGAPP_DB_URL``) so ``POST /api/meals`` actually persists.

★ **S-1021.** These fixtures now hand a test two things it did not have: a **session
against the database the server is writing to**, and :func:`assert_saved`. Before that,
the only thing a flow test could look at was the page, and the strongest thing it said was
*"a toast appeared"* — which is also true when the save failed, because a failure writes a
toast too. `test_post_bg_form_asks_reported_time_and_saves` was green for weeks on the
toast **"Could not save — please try again."**

A UI test that asserts on the *existence* of feedback is testing that the page has a
`#toast` element.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page
from sqlalchemy.orm import Session

from tests.conftest import close_recorded_context, new_recorded_context

#: The exact strings the client scripts show when a write fails. Kept verbatim rather than
#: matched loosely: `"could not" not in toast` also passes on an EMPTY toast, and an empty
#: toast means she was told nothing at all.
FAILURE_TOASTS = (
    "Could not save — your entry is kept; try again.",   # app.js
    "Could not save — please try again.",                # post_bg.js, corrections.js
)

#: Every successful save is prefixed with this. It is the contract `assert_saved` checks.
SUCCESS_MARKER = "✓"


class _Toast(Protocol):
    """Only what :func:`assert_saved` needs, so the helper can be tested without a browser."""

    def wait_for(self, **kwargs: Any) -> Any: ...
    def text_content(self) -> str | None: ...


class _HasToast(Protocol):
    def locator(self, selector: str) -> _Toast: ...


def assert_saved(page: _HasToast, *, contains: str | None = None, timeout: int = 5000) -> str:
    """Assert the page reported a **successful** save, and return the toast text.

    ★ Three separate assertions, because each rules out a different way of being wrong:

    1. the toast is **not empty** — she was told something;
    2. it is **not** one of the known failure messages — what she was told was not a failure;
    3. it carries the success marker — it is a confirmation and not, say, the validation
       prompt *"When did you take this reading?"*, which is neither a save nor a failure.

    This is deliberately not the whole assertion. A flow test must also look at the
    database: a page can say ``✓`` and be wrong, and the row is the thing she is trusting
    the app to keep.
    """
    toast = page.locator("#toast")
    toast.wait_for(state="visible", timeout=timeout)

    # ★ Visible is not the same as *written*.
    #
    # `wait_for(state="visible")` returns immediately when a toast is already on screen —
    # exactly the situation after a failed attempt, where the failure message is still
    # showing when she presses Log again. The app then clears the text and writes the new
    # one, and a single read taken in between sees an empty string. That made
    # `test_a_lost_response_is_safe_to_retry` fail roughly two runs in three, reporting "the
    # toast is empty" and pointing at the retry logic rather than at this wait.
    #
    # A flaky test in this suite is worse than a missing one: it teaches the reader that red
    # is noise, so the next real red gets re-run instead of read.
    #
    # Polled with `text_content()` rather than Playwright's `expect()`, which needs a real
    # Locator — `_Toast` exists so this helper can be tested without a browser, and
    # `expect()` broke all seven of those tests with a ValueError. A fix that costs the
    # helper its own test coverage is not a fix.
    deadline = time.monotonic() + (timeout / 1000.0)
    text = (toast.text_content() or "").strip()
    while not text and time.monotonic() < deadline:
        time.sleep(0.05)
        text = (toast.text_content() or "").strip()

    assert text, "the toast is empty — she was told nothing at all"
    assert text not in FAILURE_TOASTS, f"the page reported a FAILURE, not a save: {text!r}"
    assert text.startswith(SUCCESS_MARKER), f"not a success confirmation: {text!r}"
    if contains is not None:
        assert contains in text, f"expected {contains!r} in the confirmation, got {text!r}"
    return text


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def e2e_db_path() -> Path:
    """The single SQLite file the live server writes to and the tests read back.

    ★ It is created **before** the server fixture and shared with it, so a test cannot end
    up asserting against a different database than the one it just wrote to — the S-102
    fixture bug, which made an a11y test pass and fail for reasons unrelated to the code.
    """
    return Path(tempfile.mkdtemp(prefix="bge2e-")) / "e2e.db"


@pytest.fixture(scope="session")
def live_server(e2e_db_path: Path) -> Iterator[str]:
    import uvicorn

    os.environ["BGAPP_DB_URL"] = f"sqlite:///{e2e_db_path}"

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
def db_session(live_server: str, e2e_db_path: Path) -> Iterator[Session]:
    """A read-back session on the server's own database.

    Depends on ``live_server`` so the schema exists by the time it opens. A fresh session
    per test, because SQLAlchemy caches identity per session and a stale one would report
    the row as it was before the click.
    """
    from data.db import create_all, make_engine, session_factory

    engine = make_engine(f"sqlite:///{e2e_db_path}")
    # The app creates the schema lazily, on the first request that opens a session. A test
    # that reads the database BEFORE its first write would otherwise fail on a missing
    # table — a fixture problem masquerading as a product one, and only when run alone.
    create_all(engine)
    with session_factory(engine)() as session:
        yield session


@pytest.fixture
def page(  # browser: tests/conftest.py
    browser: Browser, live_server: str, request: pytest.FixtureRequest
) -> Iterator[Page]:
    # S-1023: records a video + trace named after the test when BGAPP_BROWSER_ARTIFACTS is
    # set, and costs nothing when it is not.
    name = f"e2e-{request.node.name}"
    context = new_recorded_context(browser, name=name)
    pg = context.new_page()
    pg.goto(live_server + "/", wait_until="networkidle")
    try:
        yield pg
    finally:
        close_recorded_context(context, name=name)


@pytest.fixture
def browser_at(
    browser: Browser, request: pytest.FixtureRequest
) -> Iterator[Callable[[str], BrowserContext]]:
    """Open a browser context in a named IANA timezone.

    ★ "The phone is in India" is her actual configuration, not an exotic one. Every other
    fixture inherits the container's timezone, which is UTC — so a UTC round trip looks
    correct for the wrong reason and a timezone bug is invisible (S-1018).
    """
    contexts: list[tuple[BrowserContext, str]] = []

    def _open(timezone_id: str) -> BrowserContext:
        ctx = new_recorded_context(
            browser,
            name=f"e2e-{request.node.name}-{timezone_id.replace('/', '-')}",
            timezone_id=timezone_id,
            locale="en-IN",
        )
        contexts.append((ctx, timezone_id))
        return ctx

    try:
        yield _open
    finally:
        for ctx, tz in contexts:
            close_recorded_context(
                ctx, name=f"e2e-{request.node.name}-{tz.replace('/', '-')}"
            )
