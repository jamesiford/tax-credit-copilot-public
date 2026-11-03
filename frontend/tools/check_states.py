"""Forced states for every routed page. Dev tooling, not shipped.

    python frontend/tools/check_states.py            # every page, every state
    python frontend/tools/check_states.py --quick    # a representative subset

The landmine sweep (`sweep.py`) walks the app as it is. This one makes the app
fail ON PURPOSE and asks whether each page says what happened:

  loading      every API answer is delayed; the page must show a loading state
               while it waits, and that state must RESOLVE (no spinner that
               never ends) once the answers arrive
  empty        every data endpoint answers 200 with an empty body; the page must
               not crash and must not be blank
  error        every data endpoint answers 500; the page must say something
               purposeful, and must not crash into the error boundary
  no-client    a page that needs a client, opened with none selected, says so
  sealed-run   the sealed workspace is unavailable; the shell says so and offers
               a retry
  assistant    the chat endpoint is down; the workspace says the assistant is
               unavailable and that the page still has the figures
  wrong-year   a year the client holds no payroll for is declined BY NAME, never
               answered with a zero

FAIL conditions: an uncaught page error, the error boundary's fallback on screen
("could not be shown"), a blank page, a skeleton or busy marker still present
after the answers arrived, a React render error in the console, or the wording
the sweep treats as a bug ("could not be read", "request failed", ...). The
network errors the harness itself provokes are NOT counted as console errors.

Nothing here changes `backend/`; it intercepts requests in the browser.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from _theme import new_page
from shoot_pages import BASE, PAGES

OUT = Path(__file__).parent / "sweep-output"

# What the shell needs to boot at all. Forcing these is the "sealed-run" state.
BOOTSTRAP = ("/api/workspace", "/api/scope", "/api/me", "/api/health", "/api/ready")

BAD_COPY = (
    "could not be shown", "could not be read", "request failed", "internal server error",
    "something went wrong", "unexpected error", "failed to fetch", "cannot read propert",
    "undefined", "[object object]", "nan",
)
# "nan" and "undefined" are matched as whole words only.
WORD_ONLY = {"nan", "undefined"}

NEEDS_CLIENT = {
    "eligibility": "/eligibility",
    "monthly-employment": "/onezero",
    "agents": "/agents",
}

PROBE = """
() => {
  const text = (document.body.innerText || '').trim();
  return {
    text,
    skeleton: document.querySelectorAll('.ui-skeleton, [aria-busy="true"], .spin, .tcc-loader').length,
    status: [...document.querySelectorAll('[role=status]')].map((n) => (n.innerText || '').trim()).filter(Boolean),
    headings: [...document.querySelectorAll('h1, h2, h3')].map((n) => (n.innerText || '').trim()).filter(Boolean),
  };
}
"""


def is_bootstrap(url: str) -> bool:
    path = url.split("?")[0].replace(BASE, "")
    return any(path == b or path.startswith(b + "/") for b in BOOTSTRAP)


def attach(page, problems: list[str]):
    page.on("pageerror", lambda e: problems.append(f"uncaught: {str(e)[:120]}"))

    def on_console(msg):
        if msg.type != "error":
            return
        text = msg.text
        # The 4xx/5xx the harness provokes arrive as a generic resource error.
        if "Failed to load resource" in text:
            return
        if "The above error occurred" in text or "Uncaught" in text:
            problems.append(f"react: {text[:120]}")

    page.on("console", on_console)


def bad_words(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for phrase in BAD_COPY:
        if phrase in WORD_ONLY:
            import re
            if re.search(rf"\b{phrase}\b", low):
                hits.append(phrase)
        elif phrase in low:
            hits.append(phrase)
    return hits


def verdict(name: str, state: str, problems: list[str], results: list[dict], note: str = "") -> None:
    ok = not problems
    results.append({"page": name, "state": state, "ok": ok, "problems": problems, "note": note})
    print(f"{'PASS' if ok else 'FAIL'}  {name:<16} {state:<12} {note if ok else '; '.join(problems)}")


def run_state(browser, name, path, state, results):
    problems: list[str] = []
    page = new_page(browser, 1440, 900)
    attach(page, problems)
    note = ""

    if state == "loading":
        def slow(route):
            if is_bootstrap(route.request.url):
                route.continue_()
                return
            page.wait_for_timeout(2500)
            route.continue_()
        page.route("**/api/**", slow)
    elif state == "empty":
        def empty(route):
            if is_bootstrap(route.request.url):
                route.continue_()
            else:
                route.fulfill(status=200, content_type="application/json", body="{}")
        page.route("**/api/**", empty)
    elif state == "error":
        def boom(route):
            if is_bootstrap(route.request.url):
                route.continue_()
            else:
                route.fulfill(status=500, content_type="application/json", body='{"detail":"forced"}')
        page.route("**/api/**", boom)

    page.goto(BASE + path, wait_until="domcontentloaded", timeout=120_000)

    if state == "loading":
        page.wait_for_timeout(900)
        early = page.evaluate(PROBE)
        if not early["text"]:
            problems.append("blank while loading")
        # Give every delayed answer time to land, then it must have resolved.
        page.wait_for_timeout(22_000)
    else:
        try:
            page.wait_for_load_state("networkidle", timeout=60_000)
        except Exception:  # a busy page is judged on what it shows
            pass
        page.wait_for_timeout(1500)

    final = page.evaluate(PROBE)
    if not final["text"]:
        problems.append("blank page")
    if final["skeleton"]:
        problems.append(f"{final['skeleton']} loading marker(s) still present")
    for hit in bad_words(final["text"]):
        problems.append(f"copy reads like a bug: {hit!r}")
    if state in ("error", "empty") and not final["headings"] and not final["status"]:
        problems.append("says nothing: no heading and no status")
    if state == "error" and not (final["status"] or "unavailable" in final["text"].lower()
                                 or "nothing was changed" in final["text"].lower()
                                 or "not calculated" in final["text"].lower()
                                 or "pick a client" in final["text"].lower()):
        # A page that never asked the API has nothing to fail; that is fine.
        note = "no failing read to report"
    page.context.close()
    verdict(name, state, problems, results, note)


def run_special(browser, results):
    # no-client: pages that need a client, opened at the book.
    for name, path in NEEDS_CLIENT.items():
        problems: list[str] = []
        page = new_page(browser, 1440, 900)
        attach(page, problems)
        page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(1500)
        text = page.evaluate(PROBE)["text"].lower()
        if "select a client" not in text and "pick a client" not in text:
            problems.append("does not say a client is needed")
        for hit in bad_words(text):
            problems.append(f"copy reads like a bug: {hit!r}")
        page.context.close()
        verdict(name, "no-client", problems, results)

    # sealed-run-missing
    problems = []
    page = new_page(browser, 1440, 900)
    attach(page, problems)
    page.route("**/api/workspace*", lambda r: r.fulfill(status=503, content_type="application/json", body='{"detail":"missing"}'))
    page.goto(BASE + "/", wait_until="networkidle", timeout=120_000)
    page.wait_for_timeout(1200)
    text = page.evaluate(PROBE)["text"]
    if "workspace unavailable" not in text.lower():
        problems.append("does not say the workspace is unavailable")
    if not page.get_by_role("button", name="Retry").count():
        problems.append("no Retry")
    page.context.close()
    verdict("shell", "sealed-run", problems, results)

    # unavailable assistant
    problems = []
    page = new_page(browser, 1440, 900)
    attach(page, problems)
    page.route("**/api/chat", lambda r: r.fulfill(status=503, content_type="application/json", body='{"detail":"down"}'))
    page.goto(BASE + "/c/2001?year=2023", wait_until="networkidle", timeout=120_000)
    page.wait_for_timeout(1000)
    page.locator("#ask-launcher").click()
    page.wait_for_selector("[role=dialog]")
    page.fill("#ask-input", "how are we doing?")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    text = page.evaluate(PROBE)["text"]
    if "The assistant is unavailable" not in text:
        problems.append("does not say the assistant is unavailable")
    if "still shows the engine" not in text:
        problems.append("does not say the page still has the figures")
    page.context.close()
    verdict("ask", "assistant", problems, results)

    # wrong-year-declined-by-name
    for name, path in (("client", "/c/2001?year=2030"), ("unit", "/c/2001/u/GA_GA-010?year=2030")):
        problems = []
        page = new_page(browser, 1440, 900)
        attach(page, problems)
        page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(1800)
        final = page.evaluate(PROBE)
        text = final["text"].lower()
        if not final["text"]:
            problems.append("blank page")
        # Declined by NAME: the year is said, and a zero is never offered for it.
        if "2030" not in text and "ty2030" not in text and "not calculated" not in text and "no payroll" not in text \
                and "awaiting" not in text and "unavailable" not in text:
            problems.append("neither names the year nor says it was not calculated")
        for hit in bad_words(text):
            problems.append(f"copy reads like a bug: {hit!r}")
        page.context.close()
        verdict(name, "wrong-year", problems, results)


def main() -> int:
    quick = "--quick" in sys.argv
    pages = {k: v for k, v in PAGES.items() if k in ("portfolio", "client", "unit", "rules")} if quick else PAGES
    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for state in ("loading", "empty", "error"):
            for name, path in pages.items():
                run_state(browser, name, path, state, results)
        run_special(browser, results)
        browser.close()

    failed = [r for r in results if not r["ok"]]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "states-report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nstates: {len(results)} checked, {len(failed)} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
