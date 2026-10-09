"""Is any data cell's text wider than the cell holding it?

A width-constrained table absorbs extra padding by shrinking columns, so it
reports as "fits" right up until the figures are unreadable. This measures the
cells themselves.

Dev tooling.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"

PROBE = """
() => {
  const cells = [...document.querySelectorAll('.trend-table tbody td, .trend-table thead th')];
  let clipped = 0;
  let narrowest = 9999;
  const samples = [];
  for (const cell of cells) {
    const box = cell.getBoundingClientRect();
    narrowest = Math.min(narrowest, Math.round(box.width));
    if (cell.scrollWidth > Math.ceil(box.width) + 1) {
      clipped += 1;
      if (samples.length < 6) {
        samples.push({
          text: cell.innerText.trim().slice(0, 14),
          cell: Math.round(box.width),
          needs: cell.scrollWidth,
        });
      }
    }
  }
  return { cells: cells.length, clipped, narrowest, samples };
}
"""


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.goto(BASE + "/c/2001?year=2023", wait_until="networkidle", timeout=120_000)
        page.wait_for_selector(".trend-table tbody tr", timeout=45_000)
        page.wait_for_timeout(600)
        result = page.evaluate(PROBE)
        browser.close()

    print(f"trend-table cells: {result['cells']}")
    print(f"clipped (text wider than its cell): {result['clipped']}")
    print(f"narrowest cell: {result['narrowest']}px")
    for sample in result["samples"]:
        print(f"   {sample['text']!r} needs {sample['needs']}px in {sample['cell']}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
