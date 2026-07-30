"""Drive the **real browser UI** end to end against a seeded DEMO database. NOT patient data.

`scripts/demo_scenarios.py` exercises the same system through FastAPI's `TestClient` — real
routes, real invariants, but **no browser**. Everything between the button and the request
body is untested by it: the form, the JavaScript that builds the payload, the content type it
posts, and whether the page tells her anything afterwards.

★ That gap is not cosmetic. Her only way into this system is a phone browser. A route that
works perfectly for `TestClient` and 422s for a real form submit is, to her, a route that
does not work.

This script walks the actual screens in Chromium, screenshots each one, and asserts against
the database afterwards — so what is claimed is what the browser did, not what the API would
have done.

Usage:
    python -m scripts.demo_ui --db demo-ui.db --out demo-ui-shots
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import re
import socket
import threading
import time
from typing import Any

import httpx
from playwright.sync_api import Page, sync_playwright
from sqlalchemy import func, select

NOW = dt.datetime(2026, 7, 30, 12, 0)

_PASS = "  ok  "
_FAIL = " FAIL "
_NOTE = "  ★   "


def h(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def sub(title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 72 - len(title)))


def check(ok: bool, message: str) -> bool:
    print(f"[{_PASS if ok else _FAIL}] {message}")
    return ok


def note(message: str) -> None:
    print(f"[{_NOTE}] {message}")


# --------------------------------------------------------------------------- server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_server(db_path: str) -> tuple[str, Any, threading.Thread]:
    """Serve the real app on a background uvicorn thread against `db_path`.

    `BGAPP_DB_URL` is set before `api.deps` builds its engine, and `_engine` is cleared,
    because it is a module-level cache: an earlier import would otherwise keep serving a
    different database while every screenshot looked correct.
    """
    import uvicorn

    os.environ["BGAPP_DB_URL"] = f"sqlite:///{db_path}"
    import api.deps as deps

    deps._engine = None
    from api.app import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20.0
    while time.time() < deadline:
        if server.started:
            try:
                httpx.get(base + "/", timeout=1.0)
                break
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    else:  # pragma: no cover - only if the server never comes up
        raise RuntimeError("live server did not start")
    return base, server, thread


# --------------------------------------------------------------------------- fixtures


def ensure_db(db_path: str, *, days: int, seed_value: int) -> None:
    from scripts.seed_demo_db import seed

    if pathlib.Path(db_path).exists():
        print(f"  using existing database {db_path}")
        return
    counts = seed(db_path, days=days, seed_value=seed_value, end=NOW.date())
    print(f"  seeded {db_path}: {counts}")


def ensure_promoted_model(db_path: str) -> str | None:
    """Fit and promote a model so the live prediction path has something to serve.

    Promotion is a **demo** act performed directly, exactly as `demo_scenarios.py` does it:
    the operator route refuses while Gate 1 is shut, and the point of this walkthrough is to
    show the screens in the state that exists *after* a promotion, with Gate 1 still shut.
    """
    from data.db import make_engine, session_factory
    from data.tables import ModelArtifact
    from models.refit import run_refit

    engine = make_engine(f"sqlite:///{db_path}")
    with session_factory(engine)() as session:
        promoted = session.scalars(
            select(ModelArtifact).where(ModelArtifact.is_promoted.is_(True))
        ).first()
        if promoted is not None:
            print(f"  already promoted: {promoted.version}")
            return str(promoted.version)
        artifact = run_refit(session, as_of=NOW)
        artifact.is_promoted = True
        session.commit()
        print(f"  fitted and promoted: {artifact.version}")
        return str(artifact.version)


def counts(db_path: str) -> dict[str, int]:
    from data.db import make_engine, session_factory
    from data.tables import BolusLog, MealEvent, PredictionLog

    engine = make_engine(f"sqlite:///{db_path}")
    with session_factory(engine)() as session:
        return {
            "meals": session.scalar(select(func.count()).select_from(MealEvent)) or 0,
            "boluses": session.scalar(select(func.count()).select_from(BolusLog)) or 0,
            "predictions": session.scalar(select(func.count()).select_from(PredictionLog)) or 0,
        }


def newest_meal(db_path: str) -> Any:
    from data.db import make_engine, session_factory
    from data.tables import MealEvent

    engine = make_engine(f"sqlite:///{db_path}")
    with session_factory(engine)() as session:
        meal = session.scalars(
            select(MealEvent).order_by(MealEvent.meal_id.desc())
        ).first()
        if meal is None:
            return None
        return {
            "meal_id": meal.meal_id,
            "datetime": meal.datetime,
            "logged_at": meal.logged_at,
            "pre_bg": meal.pre_bg,
            "carbs_g": meal.carbs_g,
            "meal_bolus_units": meal.meal_bolus_units,
            "bolus_offset_min": meal.bolus_offset_min,
            "idempotency_key": meal.idempotency_key,
        }


# --------------------------------------------------------------------------- walkthrough


class Shots:
    def __init__(self, out: pathlib.Path) -> None:
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.paths: list[pathlib.Path] = []

    def take(self, page: Page, name: str, *, full: bool = True) -> pathlib.Path:
        self.n += 1
        path = self.out / f"{self.n:02d}-{name}.png"
        page.screenshot(path=str(path), full_page=full)
        self.paths.append(path)
        print(f"        screenshot → {path}")
        return path


def step_1_log_a_meal(page: Page, base: str, shots: Shots, db: str) -> int | None:
    h("UI 1 — She logs a meal on the phone")
    before = counts(db)
    page.goto(base + "/", wait_until="networkidle")
    shots.take(page, "meal-form-empty")

    fav = page.locator(".chip.favourite").first
    fav_name = fav.inner_text().strip()
    fav.click()
    print(f"        tapped favourite: {fav_name}")

    # ★ ADR-8: the reported mealtime is TYPED, not taken from the clock. She logs at the
    # laptop later, so the browser's `now` is the wrong number for a clinical timestamp.
    reported = NOW - dt.timedelta(minutes=40)
    page.fill("#meal-time", reported.strftime("%Y-%m-%dT%H:%M"))
    page.fill("#f-pre_bg", "142")
    page.fill("#f-meal_bolus_units", "5")
    page.locator(".timing-preset", has_text="10 min before").click()
    shots.take(page, "meal-form-filled")

    page.locator("button.primary").click()
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
    toast = page.locator("#toast").inner_text().strip()
    print(f'        toast: "{toast}"')
    shots.take(page, "meal-logged-toast")

    after = counts(db)
    check(after["meals"] == before["meals"] + 1, "one meal row written by the browser submit")
    check(after["boluses"] == before["boluses"] + 1, "one bolus row written (REQ-006)")
    meal = newest_meal(db)
    if meal is None:
        return None
    check(
        meal["datetime"] == reported,
        f"reported mealtime stored as typed ({meal['datetime']}), not the clock (ADR-8)",
    )
    check(
        meal["logged_at"] != meal["datetime"],
        f"logged_at is separate ({meal['logged_at']}) — the transcription lag is visible",
    )
    check(meal["bolus_offset_min"] == -10, "bolus timing came from the chip, not a default")
    check(meal["carbs_g"] > 0, f"macros populated from the favourite (carbs {meal['carbs_g']} g)")

    sub("INV-2 — nothing on this page is model output")
    body = page.content().lower()
    leaks = [w for w in ("probability", "predict", "risk of", "% chance", "hypo risk")
             if w in body]
    check(not leaks, f"no model output in the rendered page (searched, found {leaks or 'none'})")
    check(
        after["predictions"] > before["predictions"],
        f"prediction WAS written to prediction_log ({before['predictions']} → "
        f"{after['predictions']}) — INV-9, and she never saw it",
    )
    return int(meal["meal_id"])


def step_2_double_tap(page: Page, base: str, shots: Shots, db: str) -> None:
    h("UI 2 — She taps 'Log meal' twice (the shaky-hands case)")
    before = counts(db)
    page.goto(base + "/", wait_until="networkidle")
    page.locator(".chip.favourite").first.click()
    page.fill("#meal-time", (NOW - dt.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M"))
    page.fill("#f-pre_bg", "131")
    page.fill("#f-meal_bolus_units", "4")
    page.locator(".timing-preset", has_text="Just before").click()

    button = page.locator("button.primary")
    button.click()
    button.click()  # the second tap, immediately
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
    page.wait_for_timeout(1200)  # let both requests land
    shots.take(page, "meal-double-tap")

    after = counts(db)
    meals_added = after["meals"] - before["meals"]
    boluses_added = after["boluses"] - before["boluses"]
    print(f"        meals added: {meals_added}   boluses added: {boluses_added}")
    ok = check(
        meals_added == 1 and boluses_added == 1,
        "a double tap produced ONE meal and ONE bolus",
    )
    if not ok:
        note(
            "The server-side idempotency added by S-1016 did not fire, because "
            "`app.js` mints a FRESH `crypto.randomUUID()` inside `payload()` — which is "
            "called once per submit. Two taps ⇒ two keys ⇒ two meals ⇒ two boluses."
        )
        note(
            "A duplicated bolus corrupts IOB for every later calculation, and IOB is "
            "subtracted from the dose: the calculator will then under-dose her."
        )


def step_3_post_bg(page: Page, base: str, shots: Shots, meal_id: int, db: str) -> None:
    h("UI 3 — Two hours later: the post-meal reading")
    from data.db import make_engine, session_factory
    from data.tables import MealEvent

    engine = make_engine(f"sqlite:///{db}")
    page.goto(base + f"/meals/{meal_id}/post-bg", wait_until="networkidle")
    prefilled = page.input_value("#post-bg-time")
    print(f"        reading time pre-filled with the EXPECTED time: {prefilled} (editable)")
    shots.take(page, "post-bg-form")

    page.fill("#f-post_bg", "74")
    page.locator("details.optional summary").click()
    page.locator("[data-hypo]").check()
    page.fill("#f-hypo_treatment_g", "15")
    page.locator("button.primary").click()
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
    toast = page.locator("#toast").inner_text().strip()
    print(f'        toast: "{toast}"')
    shots.take(page, "post-bg-saved-hypo")

    with session_factory(engine)() as s:
        meal = s.get(MealEvent, meal_id)
        stored = None if meal is None else meal.post_bg
    ok = check(stored == 74, f"the reading was saved (post_bg in the database: {stored})")
    if not ok:
        note(
            "`post_bg.js` posts `new Date(iso).toISOString()` — a timezone-AWARE instant. "
            "`meal.datetime` read back from SQLite is naive, so `elapsed_min` subtracts an "
            "aware from a naive datetime and raises TypeError → HTTP 500."
        )
        note(
            "★ This is the OUTCOME capture path. No post-BG means no outcome, no training "
            "row, nothing to score, and Gate 1's 90-day clock measures predictions that "
            "can never be graded. The API tests pass because `TestClient` posts naive "
            "ISO strings; only a browser sends the Z."
        )
    else:
        note(
            "She treated a low. INV-7: this meal is excluded from the outcome regression "
            "and RETAINED as a hypo event — the lows are what the system exists to predict."
        )


def step_4_readout(page: Page, base: str, shots: Shots, meal_id: int) -> None:
    h("UI 4 — What she is shown about that meal (INV-2)")
    page.goto(base + f"/meals/{meal_id}/readout", wait_until="networkidle")
    text = page.locator("main").inner_text().strip()
    print("        page says:")
    for line in text.splitlines():
        if line.strip():
            print(f"          {line.strip()}")
    shots.take(page, "readout-gate-shut")
    lowered = text.lower()
    check(
        not any(w in lowered for w in ("units", " u ", "dose", "inject")),
        "no dose word anywhere on the patient readout",
    )
    check(
        "%" not in text,
        "no probability shown — Gate 1 is shut, so there is no model output to show",
    )


def step_5_calculator(page: Page, base: str, shots: Shots) -> None:
    h("UI 5 — The bolus calculator, driven from the form")

    def work_out(carbs: str, bg: str, label: str) -> str:
        page.goto(base + "/bolus", wait_until="networkidle")
        page.fill("#at", NOW.strftime("%Y-%m-%dT%H:%M"))
        page.fill("#carbs_g", carbs)
        page.fill("#current_bg", bg)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        out = page.locator("main").inner_text().strip()
        shots.take(page, label)
        return out

    sub("a normal meal")
    out = work_out("60", "165", "calculator-suggestion")
    for line in out.splitlines():
        if line.strip():
            print(f"          {line.strip()}")

    sub("INV-4 — she is low")
    out = work_out("60", "72", "calculator-inv4-low")
    for line in out.splitlines():
        if line.strip():
            print(f"          {line.strip()}")
    check("treat the low" in out.lower(), "the page refuses to calculate and says treat it")
    # A dose-shaped token — "0.71 U", "15.00 U". The refusal must show none of them.
    doses = re.findall(r"\b\d+(?:\.\d+)?\s*U\b", out)
    check(not doses, f"no dose number appears at all below BG 80 (found {doses or 'none'})")
    check("insulin on board" not in out.lower(), "not even IOB is computed — nothing is")

    sub("INV-3 — an implausible carb entry")
    out = work_out("900", "300", "calculator-inv3-cap")
    for line in out.splitlines():
        if line.strip():
            print(f"          {line.strip()}")
    check("15" in out, "the dose is capped at MAX_BOLUS_U (15 U) and the cap is stated")


def step_6_basal(page: Page, base: str, shots: Shots, db: str) -> None:
    h("UI 6 — Recording the daily Tresiba dose")
    from data.db import make_engine, session_factory
    from data.tables import BasalLog

    engine = make_engine(f"sqlite:///{db}")
    with session_factory(engine)() as s:
        before = s.scalar(select(func.count()).select_from(BasalLog)) or 0

    page.goto(base + "/basal", wait_until="networkidle")
    shots.take(page, "basal-form")
    # ★ A date the seed does NOT already cover. `record_basal` treats a repeat date as a
    # CORRECTION, not a second dose (S-1013), so re-posting a seeded day would leave the row
    # count unchanged and the demo would report a defect that is the rule working.
    when = (NOW + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    page.fill("#date", when)
    page.fill("#units", "26")
    page.fill("#time_taken", "22:15")
    page.locator('button[type="submit"]').click()
    try:
        page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
        print(f'        toast: "{page.locator("#toast").inner_text().strip()}"')
    except Exception:  # noqa: BLE001 - the demo reports, it does not assert
        print("        no toast appeared")
    print(f"        after submit the browser is still at: {page.url}")
    shots.take(page, "basal-after-submit")

    with session_factory(engine)() as s:
        after = s.scalar(select(func.count()).select_from(BasalLog)) or 0
    ok = check(after == before + 1, "the basal dose was recorded")
    if not ok:
        note(
            "`basal.html` is a PLAIN HTML form posting to a JSON endpoint, and no script "
            "intercepts it. The browser sends application/x-www-form-urlencoded; FastAPI "
            "rejects it 422 and she is shown a raw JSON error."
        )
        note(
            "Basal is not optional data: `effective_basal` is an EWMA over the last doses "
            "(Tresiba, ~42 h action). Days she cannot record are days the feature is stale."
        )


def step_6b_correction(page: Page, base: str, shots: Shots, db: str) -> None:
    h("UI 6b — A correction bolus with no food (the clean ISF reading)")
    from data.db import make_engine, session_factory
    from data.tables import CorrectionEvent

    engine = make_engine(f"sqlite:///{db}")
    with session_factory(engine)() as s:
        before = s.scalar(select(func.count()).select_from(CorrectionEvent)) or 0

    page.goto(base + "/corrections", wait_until="networkidle")
    shots.take(page, "corrections-form")
    page.fill("#f-bg_before", "244")
    page.fill("#f-units", "2")
    page.fill("#correction-time", (NOW - dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M"))
    page.locator('input[name="food_in_window"][value="no"]').check()
    page.locator("button.primary").click()
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
    print(f'        toast: "{page.locator("#toast").inner_text().strip()}"')
    shots.take(page, "corrections-saved")

    with session_factory(engine)() as s:
        after = s.scalar(select(func.count()).select_from(CorrectionEvent)) or 0
    check(after == before + 1, "the correction event was recorded from the browser")


def step_7_operator(page: Page, base: str, shots: Shots, db: str) -> None:
    h("UI 7 — The operator's screens")
    sub("/operator — the gate dashboard")
    page.goto(base + "/operator", wait_until="networkidle")
    text = page.locator("main").inner_text()
    for line in text.splitlines()[:28]:
        if line.strip():
            print(f"          {line.strip()}")
    shots.take(page, "operator-gate")

    sub("/operator/shadow — what the model is doing where she cannot see it")
    page.goto(base + "/operator/shadow", wait_until="networkidle")
    text = page.locator("main").inner_text()
    for line in text.splitlines()[:32]:
        if line.strip():
            print(f"          {line.strip()}")
    shots.take(page, "operator-shadow")

    from data.db import make_engine, session_factory
    from data.tables import ModelArtifact

    engine = make_engine(f"sqlite:///{db}")
    with session_factory(engine)() as s:
        fitted = s.scalar(select(func.count()).select_from(ModelArtifact)) or 0
    ok = check(
        not (fitted and "no model has been fitted yet" in text.lower()),
        f"the empty-state copy matches reality ({fitted} artifact(s) exist)",
    )
    if not ok:
        note(
            "The page says 'No model has been fitted yet' while a fitted, PROMOTED "
            "artifact exists. The real reason the panel is empty is that fewer than 10 "
            "predictions have been scored — a different statement, and the one an "
            "operator needs in order to know what to do next."
        )

    sub("/operator/profile — the clinical constants, versioned")
    page.goto(base + "/operator/profile", wait_until="networkidle")
    text = page.locator("main").inner_text()
    for line in text.splitlines()[:24]:
        if line.strip():
            print(f"          {line.strip()}")
    shots.take(page, "operator-profile")


def step_9_her_timezone(browser: Any, base: str, shots: Shots, db: str) -> None:
    """★ The same form, from a browser whose clock is where she actually lives.

    Every earlier step ran in the container's timezone, which happens to be UTC — so the
    round trip looked correct for the wrong reason. `app.js` converts the typed local time
    with `new Date(iso).toISOString()`, and the server stores the instant it is given.
    """
    h("UI 9 — The same form, on a phone set to Asia/Kolkata (UTC+5:30)")
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        timezone_id="Asia/Kolkata",
        locale="en-IN",
    )
    page = context.new_page()
    typed = "2026-07-29T08:00"
    page.goto(base + "/", wait_until="networkidle")
    page.locator(".chip.favourite").first.click()
    page.fill("#meal-time", typed)
    page.fill("#f-pre_bg", "127")
    page.fill("#f-meal_bolus_units", "4")
    page.locator(".timing-preset", has_text="Just before").click()
    page.locator("button.primary").click()
    page.wait_for_selector("#toast:not([hidden])", timeout=10_000)
    shots.take(page, "phone-kolkata-logged")

    meal = newest_meal(db)
    stored = None if meal is None else meal["datetime"]
    print(f"        she typed:  {typed.replace('T', ' ')}  (breakfast)")
    print(f"        stored as:  {stored}")
    ok = check(
        stored is not None and stored.strftime("%Y-%m-%dT%H:%M") == typed,
        "the reported mealtime is stored as the wall-clock time she typed",
    )
    if not ok:
        note(
            "The reported mealtime is shifted by her UTC offset. `app.js` sends "
            "`new Date(local).toISOString()` and the server persists that instant, so a "
            "breakfast at 08:00 IST lands in the database at 02:30 — and is read back "
            "later as a naive local time of 02:30."
        )
        note(
            "★ ADR-8 forbids inventing a clinical timestamp. This does not invent one — "
            "it silently RELABELS the one she reported. `meal_type` is decided in the "
            "browser from her local time, so the row also says 'breakfast' at 02:30: the "
            "corruption is self-inconsistent inside a single row and still raises nothing."
        )
    context.close()


def step_8_phone_and_zoom(page: Page, base: str, shots: Shots) -> None:
    h("UI 8 — On the phone, and at 200% zoom")
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(base + "/", wait_until="networkidle")
    shots.take(page, "phone-meal-form")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    check(overflow <= 1, f"no horizontal scroll on a 390px screen (overflow {overflow}px)")

    page.set_viewport_size({"width": 640, "height": 900})
    page.evaluate("() => { document.documentElement.style.fontSize = '32px'; }")
    page.wait_for_timeout(200)
    shots.take(page, "zoom-200pct")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    check(overflow <= 1, f"no horizontal scroll at 200% text zoom (overflow {overflow}px)")
    page.evaluate("() => { document.documentElement.style.fontSize = ''; }")
    page.set_viewport_size({"width": 1280, "height": 900})


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="demo_ui", description="Browser walkthrough of the UI")
    p.add_argument("--db", default="demo-ui.db")
    p.add_argument("--out", default="demo-ui-shots")
    p.add_argument("--days", type=int, default=240)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args(argv)

    h("SETUP — a seeded demo database and a promoted model")
    ensure_db(args.db, days=args.days, seed_value=args.seed)
    ensure_promoted_model(args.db)
    print(f"  starting counts: {counts(args.db)}")

    base, server, thread = start_server(args.db)
    print(f"  serving on {base}")
    shots = Shots(pathlib.Path(args.out))

    try:
        with sync_playwright() as pw:
            executable = None
            root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
            if root and pathlib.Path(root, "chromium").exists():
                executable = str(pathlib.Path(root, "chromium"))
            browser = pw.chromium.launch(executable_path=executable)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.on("pageerror", lambda e: print(f"        [js error] {e}"))

            meal_id = step_1_log_a_meal(page, base, shots, args.db)
            step_2_double_tap(page, base, shots, args.db)
            if meal_id is not None:
                step_3_post_bg(page, base, shots, meal_id, args.db)
                step_4_readout(page, base, shots, meal_id)
            step_5_calculator(page, base, shots)
            step_6_basal(page, base, shots, args.db)
            step_6b_correction(page, base, shots, args.db)
            step_7_operator(page, base, shots, args.db)
            step_8_phone_and_zoom(page, base, shots)
            step_9_her_timezone(browser, base, shots, args.db)

            context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    h("DONE")
    print(f"  {shots.n} screenshots in {shots.out}/")
    print(f"  final counts: {counts(args.db)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
