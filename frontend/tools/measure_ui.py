"""Measure the revamp gates at a fixed viewport. Dev tooling, not shipped.

The gate is "can the partner see their data without scrolling", so this counts rows whose
BOTTOM edge is inside the viewport — not rows that merely exist. The chat
browser tool has no viewport control, so this drives a real Chromium at size.

    python frontend/tools/measure_ui.py            # 1024x768
    python frontend/tools/measure_ui.py 1440 900
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"

PAGES = {
    "portfolio": "/",
    "client": "/c/2001?year=2023",
    "unit": "/c/2001/u/GA_GA-010?year=2023&method=min_max",
}

PROBE = """
() => {
  const vh = window.innerHeight;
  const top = (el) => el ? Math.round(el.getBoundingClientRect().top) : null;
  const rows = [...document.querySelectorAll('table tbody tr')]
    .filter(r => r.getBoundingClientRect().height > 4);
  const visible = rows.filter(r => {
    const box = r.getBoundingClientRect();
    return box.top >= 0 && box.bottom <= vh;
  });
  const heights = rows.slice(0, 20).map(r => Math.round(r.getBoundingClientRect().height));
  heights.sort((a, b) => a - b);
  const main = document.querySelector('main');
  const side = document.querySelector('.tcc-sidenav');
  return {
    firstRowY: top(rows[0]),
    rowsVisibleNoScroll: visible.length,
    rowsTotal: rows.length,
    medianRowHeight: heights.length ? heights[Math.floor(heights.length / 2)] : null,
    contentWidth: main ? Math.round(main.getBoundingClientRect().width) : null,
    sidebarWidth: side ? Math.round(side.getBoundingClientRect().width) : 0,
    scrollHeight: Math.round(document.documentElement.scrollHeight),
    viewport: vh,
  };
}
"""


def main() -> int:
    width = int(sys.argv[1]) if len(sys.argv) > 2 else 1024
    height = int(sys.argv[2]) if len(sys.argv) > 2 else 768
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        for name, path in PAGES.items():
            page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
            try:
                page.wait_for_selector("table tbody tr", timeout=45_000)
                page.wait_for_timeout(700)
            except Exception:  # noqa: BLE001 - a page with no table is a real answer
                pass
            out[name] = page.evaluate(PROBE)
        browser.close()

    print(f"=== {width}x{height} ===")
    print(f"{'page':<11} {'VISIBLE':>8} {'total':>6} {'1st row y':>10} "
          f"{'row h':>6} {'content':>8} {'sidebar':>8} {'scroll':>7}")
    for name, m in out.items():
        print(f"{name:<11} {m['rowsVisibleNoScroll']:>8} {m['rowsTotal']:>6} "
              f"{str(m['firstRowY']):>10} {str(m['medianRowHeight']):>6} "
              f"{str(m['contentWidth']):>8} {m['sidebarWidth']:>8} {m['scrollHeight']:>7}")
    print()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
