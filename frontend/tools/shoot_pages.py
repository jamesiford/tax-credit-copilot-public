"""Screenshot every routed page, the Ask workspace and the style guide. Dev tooling.

    python frontend/tools/shoot_pages.py before                  # -> sweep-output/before/
    python frontend/tools/shoot_pages.py after modern            # -> sweep-output/after-modern/
    python frontend/tools/shoot_pages.py after classic 1024x768  # one viewport only

Arguments (any order after the label): a theme (`modern` | `classic`) and/or
viewports as `WxH`. Default viewports are 1024x768 (smoke) and 1440x900 (the
acceptance viewport). For each viewport it writes, per page, `<page>-<W>.png`,
plus `ask-<page>-<W>.png` with the workspace open (the Ask launcher clicked)
and `askfx-conversation-<W>.png` / `askfx-evidence-<W>.png` from the dev-only
`?askFixture=1` stream, so the evidence pane has something to draw without a
backend that emits it. `styleguide-<W>.png` is the dev-only /__styleguide.

It also prints, per shot, whether the page overflows horizontally: the one-line
"nothing overflows" statement the 1024 smoke check asks for.

The output folder is gitignored: screenshots may render data and must never be
committed.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from _theme import new_page

BASE = "http://localhost:5173"
OUT = Path(__file__).parent / "sweep-output"
PAGES = {
    "portfolio": "/",
    "client": "/c/2001?year=2023",
    "client-whatif": "/c/2001?year=2023&ctab=whatif",
    "unit": "/c/2001/u/GA_GA-010?year=2023&method=min_max",
    "employee": "/c/2001/e/tok-0001?year=2023",
    "rules": "/rules",
    "ingestion": "/c/1001/ingestion",
    "agents": "/c/2001/agents",
    "evidence": "/c/1001/evidence",
    "eligibility": "/c/2001/eligibility",
}
DEFAULT_VIEWPORTS = [(1024, 768), (1440, 900)]

OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def parse_args(argv: list[str]):
    label = argv[0] if argv else "before"
    theme = None
    viewports: list[tuple[int, int]] = []
    for arg in argv[1:]:
        if arg in ("modern", "classic"):
            theme = arg
        elif re.fullmatch(r"\d+x\d+", arg):
            w, h = arg.split("x")
            viewports.append((int(w), int(h)))
    return label, theme, viewports or DEFAULT_VIEWPORTS


def settle(page, ms: int = 1000) -> None:
    page.wait_for_load_state("networkidle", timeout=120_000)
    page.wait_for_timeout(ms)


def shoot(page, folder: Path, name: str, width: int) -> None:
    target = folder / f"{name}-{width}.png"
    page.screenshot(path=str(target))
    over = page.evaluate(OVERFLOW)
    print(f"{'ok  ' if over <= 0 else 'OVER'} {target.name}  horizontal overflow: {max(over, 0)}px")


def open_ask(page) -> bool:
    launcher = page.locator("#ask-launcher")
    if not launcher.count():
        return False
    launcher.click()
    page.wait_for_selector("[role=dialog]", timeout=10_000)
    page.wait_for_timeout(400)
    return True


def main() -> int:
    label, theme, viewports = parse_args(sys.argv[1:])
    folder = OUT / (label if not theme else f"{label}-{theme}")
    folder.mkdir(parents=True, exist_ok=True)
    if theme:
        os.environ["TCC_THEME"] = theme
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in viewports:
            page = new_page(browser, width, height)
            for name, path in PAGES.items():
                page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
                settle(page, 1200)
                shoot(page, folder, name, width)
                if open_ask(page):
                    shoot(page, folder, f"ask-{name}", width)

            # The evidence pane, from the dev-only fixture stream.
            page.goto(f"{BASE}/c/2001?year=2023&askFixture=1", wait_until="networkidle", timeout=120_000)
            settle(page, 800)
            if open_ask(page):
                page.fill("#ask-input", "how are we doing?")
                page.keyboard.press("Enter")
                page.wait_for_timeout(1500)
                shoot(page, folder, "askfx-conversation", width)
                evidence_tab = page.get_by_role("tab", name=re.compile("Evidence"))
                if evidence_tab.count() and width < 1280:
                    evidence_tab.first.click()
                    page.wait_for_timeout(400)
                    shoot(page, folder, "askfx-evidence", width)

            page.goto(f"{BASE}/__styleguide", wait_until="networkidle", timeout=60_000)
            settle(page, 600)
            shoot(page, folder, "styleguide", width)
            page.context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
