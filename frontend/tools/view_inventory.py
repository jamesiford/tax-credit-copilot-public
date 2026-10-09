"""Per-view design inventory. Dev tooling.

Answers, per view: does it compose the shared components or hand-roll them, is
its spacing on the scale, and does it encode a reading in a colour that is not
a --state-* token. The list of what is inconsistent is the next round's input.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

SHARED = {
    "PageHeader": r"<PageHeader\b",
    "StatCard": r"<StatCard\b|<StatRow\b",
    "Breadcrumb": r"<Breadcrumb\b",
    "MethodTabs": r"<MethodTabs\b",
    "InsightBar": r"<InsightBar\b",
}

#: Hand-rolled equivalents of the shared components.
ROLLED = {
    "own header": r'className="(page-header|panel-head|view-header)"',
    "own stat block": r'className="(kpi-strip|kpi-card|stat-row)"',
    "own tabs": r'className="[^"]*\btabs?\b[^"]*"',
}

STATE_TOKENS = re.compile(r"--state-[a-z-]+")


def main() -> int:
    rows = []
    for path in sorted(list((SRC / "components").glob("*View.jsx")) + list((SRC / "pages").glob("*Page.jsx"))):
        text = path.read_text(encoding="utf-8")
        uses = [name for name, pattern in SHARED.items() if re.search(pattern, text)]
        rolls = [name for name, pattern in ROLLED.items() if re.search(pattern, text)]
        inline = len(re.findall(r"style=\{\{", text))
        hexes = len(re.findall(r"#[0-9a-fA-F]{3,8}\b", text))
        rows.append((path.name, uses, rolls, inline, hexes))

    width = max(len(name) for name, *_ in rows)
    print(f"{'view':<{width}}  {'shared used':<34}  {'hand-rolled':<34}  inline  hex")
    for name, uses, rolls, inline, hexes in rows:
        print(f"{name:<{width}}  {', '.join(uses) or '-':<34}  "
              f"{', '.join(rolls) or '-':<34}  {inline:>6}  {hexes:>3}")

    print("\ncomponents that reference a --state-* token directly:")
    for path in sorted(SRC.rglob("*.jsx")):
        if path.name.endswith(".test.jsx"):
            continue
        found = STATE_TOKENS.findall(path.read_text(encoding="utf-8"))
        if found:
            print(f"   {path.relative_to(SRC).as_posix()}: {sorted(set(found))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
