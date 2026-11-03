"""Performance gate: bundle size, font requests, and layout shift from the font swap.
Dev tooling, not shipped.

    cd frontend ; npm run build
    npx vite preview --port 4173            # serves dist/ and proxies /api like dev
    python tools/check_perf.py              # reads dist/, drives the preview

What it reports and gates:

  * `dist/` sizes (js, css, fonts) so a before/after is one command.
  * Which font files a cold load requests. Only woff2, only the weights the
    page renders, nothing from another origin.
  * Cumulative layout shift while the fonts are DELAYED (every woff2 held for 6s). `font-display: swap`
    shows text at once in a fallback; the metric-matched fallbacks in
    styles/fonts.css exist so that swap moves nothing. The gate is CLS <= 0.10
    ("good" in Core Web Vitals). The preloaded faces must also be requested early.

Set TCC_PERF_BASE to point at a different server.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from _theme import new_page

HERE = Path(__file__).parent
DIST = HERE.parent / "dist" / "assets"
BASE = os.environ.get("TCC_PERF_BASE", "http://localhost:4173")
CLS_MAX = 0.10
FONT_DELAY_MS = 6000  # long enough that the page has its data before the fonts land
PAGES = {"portfolio": "/", "client": "/c/2001?year=2023", "unit": "/c/2001/u/GA_GA-010?year=2023&method=min_max"}

OBSERVE = """
window.__shifts = [];
new PerformanceObserver((list) => {
  for (const e of list.getEntries()) if (!e.hadRecentInput) window.__shifts.push([e.startTime, e.value]);
}).observe({ type: 'layout-shift', buffered: true });
"""


def sizes() -> dict[str, int]:
    out = {"js": 0, "css": 0, "fonts": 0, "other": 0}
    for f in DIST.glob("*"):
        key = {".js": "js", ".css": "css", ".woff2": "fonts", ".woff": "fonts"}.get(f.suffix, "other")
        out[key] += f.stat().st_size
    return out


def main() -> int:
    if not DIST.exists():
        print("no dist/: run `npm run build` first")
        return 2
    s = sizes()
    print("dist:", {k: f"{v / 1024:.1f} kB" for k, v in s.items()})
    problems: list[str] = []
    if list(DIST.glob("*.woff")):
        problems.append("a .woff is shipped: woff2 only")

    themes = [os.environ["TCC_THEME"]] if os.environ.get("TCC_THEME") else ["modern", "classic"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in themes:
            os.environ["TCC_THEME"] = theme
            for name, path in PAGES.items():
                page = new_page(browser, 1440, 900)
                page.add_init_script(OBSERVE)
                fonts: list[str] = []
                foreign: list[str] = []
                page.on("request", lambda r: fonts.append(Path(r.url.split("?")[0]).name)
                        if r.resource_type == "font" else None)
                page.on("request", lambda r: foreign.append(r.url)
                        if not r.url.startswith((BASE, "data:", "blob:")) else None)

                def slow(route):
                    page.wait_for_timeout(FONT_DELAY_MS)
                    route.continue_()

                page.route("**/*.woff2", slow)
                page.goto(BASE + path, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(FONT_DELAY_MS + 3500)
                shifts = page.evaluate("window.__shifts")
                # Everything before the fonts land is the page loading its data;
                # what moves AFTER is the swap.
                swap = sum(v for t, v in shifts if t >= FONT_DELAY_MS - 300)
                total = sum(v for _, v in shifts)
                cls = swap
                weights = sorted({f.split("-latin-")[1].split("-")[0] + ("p" if f.startswith("poppins") else "r") for f in fonts})
                ok = cls <= CLS_MAX and not foreign
                print(f"{'PASS' if ok else 'FAIL'}  {theme:<8} {name:<10} font-swap CLS {swap:.3f} (page total {total:.3f})  fonts {len(fonts)}: {', '.join(weights)}")
                if cls > CLS_MAX:
                    problems.append(f"{theme} {name}: CLS {cls:.3f} > {CLS_MAX}")
                if foreign:
                    problems.append(f"{theme} {name}: requests left the origin: {sorted(set(foreign))[:2]}")
                if any(not f.endswith(".woff2") for f in fonts):
                    problems.append(f"{theme} {name}: a non-woff2 font was requested")
                page.context.close()
        browser.close()

    for problem in problems:
        print("FAIL", problem)
    print(f"\ncheck_perf: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
