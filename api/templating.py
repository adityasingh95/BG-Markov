"""The one `Jinja2Templates` instance (S-1024).

There used to be two — `api/app.py` and `api/bolus.py` — which is the shape of every gap
this epic found: a context added to one and not the other, invisible until someone opens
the page it was not added to.

★ The demo banner is a **context processor** on this single object, so it reaches every
page that is rendered, including pages nobody has written yet. A per-template opt-in would
be forgotten on the next screen anyone adds, and the screen they forget is the one the next
reader happens to open.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from data.provenance import DEMO_BANNER_MARK, is_demo_database

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _provenance(request: Request) -> dict[str, Any]:
    """Tell every page whether it is rendering synthetic data.

    ★ Reads the flag off ``request.state``, set by :func:`provenance_middleware` from **the
    same database the request itself is using**. The first attempt opened its own session
    from `api.deps` and was wrong the moment anything pointed the request elsewhere — a
    banner describing a different file than the page is worse than no banner, because it is
    confidently mislabelled.

    Read **per request**, never cached: the app is pointed at a database by environment, and
    a value computed at startup would survive a switch and describe the wrong file. Same
    reasoning as ADR-7 — evaluate live.
    """
    demo = bool(getattr(request.state, "is_demo_data", False))
    return {"is_demo_data": demo, "demo_banner_mark": DEMO_BANNER_MARK}


async def provenance_middleware(request: Request, call_next: Any) -> Any:
    """Resolve "is this synthetic data?" once per request, from the request's own database.

    ★ It goes through ``app.dependency_overrides`` exactly as a route dependency would, so
    the banner and the page can never disagree about which database they are looking at.
    A test that points a route at one file and the banner at another would prove nothing
    about production, and production is where the mislabelling would matter.

    Fails **quiet**: an unreadable or pre-migration database yields no banner rather than an
    exception. This is a caption, and a caption must never be the reason her logging screen
    fails to render — the seeder-always-marks test is what makes that default safe.
    """
    from api.deps import get_session

    request.state.is_demo_data = False
    try:
        from api.app import app as _app

        provider = _app.dependency_overrides.get(get_session, get_session)
        gen = provider()
        session = next(gen)
        try:
            request.state.is_demo_data = is_demo_database(session)
        finally:
            gen.close()
    except Exception:  # noqa: BLE001 - a caption must never break a page; see above
        request.state.is_demo_data = False
    return await call_next(request)


templates = Jinja2Templates(directory=str(_TEMPLATE_DIR), context_processors=[_provenance])
