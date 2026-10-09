"""What size is text actually RENDERED at in the data tables?

The static audit matches selectors and over-reports: `.th-sort sup` is a
superscript, not a table header. This reads computed sizes off the page.

Dev tooling.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
PAGES = {
    "portfolio": "/",
    "client": "/c/2001?year=2023",
    "unit": "/c/2001/u/GA_GA-010?year=2023&method=min_max",
}

PROBE = """
() => {
  const seen = {};
  for (const cell of document.querySelectorAll('table tbody td, table thead th')) {
    if (!cell.innerText.trim()) continue;
    const size = getComputedStyle(cell).fontSize;
    seen[size] = (seen[size] || 0) + 1;
  }
  return seen;
}
"""


def main() -> int:
    floor = 12.0
    worst = 99.0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        for name, path in PAGES.items():
            page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
            try:
                page.wait_for_selector("table tbody tr", timeout=45_000)
                page.wait_for_timeout(600)
            except Exception:  # noqa: BLE001
                pass
            sizes = page.evaluate(PROBE)
            print(f"\n{name}: rendered font sizes in table cells")
            for size, count in sorted(sizes.items(), key=lambda kv: float(kv[0][:-2])):
                value = float(size[:-2])
                worst = min(worst, value)
                flag = "  " if value >= floor else "<-BELOW FLOOR"
                print(f"   {size:>8}  x{count:<4} {flag}")
        browser.close()

    print(f"\nsmallest rendered data text: {worst}px   (floor {floor}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
