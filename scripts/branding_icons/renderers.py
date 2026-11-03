"""The two ways to turn an SVG into a PNG, and the choice between them. [CH-15b]

The repository tracks the icon as SVG only (a committed raster fails the export audit), so a
PNG exists only as build output. `cairosvg` is preferred: pure Python plus the Cairo library.
On Windows the Cairo DLL is usually absent, so Playwright's Chromium (already a frontend
tooling dependency) is the fallback. Both are dev-only and neither is in backend/requirements.txt.
"""
from __future__ import annotations

import base64
from collections.abc import Callable

_PAGE = (
    '<!doctype html><html><body style="margin:0;background:transparent">'
    '<img id="i" width="{size}" height="{size}" src="data:image/svg+xml;base64,{payload}"></body></html>'
)


class RendererUnavailable(RuntimeError):
    """No SVG renderer can run here; the message says how to install one."""


def render_cairosvg(items: list[tuple[bytes, int]]) -> list[bytes]:
    """Render each `(svg, pixels)` with cairosvg; `RendererUnavailable` when it or Cairo is missing."""
    try:
        import cairosvg
    except (ImportError, OSError) as exc:
        raise RendererUnavailable(f"cairosvg is not usable here ({exc.__class__.__name__}: {exc})") from exc
    return [cairosvg.svg2png(bytestring=svg, output_width=size, output_height=size) for svg, size in items]


def render_chromium(items: list[tuple[bytes, int]]) -> list[bytes]:
    """Render each `(svg, pixels)` in headless Chromium with a transparent background."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise RendererUnavailable("playwright is not installed") from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                return [_screenshot(browser, svg, size) for svg, size in items]
            finally:
                browser.close()
    except Error as exc:
        raise RendererUnavailable(f"Chromium could not start ({str(exc).splitlines()[0]})") from exc


def _screenshot(browser, svg: bytes, size: int) -> bytes:
    page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
    try:
        page.set_content(_PAGE.format(size=size, payload=base64.b64encode(svg).decode()))
        page.evaluate("document.getElementById('i').decode()")
        return page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": size, "height": size})
    finally:
        page.close()


RENDERERS: dict[str, Callable[[list[tuple[bytes, int]]], list[bytes]]] = {
    "cairosvg": render_cairosvg,
    "chromium": render_chromium,
}

INSTALL_HINT = (
    "no SVG renderer is available. Install one: `pip install -r scripts/requirements-icons.txt` "
    "(cairosvg needs the Cairo library; on Windows use Chromium: `python -m playwright install chromium`)."
)


def render(items: list[tuple[bytes, int]], renderer: str = "auto") -> tuple[str, list[bytes]]:
    """Render with the named renderer, or the first that works under `auto`; returns `(name, pngs)`."""
    if renderer != "auto":
        return renderer, RENDERERS[renderer](items)
    reasons = []
    for name, function in RENDERERS.items():
        try:
            return name, function(items)
        except RendererUnavailable as exc:
            reasons.append(f"{name}: {exc}")
    raise RendererUnavailable(INSTALL_HINT + " Tried: " + "; ".join(reasons))
