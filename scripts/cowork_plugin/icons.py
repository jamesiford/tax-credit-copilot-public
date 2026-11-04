"""The two PNG icons the package carries: rendered from the agent icon SVGs. [CH-15b]

Until CH-15b these were drawn here from first principles (a ring and a dot). The package now
carries the same mark as the Teams / Copilot listing: `scripts/render-icons.py` renders
`channels/branding/*.svg` into the gitignored `dist/branding/`, and the build reads those PNGs.
Rendered output is the same bytes for the same renderer, so two builds of the same inputs still
hash the same; the PNG hashes are recorded in the build manifest next to the zip, never in a
tracked file.
"""
from __future__ import annotations

from pathlib import Path

from branding_icons.png import png_size  # noqa: F401 - re-exported: the manifest validator reads sizes through here
from branding_icons.render import COLOR, DEFAULT_OUT, OUTLINE, load_rendered, render_icons
from branding_icons.renderers import RendererUnavailable

COLOR_SIZE, OUTLINE_SIZE = COLOR.pixels, OUTLINE.pixels


class IconError(RuntimeError):
    """The icons could not be had; the message says what to run."""


def icon_files(icon_dir: Path = DEFAULT_OUT) -> dict[str, bytes]:
    """The package's `color.png` and `outline.png`, from `icon_dir`, rendering them first when absent.

    A file that exists but is the wrong size or lacks an alpha channel is an error rather than a
    reason to re-render: a stale or hand-edited icon should be noticed, not silently replaced.
    """
    try:
        rendered = load_rendered(icon_dir)
    except FileNotFoundError:
        try:
            render_icons(icon_dir)
            rendered = load_rendered(icon_dir)
        except RendererUnavailable as exc:
            raise IconError(str(exc)) from exc
    except ValueError as exc:
        raise IconError(f"{icon_dir}: {exc}. Delete it and run scripts/render-icons.py.") from exc
    return {"color.png": rendered[COLOR.filename], "outline.png": rendered[OUTLINE.filename]}
