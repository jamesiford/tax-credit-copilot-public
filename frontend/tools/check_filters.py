"""One-off: drive each filter type through the UI and report what it did.

Dev tooling. The point is to prove the control is LIVE — a control that looks
live and filters nothing is how a reader trusts a wrong number.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        print("=== client grid: ENUM (Reading) and YEAR (Tax year), client-side ===")
        page.goto(f"{BASE}/c/2001?year=2023", wait_until="networkidle", timeout=120_000)
        before = len(page.query_selector_all("table tbody tr"))
        page.click('button[aria-label="Filter Reading"]')
        page.wait_for_timeout(250)
        options = page.eval_on_selector_all(".colf-check span", "e=>e.map(x=>x.textContent)")
        print("offered (from the data, not a list):", options)
        page.click('.colf-check:has-text("below minimum") input')
        page.wait_for_timeout(400)
        print("url        ", page.url)
        print("statement  ", page.inner_text(".filter-bar-count"))
        print("chips      ", page.eval_on_selector_all(".filter-chip", "e=>e.map(x=>x.textContent.trim())"))
        print(f"rows       {before} -> {len(page.query_selector_all('table tbody tr'))}")

        print("\n=== client grid: YEAR added on top ===")
        page.goto(
            f"{BASE}/c/2001?year=2023&row_f=status:below_minimum;tax_year:2023",
            wait_until="networkidle", timeout=120_000,
        )
        print("statement  ", page.inner_text(".filter-bar-count"))
        print("chips      ", page.eval_on_selector_all(".filter-chip", "e=>e.map(x=>x.textContent.trim())"))

        print("\n=== unit grid: NUMERIC, server-side ===")
        requests = []
        page.on("request", lambda r: requests.append(r.url) if "/units/" in r.url else None)
        page.goto(
            f"{BASE}/c/1001/u/GA_1134860?year=2023&method=min_max"
            f"&emp_f=avg_weekly_hours:>%3D35;weeks_worked:>%3D26",
            wait_until="networkidle", timeout=120_000,
        )
        print("request    ", requests[-1] if requests else "(none)")
        print("statement  ", page.inner_text(".filter-bar-count"))
        print("chips      ", page.eval_on_selector_all(".filter-chip", "e=>e.map(x=>x.textContent.trim())"))
        print("rows       ", len(page.query_selector_all("table tbody tr")))
        print("tab counts ", page.eval_on_selector_all("[role=tab]", "e=>e.map(x=>x.textContent)"))

        print("\n=== unit grid: TEXT, server-side ===")
        requests.clear()
        page.goto(
            f"{BASE}/c/1001/u/GA_1134860?year=2023&method=min_max&emp_f=employee_id:~6480",
            wait_until="networkidle", timeout=120_000,
        )
        print("request    ", requests[-1] if requests else "(none)")
        print("statement  ", page.inner_text(".filter-bar-count"))
        print("rows       ", len(page.query_selector_all("table tbody tr")))

        print("\n=== a term the grammar cannot read is dropped, not widened ===")
        requests.clear()
        page.goto(
            f"{BASE}/c/1001/u/GA_1134860?year=2023&method=min_max&emp_f=weeks_worked:banana",
            wait_until="networkidle", timeout=120_000,
        )
        print("request    ", requests[-1] if requests else "(none)")
        print("statement  ", "(none - nothing claims to be filtering)"
              if not page.query_selector(".filter-bar-count")
              else page.inner_text(".filter-bar-count"))
        print("rows       ", len(page.query_selector_all("table tbody tr")))
        browser.close()


if __name__ == "__main__":
    main()
