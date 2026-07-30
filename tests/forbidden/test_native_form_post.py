"""S-1020 (SDET) — no template posts a native form to a JSON endpoint. RED first.

`basal.html` and `profile.html` are plain HTML forms with `method="post"
action="/api/…"` and **no script**. A native submit sends
`application/x-www-form-urlencoded`; the endpoints take a JSON body; FastAPI returns 422 and
**the browser navigates to it**. She leaves the app and lands on:

    {"detail":[{"type":"model_attributes_type","loc":["body"], …}]}

Both endpoints are covered by integration tests that post JSON directly. Both pass. Neither
has ever been reached from a browser.

★ This guard is the **class**, not the instance: any future form wired the same way fails
here before anyone has to notice it in a demo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import core

_TEMPLATES = Path(core.__file__).resolve().parents[1] / "api" / "templates"

_FORM = re.compile(r"<form\b[^>]*>", flags=re.S)
_ACTION = re.compile(r'action="([^"]*)"')
_SCRIPT = re.compile(r"<script\b[^>]*\bsrc=")


def _api_forms(source: str) -> list[str]:
    """Every `<form>` in this template whose action posts to the JSON API."""
    forms: list[str] = []
    for tag in _FORM.findall(source):
        action = _ACTION.search(tag)
        if action and action.group(1).startswith("/api/"):
            forms.append(tag)
    return forms


def _templates() -> list[Path]:
    return sorted(_TEMPLATES.glob("*.html"))


@pytest.mark.parametrize("template", _templates(), ids=lambda p: p.name)
def test_a_form_posting_to_the_api_has_a_script_to_send_it(template: Path) -> None:
    """★ A `<form action="/api/…">` with no script is a 422 and a lost entry.

    The check is for a script **in this template**. `base.html`'s shared helpers do not
    count: they define primitives and submit nothing, so a template that inherits them and
    forgets its own handler is exactly the broken case.
    """
    source = template.read_text(encoding="utf-8")
    forms = _api_forms(source)
    if not forms:
        pytest.skip("no /api/ form in this template")
    assert _SCRIPT.search(source), (
        f"{template.name} posts a form to the JSON API with no script to send it. "
        "The browser will send urlencoded, get a 422, and NAVIGATE to the JSON error."
    )


@pytest.mark.parametrize("template", _templates(), ids=lambda p: p.name)
def test_a_form_posting_to_the_api_declares_itself(template: Path) -> None:
    """Every such form carries `data-json-form`, so the shared submitter can find it and a
    reader can see at a glance that it is not a native submit."""
    source = template.read_text(encoding="utf-8")
    offenders = [tag for tag in _api_forms(source) if "data-json-form" not in tag]
    if not _api_forms(source):
        pytest.skip("no /api/ form in this template")
    # Forms with a bespoke handler are exempt by naming their own script explicitly.
    bespoke = {"index.html", "post_bg.html", "corrections.html"}
    if template.name in bespoke:
        pytest.skip("bespoke handler; see test_bespoke_handlers_are_still_declared")
    assert not offenders, f"{template.name}: form(s) without data-json-form: {offenders}"


def test_the_guard_bites_on_a_native_form() -> None:
    """The exact shape of `basal.html` before the fix."""
    planted = """{% extends "base.html" %}
    {% block content %}
    <form method="post" action="/api/basal" id="basal-form">
      <input name="units" />
      <button type="submit">Save</button>
    </form>
    {% endblock %}"""
    assert _api_forms(planted), "the guard cannot see the form it exists to catch"
    assert not _SCRIPT.search(planted), "the guard would not have flagged the missing script"


def test_the_guard_does_not_fire_on_a_non_api_form() -> None:
    """`/bolus` is a GET form to a *page*, and a native submit is exactly right there —
    it renders a suggestion and stores nothing."""
    planted = '<form method="get" action="/bolus"><button>Work it out</button></form>'
    assert not _api_forms(planted)


def test_bespoke_handlers_are_still_declared() -> None:
    """★ The three forms with their own scripts must still be reachable by name.

    Without this, "has a bespoke handler" becomes an unfalsifiable exemption: any template
    could claim it by having any script tag at all.
    """
    expected = {
        "index.html": "app.js",
        "post_bg.html": "post_bg.js",
        "corrections.html": "corrections.js",
    }
    for name, script in expected.items():
        source = (_TEMPLATES / name).read_text(encoding="utf-8")
        assert script in source, f"{name} no longer loads its handler {script}"
