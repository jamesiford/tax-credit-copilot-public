"""The agent icon: SVG sources tracked, PNGs rendered into dist/, one mark for the listing and the plugin. [CH-15b]

Three things must stay true. Only SVG artwork is ever tracked (a committed raster fails the export
audit). The rendered PNGs have the shape Teams and the Cowork manifest need: 192x192 colour with
transparent rounded corners, 32x32 outline that is white on transparent. And the Cowork package
carries exactly the rendered bytes, reproducibly, with their hashes recorded beside the zip rather
than in a tracked file. Tests that need a renderer skip with a reason when none is installed (the
permitted dependency-availability skip); on a machine with Chromium or Cairo they run.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from branding_icons import render as render_module  # noqa: E402
from branding_icons import renderers  # noqa: E402
from branding_icons.png import color_type, decode_rgba, is_png, png_size  # noqa: E402
from cowork_plugin import icons, package  # noqa: E402
from cowork_plugin.findings import errors  # noqa: E402
from cowork_plugin.validate_content import validate_neutrality  # noqa: E402
from tests.channel.test_cowork_package import settings  # noqa: E402
from tests.png_fixtures import solid_png  # noqa: E402

BRANDING = REPO / "channels" / "branding"
RASTER = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".tif", ".tiff", ".icns")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """The two icons and a preview rendered once for the module; skips (with the reason) when no renderer works."""
    folder = tmp_path_factory.mktemp("branding")
    try:
        render_module.render_icons(folder, preview=True)
    except renderers.RendererUnavailable as exc:
        pytest.skip(f"no SVG renderer available: {exc}")
    return folder


def pixels(path: Path):
    return decode_rgba(path.read_bytes())


# ------------------------------------------------------------------ what is tracked


def test_the_tracked_artwork_is_svg_only_and_customer_neutral():
    names = sorted(p.name for p in BRANDING.iterdir())
    assert names == ["agent-icon-outline.svg", "agent-icon.svg"]
    files = {p.name: p.read_bytes() for p in BRANDING.iterdir()}
    assert errors(validate_neutrality(files)) == []
    assert (BRANDING / "agent-icon.svg").read_text(encoding="utf-8").lstrip().startswith("<svg")
    assert 'viewBox="0 0 192 192"' in (BRANDING / "agent-icon.svg").read_text(encoding="utf-8")
    assert 'viewBox="0 0 32 32"' in (BRANDING / "agent-icon-outline.svg").read_text(encoding="utf-8")


def test_no_raster_file_is_tracked_anywhere_in_the_repository():
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    if tracked.returncode != 0:
        assert not (REPO / ".git").exists(), tracked.stderr
        return
    assert [f for f in tracked.stdout.splitlines() if f.lower().endswith(RASTER)] == []


def test_rendered_output_is_gitignored_so_a_png_cannot_be_committed_by_accident():
    for name in ("color-192.png", "outline-32.png", "color-512.png"):
        done = subprocess.run(["git", "check-ignore", "-q", f"dist/branding/{name}"], cwd=REPO)
        assert done.returncode in (0, 128)
        assert done.returncode == 0 or "dist/" in (REPO / ".gitignore").read_text(encoding="utf-8")


def test_the_web_apps_neutral_brand_mark_is_not_the_agent_icon():
    brand = (REPO / "frontend" / "public" / "brand-mark.svg").read_bytes()
    assert brand != (BRANDING / "agent-icon.svg").read_bytes()


def test_the_m365_readme_links_the_icon_by_a_relative_path():
    readme = (REPO / "docs" / "m365-channel" / "README.md").read_text(encoding="utf-8")
    assert "../../channels/branding/agent-icon.svg" in readme


# --------------------------------------------------------------- the PNG reader


def test_the_png_reader_reads_size_colour_type_and_pixels():
    data = solid_png(4, alpha=True, pixel=(10, 20, 30, 40))
    assert is_png(data) and png_size(data) == (4, 4) and color_type(data) == 6
    width, height, found = decode_rgba(data)
    assert (width, height) == (4, 4) and found == [(10, 20, 30, 40)] * 16
    assert decode_rgba(solid_png(2, alpha=False))[2][0] == (13, 40, 115, 255)


@pytest.mark.parametrize("bad", [b"", b"GIF89a" + b"\0" * 40, b"\x89PNG\r\n\x1a\n" + b"\0" * 8])
def test_the_png_reader_refuses_a_non_png(bad):
    assert not is_png(bad)
    with pytest.raises(ValueError):
        png_size(bad)


# --------------------------------------------------------- the renderer choice


def test_no_usable_renderer_gives_one_error_that_says_how_to_install_one(monkeypatch):
    def broken(items):
        raise renderers.RendererUnavailable("pretend")

    monkeypatch.setattr(renderers, "RENDERERS", {"cairosvg": broken, "chromium": broken})
    with pytest.raises(renderers.RendererUnavailable, match=r"requirements-icons\.txt.*cairosvg: pretend; chromium: pretend"):
        renderers.render([(b"<svg/>", 8)])


def test_the_first_working_renderer_wins_and_a_named_one_is_used_alone(monkeypatch):
    def broken(items):
        raise renderers.RendererUnavailable("no cairo")

    monkeypatch.setattr(renderers, "RENDERERS", {"cairosvg": broken, "chromium": lambda items: [b"png"] * len(items)})
    assert renderers.render([(b"<svg/>", 8)]) == ("chromium", [b"png"])
    with pytest.raises(renderers.RendererUnavailable):
        renderers.render([(b"<svg/>", 8)], "cairosvg")


def test_the_command_line_exits_3_with_a_message_when_no_renderer_works(monkeypatch, capsys, tmp_path):
    spec = importlib.util.spec_from_file_location("render_icons_cli", REPO / "scripts" / "render-icons.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def unavailable(*args, **kwargs):
        raise renderers.RendererUnavailable("no renderer here")

    monkeypatch.setattr(cli, "render_icons", unavailable)
    assert cli.main(["--out", str(tmp_path)]) == 3
    assert "no renderer here" in capsys.readouterr().err


def test_a_stale_or_wrong_shaped_icon_is_an_error_not_a_silent_rerender(tmp_path):
    (tmp_path / "color-192.png").write_bytes(solid_png(64, alpha=True))
    (tmp_path / "outline-32.png").write_bytes(solid_png(32, alpha=True))
    with pytest.raises(icons.IconError, match="must be 192x192"):
        icons.icon_files(tmp_path)
    (tmp_path / "color-192.png").write_bytes(solid_png(192, alpha=True))
    (tmp_path / "outline-32.png").write_bytes(solid_png(32, alpha=False))
    with pytest.raises(icons.IconError, match="RGBA"):
        icons.icon_files(tmp_path)


def test_missing_icons_and_no_renderer_is_an_error_and_fails_the_build_with_a_finding(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise renderers.RendererUnavailable("no renderer here")

    monkeypatch.setattr(icons, "render_icons", unavailable)
    with pytest.raises(icons.IconError, match="no renderer here"):
        icons.icon_files(tmp_path / "empty")
    original = icons.icon_files
    monkeypatch.setattr(icons, "icon_files", lambda: original(tmp_path / "empty"))
    with pytest.raises(package.BuildError) as raised:
        package.build(settings(tmp_path), tmp_path / "out")
    assert {f.code for f in raised.value.findings} == {"TCC-I001"} and "no renderer here" in str(raised.value.findings[0])
    assert not (tmp_path / "out" / package.ZIP_NAME).exists(), "nothing is written"


# ------------------------------------------------------- the rendered pixels


def test_the_colour_icon_is_192_square_with_transparent_rounded_corners_and_an_opaque_body(rendered):
    path = rendered / "color-192.png"
    width, height, found = pixels(path)
    assert (width, height) == (192, 192) and color_type(path.read_bytes()) == 6
    at = lambda x, y: found[y * width + x]  # noqa: E731
    for corner in ((0, 0), (191, 0), (0, 191), (191, 191)):
        assert at(*corner)[3] == 0, f"corner {corner} must be transparent (rounded tile)"
    assert at(96, 150)[3] == 255 and at(20, 96)[3] == 255, "the tile body is opaque"
    r, g, b, _ = at(10, 96)
    assert b > r and b > 100, "navy-to-royal-blue tile"


def test_the_outline_icon_is_32_square_rgba_and_only_white_on_transparent(rendered):
    path = rendered / "outline-32.png"
    width, height, found = pixels(path)
    assert (width, height) == (32, 32) and color_type(path.read_bytes()) == 6
    visible = [p for p in found if p[3] > 0]
    assert len(visible) > 60 and len(found) - len(visible) > 400, "a mark on a transparent field"
    assert all(min(p[:3]) >= 250 for p in visible), "every painted pixel is white (alpha carries the edge)"
    assert found[0][3] == 0 and found[-1][3] == 0


def test_the_preview_is_512_square_and_rendering_is_repeatable(rendered, tmp_path):
    assert png_size((rendered / "color-512.png").read_bytes()) == (512, 512)
    again = render_module.render_icons(tmp_path)
    for name in ("color-192.png", "outline-32.png"):
        assert again[name].read_bytes() == (rendered / name).read_bytes(), "same renderer, same bytes"


def test_load_rendered_returns_the_two_png_files_and_hashes_them(rendered):
    files = render_module.load_rendered(rendered)
    assert set(files) == {"color-192.png", "outline-32.png"}
    assert render_module.hashes(files)["color-192.png"] == hashlib.sha256(files["color-192.png"]).hexdigest()


# ---------------------------------------------------------- the Cowork build


def test_the_cowork_package_carries_exactly_the_rendered_icons_and_records_their_hashes(rendered, tmp_path):
    files = icons.icon_files(rendered)
    assert files["color.png"] == (rendered / "color-192.png").read_bytes()
    result = package.build(settings(tmp_path), tmp_path / "out", icon_files=files)
    with zipfile.ZipFile(result.zip_path) as archive:
        assert archive.read("color.png") == files["color.png"] and archive.read("outline.png") == files["outline.png"]
    recorded = json.loads((tmp_path / "out" / package.BUILD_MANIFEST).read_text(encoding="utf-8"))
    assert recorded["sha256"] == result.sha256 == hashlib.sha256(result.zip_path.read_bytes()).hexdigest()
    assert recorded["icons"] == {name: hashlib.sha256(files[name]).hexdigest() for name in ("color.png", "outline.png")}
    assert set(recorded["files"]) >= {"manifest.json", "color.png", "outline.png"}


def test_two_builds_from_the_same_rendered_icons_hash_the_same_and_a_different_icon_changes_it(rendered, tmp_path):
    files = icons.icon_files(rendered)
    first = package.build(settings(tmp_path), tmp_path / "a", icon_files=files)
    second = package.build(settings(tmp_path), tmp_path / "b", icon_files=files)
    assert first.sha256 == second.sha256
    other = package.build(settings(tmp_path), tmp_path / "c", icon_files={**files, "outline.png": solid_png(32, alpha=True)})
    assert other.sha256 != first.sha256


def test_the_build_manifest_is_build_output_and_never_inside_the_tracked_tree(tmp_path):
    result = package.build(settings(tmp_path), tmp_path / "out", icon_files={"color.png": solid_png(192, alpha=True),
                                                                          "outline.png": solid_png(32, alpha=True)})
    assert (tmp_path / "out" / package.BUILD_MANIFEST).is_file() and result.zip_path.parent == tmp_path / "out"
    done = subprocess.run(["git", "check-ignore", "-q", f"dist/{package.BUILD_MANIFEST}"], cwd=REPO)
    assert done.returncode in (0, 128)
