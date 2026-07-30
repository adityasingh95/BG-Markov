"""S-1019 (SDET) — the idempotency key is not minted at submit time. RED first.

★ The whole defect in one line:

    function payload() {
      return { idempotency_key: crypto.randomUUID(), ... };
    }

`payload()` runs once per submit, so every submit is a new submission by construction and
the server's duplicate check can never fire. The server half was correct and unreachable.

A cheap grep guard, in the same spirit as the rest of this directory: the expensive test is
the browser double-tap, and this one says *why* it broke the moment it breaks again.
"""

from __future__ import annotations

import re
from pathlib import Path

import core

_STATIC = Path(core.__file__).resolve().parents[1] / "api" / "static"

#: The minting call, in any of its spellings.
_MINT = re.compile(r"randomUUID\s*\(|\bDate\.now\s*\(\s*\)\s*\)?\s*;?\s*$")


def _payload_builder(source: str) -> list[str]:
    """The body of `function payload()`, or the object literal posted as the body."""
    match = re.search(r"function payload\s*\([^)]*\)\s*\{(.*?)\n  \}", source, flags=re.S)
    return match.group(1).splitlines() if match else []


def test_the_meal_key_is_not_minted_inside_the_payload_builder() -> None:
    """★ The exact place, because the exact place is what makes it wrong.

    Minting a key is fine. Minting it *per submit* is what turns S-1016's guard into
    decoration.
    """
    source = (_STATIC / "app.js").read_text(encoding="utf-8")
    body = _payload_builder(source)
    assert body, "could not find the payload builder in app.js — has it been renamed?"
    offenders = [line.strip() for line in body if "randomUUID" in line]
    assert not offenders, (
        f"the idempotency key is minted inside payload(): {offenders}. payload() runs once "
        "per submit, so two taps produce two keys and the server cannot tell them apart. "
        "Mint once per form fill; rotate only after a confirmed save (S-1019)."
    )


def test_the_guard_bites_on_the_line_that_caused_this() -> None:
    planted = """function payload() {
    var iso = timeInput.value;
    return {
      idempotency_key: crypto.randomUUID(),
      datetime: iso
    };
  }"""
    body = _payload_builder(planted)
    assert body, "the guard cannot even find a planted payload builder"
    assert any("randomUUID" in line for line in body), "the guard does not fire on the cause"


def test_a_key_minted_outside_the_builder_is_allowed() -> None:
    """The fix must be permitted, or the guard just teaches people to delete it."""
    planted = """var submissionKey = newKey();
  function payload() {
    return {
      idempotency_key: submissionKey,
      datetime: iso
    };
  }"""
    body = _payload_builder(planted)
    assert body
    assert not any("randomUUID" in line for line in body)


def test_every_form_that_writes_a_bolus_sends_a_key() -> None:
    """★ The scope rule, asserted rather than remembered.

    A form that creates a `bolus_log` row must send an idempotency key. That is the whole
    criterion: a duplicated bolus overstates IOB and the calculator subtracts IOB.
    """
    for script in ("app.js", "corrections.js"):
        source = (_STATIC / script).read_text(encoding="utf-8")
        assert "idempotency_key" in source, (
            f"{script} posts a bolus-creating request without an idempotency key"
        )
