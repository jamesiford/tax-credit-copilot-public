"""Render the agent icon PNGs from channels/branding/*.svg. [CH-15b]

    python scripts/render-icons.py                    # dist/branding/color-192.png + outline-32.png
    python scripts/render-icons.py --preview          # also color-512.png
    python scripts/render-icons.py --renderer chromium --out some/folder

The PNGs are build output (gitignored): publish-m365.ps1 and build-cowork-plugin.py read them.
Exit codes: 0 rendered · 3 no renderer available (the message says how to install one).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from branding_icons.render import DEFAULT_OUT, hashes, load_rendered, render_icons  # noqa: E402
from branding_icons.renderers import RENDERERS, RendererUnavailable  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default: dist/branding/, gitignored)")
    parser.add_argument("--renderer", choices=["auto", *RENDERERS], default="auto")
    parser.add_argument("--preview", action="store_true", help="also write a 512x512 colour preview")
    args = parser.parse_args(argv)
    try:
        written = render_icons(args.out, renderer=args.renderer, preview=args.preview)
        digests = hashes(load_rendered(args.out))
    except RendererUnavailable as exc:
        print(f"render-icons: {exc}", file=sys.stderr)
        return 3
    for name, path in written.items():
        print(f"wrote  {path}" + (f"  sha256 {digests[name]}" if name in digests else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
