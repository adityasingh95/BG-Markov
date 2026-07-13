"""FastAPI app: serves the shared UI shell (S-102).

No clinical behaviour and no model output here — this module wires the base
Jinja2 layout, the vendored Pico.css and the accessible input primitives that
every later logging/readout story is built on. Binds to 127.0.0.1 only (see
06 §7); no auth in v1.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app = FastAPI(title="BG-Markov", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """The base-layout demonstration page.

    It exercises the accessible primitives — numeric field macro, dish search
    (not a dropdown), a risk cue that is legible without colour — so the a11y
    suite has a real page to audit. The real logging forms are S-301+ and reuse
    these primitives.
    """
    return templates.TemplateResponse(request, "index.html")
