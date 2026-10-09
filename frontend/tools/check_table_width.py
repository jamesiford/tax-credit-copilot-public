"""Does the widest data table still fit 1024px, or does it now scroll?

Carbon's 16px column padding assumes a table with a handful of columns. The
trend grid is a tax year plus twelve months plus four summary columns.

Dev tooling.
"""
from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
PAGES = {"client": "/c/2001?year=2023", "portfolio": "/"}

PROBE = """
() => {
  const out = [];
  for (const table of document.querySelectorAll('table')) {
    const holder = table.closest('.tbl-scroll, .cov-scroll, .tcc-table-wrap, div') || table.parentElement;
    out.push({
      cls: (table.className || '(none)').slice(0, 40),
      cols: table.querySelectorAll('thead th').length,
      tableWidth: Math.round(table.scrollWidth),
      holderWidth: Math.round(holder.clientWidth),
      overflows: table.scrollWidth > holder.clientWidth + 1,
    });
  }
  return out;
}
"""


def main() -> int:
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
            print(f"\n=== {name}")
            for row in page.evaluate(PROBE):
                flag = "OVERFLOWS" if row["overflows"] else "fits"
                print(f"   {flag:<10} cols={row['cols']:>3}  table={row['tableWidth']:>5}  "
                      f"holder={row['holderWidth']:>5}  {row['cls']}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
