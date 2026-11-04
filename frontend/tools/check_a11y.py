"""Accessibility gate: axe-core through Playwright. Dev tooling, not shipped.

    python frontend/tools/check_a11y.py              # both themes, every page
    python frontend/tools/check_a11y.py --quick      # modern only, fewer pages
    TCC_THEME=classic python frontend/tools/check_a11y.py

Runs axe-core (pinned in package.json) on every routed page, on the dev
`/__styleguide`, and with the Ask workspace open (conversation, and the
evidence pane from the dev-only `?askFixture=1` stream and from the real backend
stream shape served by `mock_api.py`), in both themes. The gate
is ZERO violations of impact `serious` or `critical`. Lesser impacts are
printed, never hidden, so they can be worked down.

One carve-out, stated rather than hidden: the classic theme is the previous
look, kept so the revamp can be rolled back by configuration, and its palette is
unchanged on purpose (UI-DECISIONS D9). `color-contrast` is therefore REPORTED,
not failed, for classic, exactly as `check_contrast.py` does. Every other rule is
enforced in both themes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from _theme import new_page
from shoot_pages import BASE, PAGES

HERE = Path(__file__).parent
AXE = HERE.parent / "node_modules" / "axe-core" / "axe.min.js"
OUT = HERE / "sweep-output"
GATE = ("serious", "critical")

RUN = """
async () => {
  const result = await axe.run(document, {
    resultTypes: ['violations'],
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
  });
  return result.violations.map((v) => ({
    id: v.id, impact: v.impact, help: v.help,
    nodes: v.nodes.slice(0, 3).map((n) => ({ target: n.target.join(' '), html: n.html.slice(0, 140) })),
    count: v.nodes.length,
  }));
}
"""


def scan(page, label: str, theme: str, report: list[dict]) -> int:
    page.add_script_tag(path=str(AXE))
    violations = page.evaluate(RUN)
    failing = 0
    for v in violations:
        enforced = v["impact"] in GATE and not (theme == "classic" and v["id"] == "color-contrast")
        if enforced:
            failing += 1
        report.append({"theme": theme, "where": label, **v, "enforced": enforced})
        mark = "FAIL" if enforced else "note"
        print(f"  {mark} [{v['impact']}] {v['id']} x{v['count']}: {v['help']}")
        for n in v["nodes"][:2]:
            print(f"        {n['target']}  {n['html'][:100]}")
    print(f"{'FAIL' if failing else 'PASS'}  {theme:<8} {label}")
    return failing


def open_workspace(page) -> None:
    page.locator("#ask-launcher").click()
    page.wait_for_selector("[role=dialog]", timeout=10_000)
    page.wait_for_timeout(400)


def main() -> int:
    quick = "--quick" in sys.argv
    themes = [os.environ["TCC_THEME"]] if os.environ.get("TCC_THEME") else (["modern"] if quick else ["modern", "classic"])
    pages = {k: v for k, v in PAGES.items() if k in ("portfolio", "client", "rules")} if quick else PAGES
    report: list[dict] = []
    failing = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in themes:
            os.environ["TCC_THEME"] = theme
            for name, path in pages.items():
                page = new_page(browser, 1440, 900)
                page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
                page.wait_for_timeout(1200)
                failing += scan(page, name, theme, report)
                if page.locator("#ask-launcher").count():
                    open_workspace(page)
                    failing += scan(page, f"{name} + workspace", theme, report)
                page.context.close()

            # The evidence pane, fed by the dev-only fixture stream and by the real
            # backend shape (the mock serves `/api/chat` from askBackendShape.json).
            for source, query in (("fixture", "&askFixture=1"), ("backend shape", "")):
                for width, height in ((1440, 900), (1024, 768)):
                    page = new_page(browser, width, height)
                    page.goto(f"{BASE}/c/2001?year=2023{query}", wait_until="networkidle", timeout=120_000)
                    page.wait_for_timeout(800)
                    open_workspace(page)
                    page.fill("#ask-input", "how are we doing?")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1500)
                    if width < 1280:
                        page.get_by_role("tab", name="Evidence").first.click()
                        page.wait_for_timeout(300)
                    if source != "fixture" and page.get_by_role("tab", name="Who to call").count() == 0:
                        print(f"FAIL  {theme:<8} workspace evidence ({source}) @{width}: no evidence tab rendered")
                        failing += 1
                    failing += scan(page, f"workspace evidence ({source}) @{width}", theme, report)
                    page.context.close()

            page = new_page(browser, 1440, 900)
            page.goto(f"{BASE}/__styleguide", wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(800)
            failing += scan(page, "styleguide", theme, report)
            page.context.close()
        browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "a11y-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    enforced = [r for r in report if r["enforced"]]
    print(f"\na11y: {len(enforced)} serious/critical violation group(s) enforced; "
          f"{len(report) - len(enforced)} other finding group(s) reported")
    return 1 if enforced else 0


if __name__ == "__main__":
    sys.exit(main())
