"""Before / after contact sheet. Dev tooling, not shipped.

    python frontend/tools/compare.py before after-modern            # -> sweep-output/compare-before-vs-after-modern.html
    python frontend/tools/compare.py before after-modern --diff 2   # also list pairs differing by more than 2%

Pairs screenshots by file name from two folders under `sweep-output/` and writes
ONE self-contained HTML file: a side-by-side row per page (before | after | the
changed pixels in red), with the share of pixels that changed. Images are
inlined as base64 so the file can be opened or sent without the folders; because
the screenshots may render data, the HTML is as gitignored as they are
(`sweep-output/` is) and must never be committed.

It reads only what `shoot_pages.py` wrote. A name present on one side only is
listed as "new" or "removed" rather than silently skipped.
"""
from __future__ import annotations

import base64
import html
import io
import sys
from pathlib import Path

from PIL import Image, ImageChops

OUT = Path(__file__).parent / "sweep-output"


def b64(img: Image.Image, width: int = 640) -> str:
    img = img.convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def changed(a: Image.Image, b: Image.Image) -> tuple[float, Image.Image]:
    """Share of pixels that differ, and a red overlay of where."""
    size = (max(a.width, b.width), max(a.height, b.height))
    pa = Image.new("RGB", size, "white"); pa.paste(a.convert("RGB"))
    pb = Image.new("RGB", size, "white"); pb.paste(b.convert("RGB"))
    diff = ImageChops.difference(pa, pb).convert("L").point(lambda v: 255 if v > 24 else 0)
    share = sum(1 for v in diff.getdata() if v) / (size[0] * size[1])
    red = Image.new("RGB", size, "white")
    red.paste(Image.new("RGB", size, (214, 40, 40)), mask=diff)
    return share, red


def main() -> int:
    argv = sys.argv[1:]
    threshold = None
    if "--diff" in argv:
        i = argv.index("--diff")
        threshold = float(argv[i + 1]) / 100
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2
    before_dir, after_dir = OUT / args[0], OUT / args[1]
    before = {p.name: p for p in before_dir.glob("*.png")}
    after = {p.name: p for p in after_dir.glob("*.png")}

    rows, flagged = [], []
    for name in sorted(set(before) | set(after)):
        if name in before and name in after:
            a, b = Image.open(before[name]), Image.open(after[name])
            share, red = changed(a, b)
            if threshold is not None and share > threshold:
                flagged.append((name, share))
            rows.append(
                f"<section><h2>{html.escape(name)} <small>{share * 100:.1f}% of pixels changed</small></h2>"
                f"<div class='row'><figure><figcaption>before</figcaption><img src='data:image/png;base64,{b64(a)}'></figure>"
                f"<figure><figcaption>after</figcaption><img src='data:image/png;base64,{b64(b)}'></figure>"
                f"<figure><figcaption>changed</figcaption><img src='data:image/png;base64,{b64(red)}'></figure></div></section>"
            )
        else:
            side = "new" if name in after else "removed"
            src = after.get(name) or before.get(name)
            rows.append(
                f"<section><h2>{html.escape(name)} <small>{side}</small></h2>"
                f"<div class='row'><figure><img src='data:image/png;base64,{b64(Image.open(src))}'></figure></div></section>"
            )

    page = (
        "<!doctype html><meta charset='utf-8'><title>Before / after</title>"
        "<style>body{font:14px system-ui;margin:24px;background:#f4f5f8;color:#1b2559}"
        "h2{font-size:15px;margin:24px 0 8px}small{font-weight:400;color:#555}"
        ".row{display:flex;gap:12px;align-items:flex-start}figure{margin:0;flex:1;min-width:0}"
        "figcaption{font-size:12px;color:#555;margin-bottom:4px}img{width:100%;border:1px solid #ccd;background:#fff}</style>"
        f"<h1>{html.escape(args[0])} vs {html.escape(args[1])}</h1>" + "".join(rows)
    )
    target = OUT / f"compare-{args[0]}-vs-{args[1]}.html"
    target.write_text(page, encoding="utf-8")
    print(f"{target}  ({len(rows)} pair(s), {target.stat().st_size / 1024 / 1024:.1f} MB)")
    for name, share in sorted(flagged, key=lambda x: -x[1]):
        print(f"  changed {share * 100:5.1f}%  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
