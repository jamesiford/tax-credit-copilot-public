"""Screenshot every routed page at a set of viewports. Dev tooling, not shipped.

    python frontend/tools/shoot_pages.py before            # -> sweep-output/before/
    python frontend/tools/shoot_pages.py after modern      # -> sweep-output/after-modern/
    python frontend/tools/shoot_pages.py after classic

The optional second argument is the theme to force (`modern` | `classic`); it is
written to localStorage before the app boots, which is where `applyTheme` looks
as the last override. The output folder is gitignored: screenshots may render
data and must never be committed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from _theme import new_page

BASE = "http://localhost:5173"
OUT = Path(__file__).parent / "sweep-output"
PAGES = {
    "portfolio": "/",
    "client": "/c/2001?year=2023",
    "client-whatif": "/c/2001?year=2023&tab=whatif",
    "unit": "/c/2001/u/GA_GA-010?year=2023&method=min_max",
    "employee": "/c/2001/e/tok-0001?year=2023",
    "rules": "/rules",
    "ingestion": "/c/1001/ingestion",
    "agents": "/c/2001/agents",
    "evidence": "/c/1001/evidence",
    "eligibility": "/c/2001/eligibility",
}
VIEWPORTS = [(1440, 900)]


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    theme = sys.argv[2] if len(sys.argv) > 2 else None
    folder = OUT / (label if not theme else f"{label}-{theme}")
    folder.mkdir(parents=True, exist_ok=True)
    if theme:
        os.environ["TCC_THEME"] = theme
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in VIEWPORTS:
            page = new_page(browser, width, height)
            for name, path in PAGES.items():
                page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
                page.wait_for_timeout(1200)
                target = folder / f"{name}-{width}.png"
                page.screenshot(path=str(target))
                print(target)
            page.context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
