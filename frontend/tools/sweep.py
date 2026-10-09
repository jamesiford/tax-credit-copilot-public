"""
S-01 — landmine sweep.

Shashi's hard requirement for the exec demo:

    "No matter where we click, our app should support that... it's not that you
     put a tab that doesn't take you anywhere. These guys are engineers, they
     build things, they break things."

So this walks every reachable state of the app and records what happened.

    PASS  renders something meaningful, or says plainly why it cannot
    FAIL  stack trace | spinner that never resolves | empty state that reads
          like a bug | a console error | an unhandled network failure

What it covers
--------------
  * every nav view, at portfolio scope and under each client
  * the full drill: portfolio -> client -> unit -> employee
  * a breadcrumb walk back out from the deepest level

Run it, read sweep-report.md, hand the failures to GHCP. Re-run after every
code change -- the whole point is that it is cheap the second time.

Usage
-----
    python sweep.py                 # full sweep
    python sweep.py --clients 2003  # one client, for a quick re-check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, Error as PlaywrightError

WEB = "http://localhost:5173"
API = "http://localhost:8000/api"
OUT = Path(__file__).parent / "sweep-output"

# The nav views, by route id. Labels are today's -- WI-01/WI-03 will rename
# them, and this list is deliberately keyed on the ID so the sweep keeps
# working across that rename.
VIEWS = {
    "eligibility": "Who qualifies",
    "onezero": "One/Zero detail",
    "ingestion": "Data ingestion",
    "agents": "Agent activity",
    "evidence": "Evidence pack",
    "compare": "Compare to Access",
    "rules": "Rules & statute",
    "assumptions": "Methodology",
}

# Text that means the page gave up. An empty state is fine when it EXPLAINS
# itself; these are the ones that read as a bug to somebody who did not write
# the app.
BAD_COPY = [
    "select a single program",          # the known scope dead-end (WI-02)
    "could not be read",
    "request failed",
    "internal server error",
    "something went wrong",
    "unexpected error",
    "failed to fetch",
    "cannot read propert",
    "undefined is not",
    "networkerror",
    "unavailable: error",              # the /null 422 signature
    "/null",
]

# Long waits are legitimate here: a cold Fabric read is ~55-70s per tenant.
SETTLE_MS = 2_500
NAV_TIMEOUT_MS = 90_000


@dataclass
class Result:
    scope: str
    view: str
    url: str
    status: str                       # PASS | FAIL | WARN
    reasons: list[str] = field(default_factory=list)
    heading: str = ""
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    shot: str = ""
    ms: int = 0


def clients() -> list[dict]:
    """The tenants the app will actually offer, straight from the API."""
    import urllib.request

    with urllib.request.urlopen(f"{API}/scope", timeout=120) as r:
        scope = json.loads(r.read())
    return scope.get("clients", [])


def visible_text(page) -> str:
    try:
        return (page.inner_text("body") or "").lower()
    except PlaywrightError:
        return ""


def first_heading(page) -> str:
    for sel in ("h1", "h2", ".page-title", ".panel-title"):
        try:
            el = page.query_selector(sel)
            if el:
                t = (el.inner_text() or "").strip()
                if t:
                    return t.splitlines()[0][:80]
        except PlaywrightError:
            continue
    return ""


def check(page, scope: str, view: str, url: str, console_sink, request_sink) -> Result:
    console_sink.clear()
    request_sink.clear()
    started = datetime.now()
    res = Result(scope=scope, view=view, url=url, status="PASS")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except PlaywrightError as exc:
        res.status = "FAIL"
        res.reasons.append(f"navigation failed: {str(exc).splitlines()[0][:160]}")
        return res

    # Let the view settle, then give any real spinner a generous window.
    #
    # Detect the spinner by ELEMENT, never by substring: the rules page prose
    # contains the word "calculating", and matching on text marked a perfectly
    # healthy page as a hung spinner. `.spin` is the class every Loader2 in
    # this app carries.
    page.wait_for_timeout(SETTLE_MS)

    def spinning() -> bool:
        try:
            return any(el.is_visible() for el in page.query_selector_all(".spin"))
        except PlaywrightError:
            return False

    if spinning():
        for wait in (20_000, 45_000):
            page.wait_for_timeout(wait)
            if not spinning():
                break
        else:
            res.status = "FAIL"
            res.reasons.append("spinner never resolved (>65s)")

    body = visible_text(page)

    res.heading = first_heading(page)
    res.ms = int((datetime.now() - started).total_seconds() * 1000)

    # An app that renders nothing is worse than one that explains itself.
    #
    # Give a thin page a second chance before calling it empty: several views
    # fetch after first paint, and at 2.5s the agents page legitimately still
    # has only its heading. Judging it there marked a healthy page FAIL on one
    # run and PASS on the next, which is worse than useless — a flaky sweep
    # gets ignored.
    if len(body.strip()) < 400:
        page.wait_for_timeout(12_000)
        body = visible_text(page)
        res.heading = first_heading(page) or res.heading

    if len(body.strip()) < 120:
        res.status = "FAIL"
        res.reasons.append(f"page nearly empty ({len(body.strip())} chars)")

    for phrase in BAD_COPY:
        if phrase in body:
            # A bare 404/500 inside a long page is usually a real figure, so
            # only trust those when the page is otherwise thin.
            if phrase in ("404", "500") and len(body) > 2_000:
                continue
            res.status = "FAIL"
            res.reasons.append(f"copy on screen: {phrase!r}")

    if console_sink:
        res.console_errors = list(console_sink)[:5]
        if res.status == "PASS":
            res.status = "WARN"
        res.reasons.append(f"{len(console_sink)} console error(s)")

    if request_sink:
        res.failed_requests = list(request_sink)[:5]
        res.status = "FAIL"
        res.reasons.append(f"{len(request_sink)} failed request(s)")

    OUT.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", f"{scope}-{view}").strip("-")[:70]
    shot = OUT / f"{safe}.png"
    # The screenshot is evidence, not the verdict. Windows intermittently
    # refuses the write (EINVAL, a different file each run), and letting that
    # escape aborted the whole sweep with no report.
    try:
        png = page.screenshot()
    except PlaywrightError:
        png = None
    if png is not None:
        for attempt in range(3):
            try:
                shot.write_bytes(png)
                res.shot = shot.name
                break
            except OSError:
                time.sleep(0.5 * (attempt + 1))
    return res


def drill(page, client_id: int, name: str, console_sink, request_sink) -> list[Result]:
    """Portfolio -> client -> unit -> employee, then walk back out.

    Navigation here is by BUTTON, not by anchor: the location grid opens a unit
    from a `TY20xx` cell, and the unit page opens an employee from an "Open the
    walk" / "Walk" link-button carrying a record token. Looking for `<a href>`
    finds nothing and reports a false gap, which is how a first pass of this
    sweep claimed the drill was unreachable on all five clients.

    "Detail" on a location card is a disclosure toggle (Detail <-> Less), not a
    route. It is deliberately not treated as a drill step.
    """
    out: list[Result] = []
    scope = f"drill/{name}"

    out.append(check(page, scope, "1-client", f"{WEB}/c/{client_id}", console_sink, request_sink))

    # --- unit: click a year cell in the location grid ----------------------
    unit_url = None
    try:
        years = [b for b in page.query_selector_all("button")
                 if (b.inner_text() or "").strip().startswith("TY20")]
        for btn in years[:6]:
            btn.scroll_into_view_if_needed()
            btn.click()
            page.wait_for_timeout(SETTLE_MS * 2)
            if "/u/" in page.url:
                unit_url = page.url
                break
            page.goto(f"{WEB}/c/{client_id}", wait_until="domcontentloaded",
                      timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(SETTLE_MS)
    except PlaywrightError as exc:
        out.append(Result(scope, "2-unit", page.url, "FAIL",
                          [f"could not reach a unit: {str(exc)[:120]}"]))

    if not unit_url:
        out.append(Result(scope, "2-unit", f"{WEB}/c/{client_id}", "FAIL",
                          ["no TY year cell opened a unit from the location grid"]))
        return out

    out.append(check(page, scope, "2-unit", unit_url, console_sink, request_sink))

    # --- employee: "Open the walk" / "Walk" -------------------------------
    # The unit page fetches its employee table AFTER first paint, and on a cold
    # client that table can be ~10s behind the heading. Querying straight after
    # check() returns found nothing and reported a false gap on all five
    # clients. Wait for the control rather than assuming it is there.
    opened = False
    try:
        try:
            # Text-specific: the breadcrumbs ("Portfolio", the client name) are
            # also button.tcc-link, so waiting on the class alone returns
            # immediately and we query before the employee table exists.
            page.wait_for_selector(
                "button.tcc-link:has-text('Open the walk'), button.tcc-link:has-text('Walk')",
                timeout=45_000,
            )
        except PlaywrightError:
            pass
        walks = [b for b in page.query_selector_all("button.tcc-link")
                 if (b.inner_text() or "").strip() in ("Open the walk", "Walk")]
        if walks:
            console_sink.clear()
            request_sink.clear()
            walks[0].scroll_into_view_if_needed()
            walks[0].click()
            page.wait_for_timeout(SETTLE_MS * 2)
            opened = "/e/" in page.url
            if opened:
                out.append(check(page, scope, "3-employee", page.url,
                                 console_sink, request_sink))
            else:
                out.append(Result(scope, "3-employee", page.url, "FAIL",
                                  ["'Open the walk' did not navigate to an employee"]))
        else:
            out.append(Result(scope, "3-employee", unit_url, "WARN",
                              ["no 'Open the walk' button on the unit page"]))
    except PlaywrightError as exc:
        out.append(Result(scope, "3-employee", page.url, "FAIL", [str(exc)[:120]]))

    # --- breadcrumb back out ----------------------------------------------
    # A dead breadcrumb is exactly what the partner would step on mid-sentence.
    if opened:
        for label, expect in (("Portfolio", WEB.rstrip("/")),):
            try:
                b = page.query_selector(f"button:has-text('{label}')")
                if not b:
                    out.append(Result(scope, "4-breadcrumb-back", page.url, "FAIL",
                                      [f"no '{label}' breadcrumb on the employee page"]))
                    continue
                b.click()
                page.wait_for_timeout(SETTLE_MS)
                ok = page.url.rstrip("/") == expect
                out.append(Result(scope, "4-breadcrumb-back", page.url,
                                  "PASS" if ok else "FAIL",
                                  [] if ok else [f"'{label}' landed on {page.url}"]))
            except PlaywrightError as exc:
                out.append(Result(scope, "4-breadcrumb-back", page.url, "FAIL",
                                  [str(exc)[:120]]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", nargs="*", type=int, default=None,
                    help="account ids to sweep; default is all")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    every = clients()
    if args.clients:
        every = [c for c in every if c["account_id"] in args.clients]
    print(f"sweeping {len(every)} client(s): {', '.join(c['name'] for c in every)}\n")

    results: list[Result] = []
    console_sink: list[str] = []
    request_sink: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.on("console", lambda m: console_sink.append(f"{m.type}: {m.text[:200]}")
                if m.type == "error" else None)
        page.on("requestfailed", lambda r: request_sink.append(
            f"{r.method} {r.url[:140]} :: {(r.failure or '')[:80]}"))
        page.on("response", lambda r: request_sink.append(
            f"HTTP {r.status} {r.url[:140]}") if r.status >= 500 else None)

        # ---- portfolio scope -------------------------------------------------
        print("portfolio scope")
        results.append(check(page, "portfolio", "book", WEB, console_sink, request_sink))
        print(f"  {results[-1].status:5} book")
        for vid in VIEWS:
            r = check(page, "portfolio", vid, f"{WEB}/{vid}", console_sink, request_sink)
            results.append(r)
            print(f"  {r.status:5} {vid}")

        # ---- each client -----------------------------------------------------
        for c in every:
            cid, name = c["account_id"], c["name"]
            print(f"\n{name} ({cid})")
            for vid in VIEWS:
                r = check(page, name, vid, f"{WEB}/c/{cid}/{vid}", console_sink, request_sink)
                results.append(r)
                print(f"  {r.status:5} {vid}")

        # ---- the drill, on the demo client first -----------------------------
        for c in every:
            cid, name = c["account_id"], c["name"]
            print(f"\ndrill: {name}")
            for r in drill(page, cid, name, console_sink, request_sink):
                results.append(r)
                print(f"  {r.status:5} {r.view}")

        browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    write_report(results)

    fails = [r for r in results if r.status == "FAIL"]
    warns = [r for r in results if r.status == "WARN"]
    print(f"\n{'='*66}")
    print(f"{len(results)} states · {len(fails)} FAIL · {len(warns)} WARN")
    print(f"report: {OUT / 'sweep-report.md'}")
    return 1 if fails else 0


def write_report(results: list[Result]) -> None:
    fails = [r for r in results if r.status == "FAIL"]
    warns = [r for r in results if r.status == "WARN"]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    L = [
        "# S-01 landmine sweep",
        f"\n**{stamp}** · {len(results)} states · "
        f"**{len(fails)} FAIL** · {len(warns)} WARN · "
        f"{len(results)-len(fails)-len(warns)} PASS\n",
        "> Shashi's bar: *\"No matter where we click, our app should support "
        "that… it's not that you put a tab that doesn't take you anywhere.\"*\n",
        "---\n",
    ]

    if fails:
        L.append("## FAIL — fix before the demo\n")
        L.append("| Scope | View | Why | URL |")
        L.append("|---|---|---|---|")
        for r in fails:
            L.append(f"| {r.scope} | `{r.view}` | {'; '.join(r.reasons)} | `{r.url}` |")
        L.append("")
        L.append("### Detail\n")
        for r in fails:
            L.append(f"**{r.scope} · {r.view}** — `{r.url}`\n")
            L.append(f"- heading: {r.heading or '(none)'}")
            for reason in r.reasons:
                L.append(f"- {reason}")
            for e in r.console_errors:
                L.append(f"  - console: `{e}`")
            for q in r.failed_requests:
                L.append(f"  - request: `{q}`")
            if r.shot:
                L.append(f"- shot: `sweep-output/{r.shot}`")
            L.append("")
    else:
        L.append("## No failures. Every state rendered or explained itself.\n")

    if warns:
        L.append("## WARN — console noise, not a visible break\n")
        L.append("| Scope | View | Why |")
        L.append("|---|---|---|")
        for r in warns:
            L.append(f"| {r.scope} | `{r.view}` | {'; '.join(r.reasons)} |")
        L.append("")

    L.append("## Every state\n")
    L.append("| Scope | View | Status | Heading | ms |")
    L.append("|---|---|---|---|---|")
    for r in results:
        mark = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[r.status]
        L.append(f"| {r.scope} | `{r.view}` | {mark} {r.status} | {r.heading or '—'} | {r.ms} |")

    slow = sorted(results, key=lambda r: -r.ms)[:8]
    L.append("\n## Slowest states\n")
    L.append("Anything over 3s needs warming in pre-flight, not cutting.\n")
    L.append("| Scope | View | Seconds |")
    L.append("|---|---|---|")
    for r in slow:
        L.append(f"| {r.scope} | `{r.view}` | {r.ms/1000:.1f} |")

    (OUT / "sweep-report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
