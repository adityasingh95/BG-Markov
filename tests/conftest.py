"""Shared browser fixture for all Playwright suites (a11y + e2e).

The Playwright sync API cannot run two ``sync_playwright()`` contexts in one
process, so the browser is launched once here and shared across suites. Each
suite provides its own ``live_server`` and ``page``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright


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
