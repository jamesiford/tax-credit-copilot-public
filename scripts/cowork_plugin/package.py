"""Assembles, validates and zips the plugin, byte for byte reproducibly. [CH-10]

Reproducible means two builds of the same sources and settings hash the same: entries
are sorted, every timestamp and permission is fixed, text files are normalised to LF
(a Windows checkout with `core.autocrlf` would otherwise change the hash of a file nobody
edited), and the icons are drawn deterministically. A hash you can recompute is how an
admin who uploaded a package to the tenant can prove it is the one that was reviewed.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cowork_plugin import icons, manifest as manifest_module
from cowork_plugin.findings import Finding, errors
from cowork_plugin.settings import PluginSettings
from cowork_plugin.validate_content import validate_neutrality, validate_tools
from cowork_plugin.validate_manifest import validate_manifest
from cowork_plugin.validate_skills import validate_skills

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "channels" / "cowork"
ZIP_NAME = "tcc-cowork-plugin.zip"
BUILD_MANIFEST = "tcc-cowork-plugin.build.json"
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_TEXT_SUFFIXES = (".md", ".json", ".svg", ".txt")


class BuildError(RuntimeError):
    """The package did not validate; `findings` says why."""

    def __init__(self, findings: list[Finding]) -> None:
        super().__init__("\n".join(str(f) for f in errors(findings)))
        self.findings = findings


@dataclass
class Build:
    """The result of one build: where it was written, its hash, and everything validation said."""

    zip_path: Path | None
    sha256: str
    files: dict[str, bytes]
    findings: list[Finding] = field(default_factory=list)


def _normalise(name: str, data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n") if name.endswith(_TEXT_SUFFIXES) else data


def collect_skills(root: Path) -> dict[str, bytes]:
    """Every file under `skills/`, keyed by its package path."""
    found: dict[str, bytes] = {}
    for path in sorted((root / "skills").rglob("*")):
        if path.is_file():
            name = path.relative_to(root).as_posix()
            found[name] = _normalise(name, path.read_bytes())
    return found


def assemble(settings: PluginSettings, root: Path = PLUGIN_ROOT,
             icon_files: dict[str, bytes] | None = None) -> tuple[dict[str, Any], dict[str, bytes]]:
    """The manifest and every file in the package, before validation.

    `icon_files` is `{"color.png": ..., "outline.png": ...}`; left out, the rendered agent icons are
    read from dist/branding (and rendered first when absent). `IconError` when they cannot be had.
    """
    document = manifest_module.render_manifest(root / "manifest.template.json", settings)
    files = {
        "manifest.json": manifest_module.dumps(document),
        **(icon_files if icon_files is not None else icons.icon_files()),
        **collect_skills(root),
    }
    if settings.manifest_version == "1.28":
        files[manifest_module.TOOL_FILE] = manifest_module.dumps(manifest_module.tool_description())
    return document, files


def validate(document: dict[str, Any], files: dict[str, bytes], settings: PluginSettings | None = None) -> list[Finding]:
    """Manifest, skills, tool references, and customer neutrality of the shipped skills."""
    shipped = {name: data for name, data in files.items() if name.startswith("skills/")}
    findings = validate_manifest(document, files) + validate_skills(document, files)
    findings += validate_tools(files) + validate_neutrality(shipped)
    if settings is not None:
        findings += [Finding("TCC-P001", key, "still holds a placeholder value", "warning") for key in settings.placeholders()]
    return findings


def write_zip(files: dict[str, bytes], target: Path) -> str:
    """Write the deterministic zip and return its SHA-256."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, _FIXED_TIME)
            entry.compress_type, entry.external_attr, entry.create_system = zipfile.ZIP_DEFLATED, 0o644 << 16, 3
            archive.writestr(entry, files[name])
    return hashlib.sha256(target.read_bytes()).hexdigest()


def build_manifest(files: dict[str, bytes], sha256: str) -> dict[str, Any]:
    """What a build produced, for the file written beside the zip: the package hash and each PNG's hash.

    Kept out of the tracked tree on purpose: the icon bytes depend on the renderer, so the hashes
    describe a build, not the sources.
    """
    return {
        "zip": ZIP_NAME, "sha256": sha256,
        "icons": {name: hashlib.sha256(files[name]).hexdigest() for name in ("color.png", "outline.png")},
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }


def build(settings: PluginSettings, out_dir: Path, *, strict: bool = False, root: Path = PLUGIN_ROOT,
          icon_files: dict[str, bytes] | None = None) -> Build:
    """Assemble, validate and (when there are no errors) zip. `strict` turns placeholder warnings into errors.

    Also writes `tcc-cowork-plugin.build.json` (hashes of the zip, the icons and every file) beside the zip.
    """
    try:
        document, files = assemble(settings, root, icon_files)
    except icons.IconError as exc:
        raise BuildError([Finding("TCC-I001", "icons", str(exc))]) from exc
    findings = validate(document, files, settings)
    if strict:
        findings = [Finding(f.code, f.path, f.message, "error") if f.code == "TCC-P001" else f for f in findings]
    if errors(findings):
        raise BuildError(findings)
    target = out_dir / ZIP_NAME
    digest = write_zip(files, target)
    (out_dir / BUILD_MANIFEST).write_text(json.dumps(build_manifest(files, digest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Build(target, digest, files, findings)
