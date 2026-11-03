"""Token discipline gate. Static, no browser needed. Dev tooling.

Fails when the design system's own files step around the tokens:

  1. a literal colour (hex, rgb/rgba/hsl, or a named colour) in
     `src/components/ui/*.css` or `src/pages/Styleguide.css`;
  2. a `px` value in font-size, padding, margin, gap or border-radius in the same
     files (`0` is fine; `1px` borders, outlines and sizes are not spacing);
  3. `style={{` anywhere in `src/` except the two documented exceptions.

New CSS goes in files next to its component and is held to this; the legacy
`index.css` is migrated opportunistically and reported by design_metrics.py.

    python frontend/tools/check_tokens.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
UI_CSS = [*sorted((SRC / "components" / "ui").glob("*.css")), SRC / "pages" / "Styleguide.css"]

# The two places an inline style is correct, each carrying a comment saying why:
# a width computed per render, and a library prop that takes style objects.
STYLE_EXCEPTIONS = {"App.jsx", "FootprintMap.jsx"}

NAMED = r"\b(white|black|red|green|blue|gray|grey|orange|yellow|purple|pink|navy|teal)\b"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FUNC = re.compile(r"\b(rgba?|hsla?)\(", re.I)
SPACING = re.compile(r"\b(font-size|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?|gap|row-gap|column-gap|border-radius)\s*:\s*([^;{}]+);")
PX = re.compile(r"(?<![\w.-])\d*\.?\d+px")


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def check_css(path: Path) -> list[str]:
    problems = []
    for number, line in enumerate(strip_comments(path.read_text(encoding="utf-8")).splitlines(), 1):
        if HEX.search(line) or FUNC.search(line):
            problems.append(f"{path.name}:{number}: literal colour: {line.strip()}")
        elif re.search(NAMED, line, re.I) and re.search(r":\s*[^;]*" + NAMED, line, re.I) and "var(" not in line:
            problems.append(f"{path.name}:{number}: named colour: {line.strip()}")
        for prop, value in SPACING.findall(line):
            if PX.search(value) and "var(" not in value.split("px")[0][-12:]:
                problems.append(f"{path.name}:{number}: px in {prop}: {line.strip()}")
    return problems


def check_inline_styles() -> list[str]:
    problems = []
    for path in sorted(SRC.rglob("*.jsx")):
        if path.name.endswith(".test.jsx") or path.name in STYLE_EXCEPTIONS:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "style={{" in line:
                problems.append(f"{path.relative_to(SRC)}:{number}: inline style: {line.strip()}")
    return problems


def main() -> int:
    problems = [p for css in UI_CSS if css.exists() for p in check_css(css)] + check_inline_styles()
    for problem in problems:
        print(problem)
    print(f"\ncheck_tokens: {len(UI_CSS)} stylesheets, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
