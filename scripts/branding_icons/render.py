"""Render the agent icon from its SVG sources into a gitignored folder. [CH-15b]

One mark, three consumers: the Teams / Microsoft 365 Copilot listing (publish-m365.ps1 sends
the 192x192 colour and 32x32 outline PNGs), the Cowork plugin (build-cowork-plugin.py puts the
same two in the package), and previews. The SVGs under channels/branding/ are the only tracked
artwork; everything rendered here is build output under dist/branding/.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from branding_icons.png import color_type, png_size
from branding_icons.renderers import render

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "channels" / "branding"
DEFAULT_OUT = ROOT / "dist" / "branding"


@dataclass(frozen=True)
class IconSpec:
    """One output file: which SVG, how many pixels square, and whether the listing needs it."""

    filename: str
    source: str
    pixels: int
    required: bool = True


COLOR = IconSpec("color-192.png", "agent-icon.svg", 192)
OUTLINE = IconSpec("outline-32.png", "agent-icon-outline.svg", 32)
PREVIEW = IconSpec("color-512.png", "agent-icon.svg", 512, required=False)


def render_icons(out_dir: Path = DEFAULT_OUT, *, renderer: str = "auto", preview: bool = False,
                 source_dir: Path = SOURCE_DIR) -> dict[str, Path]:
    """Write the icons to `out_dir` and return `{filename: path}`; `RendererUnavailable` when none can run."""
    specs = [COLOR, OUTLINE] + ([PREVIEW] if preview else [])
    items = [((source_dir / spec.source).read_bytes(), spec.pixels) for spec in specs]
    _, pngs = render(items, renderer)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for spec, data in zip(specs, pngs, strict=True):
        written[spec.filename] = out_dir / spec.filename
        written[spec.filename].write_bytes(data)
    return written


def load_rendered(out_dir: Path = DEFAULT_OUT) -> dict[str, bytes]:
    """The two required PNGs already rendered into `out_dir`, checked for size and colour type.

    `FileNotFoundError` names the missing file; `ValueError` names a file that is the wrong shape,
    so a stale or hand-edited icon cannot reach a published listing or a package.
    """
    found = {}
    for spec, kind in ((COLOR, 2), (OUTLINE, 6)):
        data = (out_dir / spec.filename).read_bytes()
        if png_size(data) != (spec.pixels, spec.pixels):
            raise ValueError(f"{spec.filename} must be {spec.pixels}x{spec.pixels}")
        if kind == 6 and color_type(data) != 6:
            raise ValueError(f"{spec.filename} must be RGBA (a transparent background)")
        found[spec.filename] = data
    return found


def hashes(files: dict[str, bytes]) -> dict[str, str]:
    """SHA-256 of each PNG, for the build manifest."""
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
