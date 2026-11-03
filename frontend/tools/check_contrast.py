"""WCAG contrast of the text actually rendered. Dev tooling.

Computed styles, not declarations: a rule that sets a colour proves nothing if
something later wins, and a colour is only legible against the surface it
lands on. For every element that directly holds text this finds the first
opaque ancestor background and measures the pair.

  < 4.5:1 fails for text; < 3:1 for large text (24px, or 18.66px bold) .

Gradients and images are not sampled (an element over one is skipped and
counted), so the styleguide, which draws flat surfaces, is the strictest view.
Offenders are reported once per selector and colour pair.

    python frontend/tools/check_contrast.py                 # both themes
    TCC_THEME=classic python frontend/tools/check_contrast.py
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

from _theme import new_page

BASE = "http://localhost:5173"
PAGES = {
    "styleguide": "/__styleguide",
    "portfolio": "/",
    "client": "/c/2001?year=2023",
    "unit": "/c/2001/u/GA_GA-010?year=2023&method=min_max",
}

PROBE = """
() => {
  const parse = (value) => {
    const m = value.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (top, under) => ({
    r: top.r * top.a + under.r * (1 - top.a),
    g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a),
    a: 1,
  });
  const backdrop = (el) => {
    const stack = [];
    for (let node = el; node; node = node.parentElement) {
      const s = getComputedStyle(node);
      if (s.backgroundImage !== 'none') return null;
      const bg = parse(s.backgroundColor);
      if (bg && bg.a > 0) { stack.push(bg); if (bg.a >= 1) break; }
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (const layer of stack.reverse()) base = over(layer, base);
    return base;
  };
  const lum = ({ r, g, b }) => {
    const c = [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const selector = (el) => {
    const cls = [...el.classList].slice(0, 2).join('.');
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
  };
  const out = []; let skipped = 0; let checked = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent.trim()) continue;
    const el = node.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || el.getBoundingClientRect().width === 0) continue;
    const fg = parse(s.color);
    const bg = backdrop(el);
    if (!fg || !bg) { skipped++; continue; }
    const text = over(fg, bg);
    const l1 = lum(text), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(s.fontSize);
    const bold = parseInt(s.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    checked++;
    if (ratio < (large ? 3 : 4.5)) {
      out.push({ selector: selector(el), ratio: Math.round(ratio * 100) / 100, need: large ? 3 : 4.5,
                 fg: s.color, bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
                 size, text: node.textContent.trim().slice(0, 30), disabled: el.closest('[disabled], [aria-disabled=true]') !== null });
    }
  }
  return { out, skipped, checked };
}
"""


def run(theme: str | None) -> int:
    if theme:
        os.environ["TCC_THEME"] = theme
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = new_page(browser, 1440, 900)
        for name, path in PAGES.items():
            page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
            page.wait_for_timeout(900)
            result = page.evaluate(PROBE)
            unique = {}
            for item in result["out"]:
                # A disabled control is exempt from WCAG contrast (1.4.3).
                if item["disabled"]:
                    continue
                unique.setdefault((item["selector"], item["fg"], item["bg"]), item)
            print(f"[{theme or 'default'}] {name}: {result['checked']} text nodes, "
                  f"{result['skipped']} over gradients, {len(unique)} below threshold")
            for item in sorted(unique.values(), key=lambda i: i["ratio"])[:25]:
                print(f"   {item['ratio']:>5}:1 (need {item['need']})  {item['selector']:<34} "
                      f"{item['fg']} on {item['bg']}  '{item['text']}'")
            failures += len(unique)
        browser.close()
    return failures


def main() -> int:
    themes = [os.environ["TCC_THEME"]] if os.environ.get("TCC_THEME") else ["modern", "classic"]
    total = 0
    for theme in themes:
        failures = run(theme)
        if theme == "classic" and not os.environ.get("TCC_STRICT_CLASSIC"):
            # The classic palette is the previous look, preserved as it was. Its
            # muted greys predate this gate; reporting them is useful, failing
            # the build on a look nobody is changing is not.
            print(f"[classic] {failures} pair(s) below threshold (informational)")
        else:
            total += failures
    print(f"\ncheck_contrast: {total} pair(s) below threshold")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
