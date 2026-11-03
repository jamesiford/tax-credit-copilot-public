"""Design-system metrics for the stylesheets and components. Dev tooling.

Counts the things a scale is supposed to make boring: type steps in use, raw
font sizes, radii, raw spacing, inline styles and the deprecated token aliases.
Run before and after a migration; the numbers are the gate.

    python frontend/tools/design_metrics.py

The token layers moved out of index.css into src/styles/tokens/, so everything
here is measured over the stylesheets that USE tokens (index.css and
components/ui/*.css), never over the files that DEFINE them.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOKENS = SRC / "styles" / "tokens"
CSS = SRC / "index.css"
UI_CSS = sorted((SRC / "components" / "ui").glob("*.css"))

DEPRECATED = [r"--accent(?:-strong|-bg)?", r"--accent-2(?:-strong|-bg|-line)?", r"--exp-[\w-]+"]


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def show(title: str, counter: Counter, limit: int = 40) -> None:
    total = sum(counter.values())
    print(f"\n{title}: {len(counter)} distinct, {total} uses")
    for value, count in counter.most_common(limit):
        print(f"   {count:>4}  {value}")


def scale(theme_file: str, selector: str) -> dict[str, str]:
    text = strip_comments((TOKENS / theme_file).read_text(encoding="utf-8"))
    block = text.split(selector)[1].split("\n}")[0]
    return dict(re.findall(r"(--text-(?:micro|caption|small|body|strong|subhead|title|display))\s*:\s*([^;]+);", block))


def main() -> int:
    body = strip_comments(CSS.read_text(encoding="utf-8"))
    ui = "\n".join(strip_comments(p.read_text(encoding="utf-8")) for p in UI_CSS)

    print("type scale per theme (chrome; data is --text-data, 12px in both)")
    modern = scale("theme-modern.css", ':root,\nhtml[data-theme="modern"] {')
    classic = scale("theme-classic.css", 'html[data-theme="classic"] {')
    for name in modern:
        print(f"   {name:<16} modern {modern[name]:<6} classic {classic.get(name, '?')}")

    tokens = Counter(re.findall(r"font-size:\s*var\((--text-[\w-]+)\)", body))
    show("font-size tokens in index.css", tokens)
    raw = Counter(re.findall(r"font-size:\s*([0-9.]+px)", body + ui))
    show("raw px font-size (a bug)", raw)
    print(f"   -> half-pixel: {sum(v for k, v in raw.items() if '.' in k)} uses")

    show("border-radius", Counter(re.findall(r"border-radius:\s*([^;]+);", body)))

    # Raw px in padding/margin. Counted even when the declaration ALSO uses a
    # token: `padding: 58px var(--space-9) 40px` is still two raw values.
    raw_space = Counter()
    for source in (body, ui):
        for prop in ("padding", "margin", "gap"):
            for match in re.finditer(rf"\b{prop}(?:-\w+)?:\s*([^;]+);", source):
                value = match.group(1).strip()
                for number in re.findall(r"(?<![\w.-])\d+(?:\.\d+)?px", value):
                    raw_space[f"{prop}: {value}  <- {number}"] += 1
    show("raw px padding/margin/gap", raw_space, limit=25)
    print(f"   -> {sum(raw_space.values())} raw values total")

    inline = Counter()
    for path in sorted(SRC.rglob("*.jsx")):
        if path.name.endswith(".test.jsx"):
            continue
        hits = len(re.findall(r"style=\{\{", path.read_text(encoding="utf-8")))
        if hits:
            inline[path.relative_to(SRC).as_posix()] = hits
    show("inline style={{ }}", inline, limit=30)
    print(f"   -> {sum(inline.values())} total")

    deprecated = Counter()
    for path in [*SRC.rglob("*.css"), *SRC.rglob("*.jsx")]:
        if TOKENS in path.parents or path.name.endswith(".test.jsx"):
            continue
        text = strip_comments(path.read_text(encoding="utf-8"))
        for pattern in DEPRECATED:
            for name in re.findall(rf"var\(({pattern})\b(?![\w-])", text):
                deprecated[name] += 1
    show("deprecated token aliases (ratchet: src/lib/tokens.test.js)", deprecated)
    print(f"   -> {sum(deprecated.values())} uses total")

    ui_literals = len(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", ui))
    print(f"\nliteral colours in components/ui/*.css: {ui_literals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
