"""Design-system metrics for index.css and the components. Dev tooling.

Counts the things a scale is supposed to make boring: font sizes, radii, raw
spacing, inline styles. Run before and after a migration; the numbers are the
gate.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "src" / "index.css"


def root_bounds(text: str) -> tuple[int, int]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(":root {"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    return start, end


def outside_root(text: str) -> str:
    lines = text.splitlines()
    start, end = root_bounds(text)
    return "\n".join(lines[:start] + lines[end + 1:])


def show(title: str, counter: Counter, limit: int = 40) -> None:
    total = sum(counter.values())
    print(f"\n{title}: {len(counter)} distinct, {total} uses")
    for value, count in counter.most_common(limit):
        print(f"   {count:>4}  {value}")


def main() -> int:
    text = CSS.read_text(encoding="utf-8")
    body = outside_root(text)

    sizes = Counter(re.findall(r"font-size:\s*([0-9.]+px)", body))
    show("font-size", sizes)
    half = {k: v for k, v in sizes.items() if "." in k}
    print(f"   -> half-pixel: {len(half)} distinct, {sum(half.values())} uses")

    radii = Counter(re.findall(r"border-radius:\s*([^;]+);", body))
    show("border-radius", radii)

    # Raw px in padding/margin. Counted even when the declaration ALSO uses a
    # token: `padding: 58px var(--space-9) 40px` is still two raw values, and
    # skipping mixed declarations is how a migration looks finished when it is
    # not.
    raw_space = Counter()
    for prop in ("padding", "margin"):
        for match in re.finditer(rf"\b{prop}(?:-\w+)?:\s*([^;]+);", body):
            value = match.group(1).strip()
            for number in re.findall(r"\d+(?:\.\d+)?px", value):
                raw_space[f"{prop}: {value}  <- {number}"] += 1
    show("raw px padding/margin", raw_space, limit=25)
    print(f"   -> {sum(raw_space.values())} raw values total")

    inline = Counter()
    for path in sorted((ROOT / "src").rglob("*.jsx")):
        if path.name.endswith(".test.jsx"):
            continue
        hits = len(re.findall(r"style=\{\{", path.read_text(encoding="utf-8")))
        if hits:
            inline[path.relative_to(ROOT / "src").as_posix()] = hits
    show("inline style={{ }}", inline, limit=30)
    print(f"   -> {sum(inline.values())} total")

    return 0


if __name__ == "__main__":
    sys.exit(main())
