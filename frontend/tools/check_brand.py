"""Brand gate, per theme: computed font, state colours, selection vs verdict,
and network origins. Dev tooling, not shipped.

Everything here is read from the RENDERED page -- a CSS declaration proves
nothing if a fallback wins.

Per theme it asserts that

  * body, headings, buttons and table cells compute to the font the theme
    names (`--font-sans`; `--font-data` for the data register);
  * every --state-* token (five families x bg/ink/line) resolves to a colour,
    and --state-base-year and --state-below-min stay apart (CIE76 distance on
    ink and on line above the stated thresholds): "we hold no prior year" and
    "they did not grow enough" are different findings;
  * the selection colour is not any state colour: a selected tab must never be
    mistakable for a verdict;
  * no request leaves the origin (no hotlinked font or asset).

    python frontend/tools/check_brand.py             # both themes
    TCC_THEME=modern python frontend/tools/check_brand.py
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

from _theme import new_page

BASE = "http://localhost:5173"
CLIENT = "/c/2001?year=2023"

INK_DISTANCE_MIN = 30.0   # base-year ink vs below-min ink, CIE76
LINE_DISTANCE_MIN = 15.0  # their outlines
FAMILIES = ["base-year", "above-min", "below-min", "partial", "neutral"]
EXPECTED_FONT = {"modern": {"ui": "Poppins", "data": "Roboto"}, "classic": {"ui": "Roboto", "data": "Roboto"}}

PROBE = """
(families) => {
  const root = getComputedStyle(document.documentElement);
  const toRgb = (value) => {
    const probe = document.createElement('i');
    probe.style.color = value.trim();
    document.body.appendChild(probe);
    const rgb = getComputedStyle(probe).color;
    probe.remove();
    return rgb;
  };
  const token = (name) => root.getPropertyValue(name).trim();
  const state = {};
  for (const family of families) {
    for (const part of ['', '-ink', '-line']) {
      const name = `--state-${family}${part}`;
      state[name] = token(name) ? toRgb(token(name)) : null;
    }
  }
  const select = {};
  for (const name of ['--select', '--select-strong', '--select-bg', '--select-line']) {
    select[name] = token(name) ? toRgb(token(name)) : null;
  }
  const font = (sel) => {
    const el = document.querySelector(sel);
    return el ? getComputedStyle(el).fontFamily : null;
  };
  return {
    theme: document.documentElement.getAttribute('data-theme'),
    state, select,
    fonts: { body: font('body'), heading: font('h1, h2'), button: font('button'), cell: font('table tbody td') },
  };
}
"""


VERDICT_PROBE = """
() => {
  // Anything that states a reading: a state tile, a pill that is not a plain
  // category or neutral label, a verdict card, a band chip.
  const sel = [
    '.ui-kpi:not(.ui-kpi-neutral):not(.ui-kpi-empty)',
    '.ui-pill:not(.ui-pill-category):not(.ui-pill-neutral):not(.ui-pill-info)',
    '[class*="ui-card-verdict-"]',
    '.tcc-band',
  ].join(',');
  return [...document.querySelectorAll(sel)].map((el) => {
    const cs = getComputedStyle(el);
    return {
      selector: el.className.toString().split(' ').slice(0, 2).join('.'),
      text: (el.textContent || '').trim().slice(0, 24),
      colours: {
        background: cs.backgroundColor,
        border: cs.borderLeftColor,
        text: cs.color,
      },
    };
  });
}
"""


def lab(rgb: str) -> tuple[float, float, float]:
    r, g, b = [int(float(v)) / 255 for v in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3]]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e(a: str, b: str) -> float:
    return sum((p - q) ** 2 for p, q in zip(lab(a), lab(b))) ** 0.5


def verdict_problems(page, select: dict[str, str]) -> list[str]:
    """No rendered verdict wears the selection colour (UI-04..06 doctrine)."""
    page.goto(BASE + "/", wait_until="networkidle", timeout=120_000)
    page.wait_for_selector(".cov-grid tbody tr", timeout=45_000)
    page.wait_for_timeout(600)
    found = page.evaluate(VERDICT_PROBE)
    print(f"verdict surfaces checked on the book: {len(found)}")
    chosen = {v: k for k, v in select.items() if v}
    problems = []
    for item in found:
        for prop, value in item["colours"].items():
            if value in chosen:
                problems.append(
                    f"verdict {item['selector']} ({item['text']!r}) {prop} is the selection colour {chosen[value]}"
                )
    return problems


def check(theme: str, page) -> list[str]:
    problems: list[str] = []
    page.goto(BASE + CLIENT, wait_until="networkidle", timeout=120_000)
    page.wait_for_selector(".trend-unit-row", timeout=45_000)
    page.wait_for_timeout(600)
    probe = page.evaluate(PROBE, FAMILIES)
    print(json.dumps({"theme": theme, **probe}, indent=2))

    if probe["theme"] != theme:
        problems.append(f"data-theme is {probe['theme']!r}, expected {theme!r}")

    want = EXPECTED_FONT[theme]
    for role, key in (("body", "ui"), ("heading", "ui"), ("button", "ui"), ("cell", "data")):
        family = probe["fonts"][role]
        if family is None:
            continue
        if want[key] not in family.split(",")[0]:
            problems.append(f"{role} font is {family!r}, expected {want[key]} first")

    resolved = True
    for name, value in probe["state"].items():
        if not value:
            problems.append(f"{name} does not resolve to a colour")
            resolved = False
    state = probe["state"]
    if resolved:
        ink = delta_e(state["--state-base-year-ink"], state["--state-below-min-ink"])
        line = delta_e(state["--state-base-year-line"], state["--state-below-min-line"])
        print(f"base-year vs below-min: ink dE {ink:.1f} (min {INK_DISTANCE_MIN}), line dE {line:.1f} (min {LINE_DISTANCE_MIN})")
        if ink < INK_DISTANCE_MIN:
            problems.append(f"base-year and below-min inks too close: dE {ink:.1f}")
        if line < LINE_DISTANCE_MIN:
            problems.append(f"base-year and below-min lines too close: dE {line:.1f}")

    verdicts = {v for v in state.values() if v}
    for name, value in probe["select"].items():
        if value in verdicts:
            problems.append(f"selection colour {name} ({value}) is also a state colour")
    problems += verdict_problems(page, probe["select"])
    return problems


def main() -> int:
    themes = [os.environ["TCC_THEME"]] if os.environ.get("TCC_THEME") else ["modern", "classic"]
    failures: list[str] = []
    external: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in themes:
            os.environ["TCC_THEME"] = theme
            page = new_page(browser, 1440, 900)
            page.on("request", lambda r: external.append(r.url)
                    if not r.url.startswith((BASE, "data:", "blob:")) else None)
            failures += [f"[{theme}] {problem}" for problem in check(theme, page)]
            page.context.close()
        browser.close()

    if external:
        failures.append(f"requests left the origin: {sorted(set(external))}")
    for failure in failures:
        print("FAIL", failure)
    print(f"\ncheck_brand: {len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
