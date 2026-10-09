"""Brand gate: computed font, state colours, chip treatment, network origins.

Dev tooling, not shipped. Everything here is read from the RENDERED page --
a CSS declaration proves nothing if a fallback wins.
"""
from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
CLIENT = "/c/2001?year=2023"


def main() -> int:
    out: dict[str, object] = {}
    external: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.on("request", lambda r: external.append(r.url)
                if ("googleapis.com" in r.url or "gstatic.com" in r.url) else None)

        page.goto(BASE + CLIENT, wait_until="networkidle", timeout=120_000)
        page.wait_for_selector(".trend-unit-row", timeout=45_000)
        page.wait_for_timeout(800)

        out["computed_font"] = page.evaluate("""
          () => {
            const read = (sel) => {
              const el = document.querySelector(sel);
              return el ? getComputedStyle(el).fontFamily : null;
            };
            return {
              body: read('body'),
              heading: read('h1, h2'),
              cell: read('table tbody td'),
            };
          }
        """)
        out["roboto_rendered"] = page.evaluate("""
          () => document.fonts.check('12px Roboto')
        """)

        out["state_colours"] = page.evaluate("""
          () => {
            const pick = (cls) => {
              const row = document.querySelector('tr.' + cls);
              const pill = row && row.querySelector('.pill');
              if (!pill) return null;
              const s = getComputedStyle(pill);
              return { label: pill.textContent.trim(),
                       bg: s.backgroundColor, ink: s.color };
            };
            return { base_year: pick('trend-accent'), below_min: pick('trend-bad') };
          }
        """)

        # Open one unit's detail so the chips exist.
        page.locator(".trend-unit-more").first.click()
        page.wait_for_timeout(300)
        out["chips"] = page.evaluate("""
          () => {
            const read = (el) => el ? {
              opacity: getComputedStyle(el).opacity,
              border: getComputedStyle(el).borderTopStyle,
            } : null;
            return {
              measured: read(document.querySelector('.trend-credit:not(.projected)')),
              projected: read(document.querySelector('.trend-credit.projected')),
            };
          }
        """)

        browser.close()

    out["google_font_requests"] = external
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
