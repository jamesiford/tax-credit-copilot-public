"""publish-m365.ps1 and the agent icon: what is sent, what is refused, what is never printed. [CH-15b]

The Microsoft 365 publish API takes `colorIconBase64` (192x192 PNG) and `outlineIconBase64` (32x32 PNG).
A wrong icon is found by the service only after a version number is spent and the listing may show a
default, so the script validates the PNG signature and size first. The base64 is large and is the
artwork itself, so it is sent to `az` through the temp body file and never printed. Same fake-`az`
harness as `test_publish_m365.py`; nothing reaches Azure.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

from tests import publish_shim as shim
from tests.png_fixtures import solid_png
from tests.test_publish_m365 import REPO, SCRIPT, run, said

pytestmark = pytest.mark.skipif(shim.PWSH is None, reason="PowerShell 7 (pwsh) is not installed")

PUBLISH_FIELDS = {"agentDisplayName", "botServiceArmId", "publishScope", "publishAsAutopilot", "appVersion", "shortDescription",
                  "fullDescription", "developerName", "developerWebsiteUrl", "privacyUrl", "termsOfUseUrl"}


@pytest.fixture
def icons(tmp_path):
    folder = tmp_path / "icons"
    folder.mkdir()
    color, outline = folder / "color.png", folder / "outline.png"
    color.write_bytes(solid_png(192, alpha=False))
    outline.write_bytes(solid_png(32, alpha=True))
    return color, outline


def with_icons(color, outline):
    return ["-ColorIconPath", str(color), "-OutlineIconPath", str(outline)]


def posts(fake):
    return fake.rest("post")


def test_both_icons_are_sent_in_the_publish_body_and_the_package_download(tmp_path, icons):
    color, outline = icons
    fake, done = run(tmp_path, *with_icons(color, outline), icons=True)
    assert done.returncode == 0, said(done)
    publish, download = posts(fake)
    for body in (publish["body"], download["body"]):
        assert set(body) == PUBLISH_FIELDS | {"colorIconBase64", "outlineIconBase64"}
        assert base64.b64decode(body["colorIconBase64"]) == color.read_bytes()
        assert base64.b64decode(body["outlineIconBase64"]) == outline.read_bytes()


def test_one_icon_alone_is_sent_without_the_other(tmp_path, icons):
    color, _ = icons
    fake, done = run(tmp_path, "-ColorIconPath", str(color), "-OutlineIconPath", "", icons=True)
    assert done.returncode == 0, said(done)
    assert set(posts(fake)[0]["body"]) == PUBLISH_FIELDS | {"colorIconBase64"}


def test_the_icons_survive_a_version_bump(tmp_path, icons):
    scenario = shim.default_scenario()
    shim.route(scenario, "publish", {"exit": 1, "stderr": "Version 1.0.3 already exists."}, {"stdout": {"titleId": "T_example-title-id"}})
    fake, done = run(tmp_path, *with_icons(*icons), "-AppVersion", "1.0.3", scenario=scenario, icons=True)
    assert done.returncode == 0, said(done)
    bodies = [p["body"] for p in posts(fake)]
    assert [b["appVersion"] for b in bodies] == ["1.0.3", "1.0.4", "1.0.4"]
    assert all("colorIconBase64" in b and "outlineIconBase64" in b for b in bodies)


@pytest.mark.parametrize("which,make,message", [
    ("color", lambda: solid_png(32, alpha=False), "must be 192x192 pixels"),
    ("color", lambda: solid_png(512, alpha=False), "must be 192x192 pixels"),
    ("outline", lambda: solid_png(192, alpha=True), "must be 32x32 pixels"),
    ("outline", lambda: solid_png(32, alpha=False), "must be an RGBA PNG"),
    ("color", lambda: b"GIF89a" + b"\x00" * 64, "is not a PNG"),
    ("outline", lambda: b"\xff\xd8\xff\xe0" + b"\x00" * 64, "is not a PNG"),
    ("color", lambda: b"\x89PNG", "is not a PNG"),
])
def test_a_wrong_icon_is_refused_before_any_request_is_made(tmp_path, icons, which, make, message):
    color, outline = icons
    (color if which == "color" else outline).write_bytes(make())
    fake, done = run(tmp_path, *with_icons(color, outline), icons=True)
    assert done.returncode != 0 and message in said(done)
    assert fake.calls() == [], "nothing was sent, no version was spent"


def test_an_explicit_icon_path_that_does_not_exist_is_an_error_not_a_silent_default(tmp_path, icons):
    fake, done = run(tmp_path, "-ColorIconPath", str(tmp_path / "missing.png"), "-OutlineIconPath", str(icons[1]), icons=True)
    assert done.returncode != 0 and "does not exist" in said(done) and fake.calls() == []


def test_the_base64_is_never_printed_and_whatif_shows_lengths_instead(tmp_path, icons):
    color, outline = icons
    secret = base64.b64encode(color.read_bytes()).decode()
    for whatif in (False, True):
        work = tmp_path / f"whatif-{whatif}"
        work.mkdir()
        fake, done = run(work, *with_icons(color, outline), icons=True, whatif=whatif)
        assert done.returncode == 0, said(done)
        assert secret[:40] not in said(done) and base64.b64encode(outline.read_bytes()).decode()[:40] not in said(done)
        assert "base64 characters" in said(done)
        if whatif:
            assert f"<{len(secret)} base64 characters>" in done.stdout, "WhatIf prints the length of what would be sent"
            assert posts(fake) == []
        else:
            assert posts(fake)[0]["body"]["colorIconBase64"] == secret, "but the real request carries it"


@pytest.fixture
def tree(tmp_path):
    """The script copied into a scratch repo layout, so its dist/branding default can be controlled."""
    (tmp_path / "repo" / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, tmp_path / "repo" / "scripts" / SCRIPT.name)
    return tmp_path / "repo"


def run_copy(tree, work, *extra):
    fake = shim.install(work)
    arguments = [shim.PWSH, "-NoProfile", "-NonInteractive", "-File", str(tree / "scripts" / SCRIPT.name), *shim.required_arguments(),
                 "-OutputDir", str(work / "out"), *extra]
    done = subprocess.run(arguments, capture_output=True, text=True, env=fake.environment(), timeout=180)
    return fake, done


def test_the_rendered_icons_under_dist_branding_are_the_default(tree, tmp_path):
    (tree / "dist" / "branding").mkdir(parents=True)
    (tree / "dist" / "branding" / "color-192.png").write_bytes(solid_png(192, alpha=False))
    (tree / "dist" / "branding" / "outline-32.png").write_bytes(solid_png(32, alpha=True))
    work = tmp_path / "work"
    work.mkdir()
    fake, done = run_copy(tree, work)
    assert done.returncode == 0, said(done)
    assert set(posts(fake)[0]["body"]) == PUBLISH_FIELDS | {"colorIconBase64", "outlineIconBase64"}


def test_without_rendered_icons_the_publish_still_works_and_says_so(tree, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    fake, done = run_copy(tree, work)
    assert done.returncode == 0, said(done)
    assert set(posts(fake)[0]["body"]) == PUBLISH_FIELDS and "No custom icons" in done.stdout


def test_a_stale_wrong_sized_default_is_refused_not_ignored(tree, tmp_path):
    (tree / "dist" / "branding").mkdir(parents=True)
    (tree / "dist" / "branding" / "color-192.png").write_bytes(solid_png(64, alpha=False))
    work = tmp_path / "work"
    work.mkdir()
    fake, done = run_copy(tree, work)
    assert done.returncode != 0 and "must be 192x192" in said(done) and fake.calls() == []


def test_the_default_developer_name_fits_the_platforms_32_characters_and_a_longer_one_is_refused(tmp_path):
    fake, done = run(tmp_path)
    name = posts(fake)[0]["body"]["developerName"]
    assert done.returncode == 0 and 0 < len(name) <= 32, name
    other = tmp_path / "long"
    other.mkdir()
    fake, done = run(other, "-DeveloperName", "x" * 33)
    assert done.returncode != 0 and fake.calls() == []
    exact = tmp_path / "exact"
    exact.mkdir()
    _, done = run(exact, "-DeveloperName", "x" * 32)
    assert done.returncode == 0, said(done)


def test_the_script_documents_both_icon_parameters():
    source = (REPO / "scripts" / "publish-m365.ps1").read_text(encoding="utf-8")
    for fragment in ("ColorIconPath", "OutlineIconPath", "colorIconBase64", "outlineIconBase64"):
        assert fragment in source
    assert Path(REPO / "scripts" / "render-icons.py").is_file()
