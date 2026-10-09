"""Fail on a relative Markdown link that does not resolve.

    python scripts/check-links.py            # every tracked *.md file
    python scripts/check-links.py docs/x.md  # just these

Checks `[text](target)` and `[label]: target` links whose target is a path:
URLs (http, https, mailto), pure anchors (#...) and absolute paths are
skipped. A target resolves relative to the linking file; a `#fragment` is
ignored, so a link to a heading in an existing file passes. Fenced code blocks
and inline code are skipped, because a path in an example is not a link.

Exit codes: 0 every link resolves · 1 at least one is broken.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

_INLINE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+\"[^\"]*\")?\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN = re.compile(r"`[^`]*`")
_SKIP = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#|/)", re.IGNORECASE)


def tracked_markdown() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode("utf-8")
    return [ROOT / name for name in out.split("\0") if name]


def links(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        line = _CODE_SPAN.sub("", line)
        found.extend((number, match.group(1)) for match in _INLINE.finditer(line))
        reference = _REFERENCE.match(line)
        if reference:
            found.append((number, reference.group(1)))
    return found


def broken(path: Path) -> list[str]:
    problems: list[str] = []
    for number, target in links(path.read_text(encoding="utf-8", errors="replace")):
        if _SKIP.match(target):
            continue
        relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not relative:
            continue
        if not (path.parent / relative).exists():
            problems.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {target}")
    return problems


def main(argv: list[str]) -> int:
    files = [Path(arg).resolve() for arg in argv] if argv else tracked_markdown()
    problems = [problem for path in files for problem in broken(path)]
    for problem in problems:
        print(problem)
    print(f"checked {len(files)} file(s): {len(problems)} broken link(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
