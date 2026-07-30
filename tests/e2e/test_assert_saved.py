"""S-1021 (SDET) — the assertion that the assertion works.

`assert_saved` is the only thing standing between "the write worked" and "a toast
appeared". A guard nobody has watched fail is not a guard, so this feeds it every toast the
application can actually produce and pins which ones it must reject.

No browser: the helper is duck-typed on ``page.locator("#toast")`` precisely so this can
run as a unit test and stay honest about *why* it rejects each string.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import FAILURE_TOASTS, SUCCESS_MARKER, assert_saved

pytestmark = pytest.mark.e2e


class _FakeToast:
    def __init__(self, text: str) -> None:
        self._text = text

    def wait_for(self, **_: Any) -> None:
        return None

    def text_content(self) -> str:
        return self._text


class _FakePage:
    def __init__(self, text: str) -> None:
        self._toast = _FakeToast(text)

    def locator(self, selector: str) -> _FakeToast:
        assert selector == "#toast"
        return self._toast


def test_it_accepts_a_real_success_toast() -> None:
    assert_saved(_FakePage("✓ Logged. Set a phone alarm for 1:20 PM to test."))
    assert_saved(_FakePage("✓ Saved — 121 min after your meal."))


@pytest.mark.parametrize("copy", FAILURE_TOASTS)
def test_it_rejects_the_real_failure_copy(copy: str) -> None:
    """★ The exact string the post-BG form was showing while its test passed."""
    with pytest.raises(AssertionError, match="FAILURE"):
        assert_saved(_FakePage(copy))


def test_it_rejects_an_empty_toast() -> None:
    """★ The obvious weakening — `"could not" not in text` — passes here. This must not.

    An empty toast is the worst outcome of the three: she was told nothing, so she cannot
    even know to retry.
    """
    with pytest.raises(AssertionError, match="empty"):
        assert_saved(_FakePage("   "))


def test_it_rejects_a_validation_prompt() -> None:
    """A prompt is neither a save nor a failure, and must not read as either."""
    with pytest.raises(AssertionError, match="not a success"):
        assert_saved(_FakePage("When did you take this reading? Please add the time."))


def test_it_rejects_a_success_marker_that_is_only_a_substring() -> None:
    with pytest.raises(AssertionError, match="not a success"):
        assert_saved(_FakePage("Something went wrong ✓"))


def test_contains_narrows_further() -> None:
    with pytest.raises(AssertionError, match="expected"):
        assert_saved(_FakePage("✓ Saved."), contains="121 min")


_STATIC = Path(__file__).resolve().parents[2] / "api" / "static"


@pytest.mark.parametrize("script", ["app.js", "post_bg.js", "corrections.js"])
def test_the_failure_copy_in_the_page_is_still_the_copy_this_helper_rejects(script: str) -> None:
    """★ Drift guard.

    `assert_saved` rejects string literals. If the page's failure copy is reworded and this
    list is not, the helper silently stops rejecting anything and every flow test goes green
    again — the exact failure this story exists to end, restored by a copy edit.
    """
    source = (_STATIC / script).read_text(encoding="utf-8")
    assert any(copy in source for copy in FAILURE_TOASTS), (
        f"{script} no longer contains any failure copy that assert_saved knows about; "
        "update FAILURE_TOASTS in tests/e2e/conftest.py"
    )


@pytest.mark.parametrize("script", ["app.js", "post_bg.js", "corrections.js"])
def test_every_success_toast_in_the_page_carries_the_marker(script: str) -> None:
    """★ The other half of the drift guard: a success path that forgets the ``✓``.

    Without this, a success message that does not start with the marker fails
    `assert_saved` and reads to whoever hits it as *"the feature is broken"*, when the
    feature is fine and the copy is not.
    """
    source = (_STATIC / script).read_text(encoding="utf-8")
    success_lines = [
        line.strip()
        for line in source.splitlines()
        if "toast.textContent" in line and "Could not save" not in line and "Please" not in line
    ]
    assert success_lines, f"no success toast found in {script}"
    for line in success_lines:
        # ★ The marker must be the START of the assigned string, not merely present in the
        # line. `= res.message || "✓ Saved."` contains a ✓ and renders the server's message
        # without one — which is how `corrections.js` shipped a success toast that
        # `assert_saved` rejects and a human reads as "it worked".
        assert re.search(rf'toast\.textContent\s*=\s*"{SUCCESS_MARKER}', line), (
            f"the success toast does not BEGIN with the success marker: {line}"
        )
