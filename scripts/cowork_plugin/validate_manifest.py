"""Manifest checks, derived from the Cowork plugin documentation and the 1.28 / 1.29 schemas. [CH-10]

Not a copy of the schema: the keys this builder generates and the rules the platform
states (field lengths, HTTPS, the `referenceId` / `None` rule, the 1.28 tool file).
`wiqd plugin validate --mode deep` and `atk validate` remain the authority; this runs
offline, in CI, on every build.
"""
from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlparse

from cowork_plugin.findings import Finding
from cowork_plugin.icons import COLOR_SIZE, OUTLINE_SIZE, png_size

ROOT_KEYS = frozenset({
    "$schema", "manifestVersion", "version", "id", "developer", "name", "description", "icons",
    "accentColor", "agentSkills", "agentConnectors",
})
REQUIRED_ROOT = ("manifestVersion", "version", "id", "developer", "name", "description", "icons", "accentColor")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
AUTH_TYPES = ("None", "OAuthPluginVault", "ApiKeyPluginVault", "DynamicClientRegistration", "AzureKeyVault")


def _https(value: Any) -> bool:
    parsed = urlparse(value) if isinstance(value, str) else None
    return bool(parsed and parsed.scheme == "https" and parsed.netloc and "<" not in value)


def _limit(findings: list[Finding], path: str, value: Any, maximum: int) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        findings.append(Finding("TCC-M002", path, f"must be a string of 1-{maximum} characters"))


def _identity(manifest: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    for key in sorted(set(manifest) - ROOT_KEYS):
        found.append(Finding("TCC-M001", key, "not a field this package may carry (the schema is strict)"))
    for key in REQUIRED_ROOT:
        if key not in manifest:
            found.append(Finding("TCC-M001", key, "is required"))
    version = manifest.get("manifestVersion")
    if manifest.get("$schema") and f"/v{version}/" not in manifest["$schema"]:
        found.append(Finding("TCC-M003", "$schema", f"does not name manifest version {version}"))
    try:
        uuid.UUID(str(manifest.get("id")))
    except ValueError:
        found.append(Finding("TCC-M004", "id", "must be a UUID"))
    if not _SEMVER.match(str(manifest.get("version", ""))):
        found.append(Finding("TCC-M004", "version", "must be MAJOR.MINOR.PATCH"))
    if not _COLOR.match(str(manifest.get("accentColor", ""))):
        found.append(Finding("TCC-M004", "accentColor", "must be #RRGGBB"))
    return found


def _listing(manifest: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    developer = manifest.get("developer") or {}
    _limit(found, "developer.name", developer.get("name"), 32)
    for key in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
        if not _https(developer.get(key)):
            found.append(Finding("TCC-M005", f"developer.{key}", "must be an HTTPS URL"))
    for block, short, full in (("name", 30, 100), ("description", 80, 4000)):
        _limit(found, f"{block}.short", (manifest.get(block) or {}).get("short"), short)
        _limit(found, f"{block}.full", (manifest.get(block) or {}).get("full"), full)
    return found


def _icons(manifest: dict[str, Any], files: dict[str, bytes]) -> list[Finding]:
    found: list[Finding] = []
    for key, size in (("color", COLOR_SIZE), ("outline", OUTLINE_SIZE)):
        name = (manifest.get("icons") or {}).get(key)
        if name not in files:
            found.append(Finding("TCC-M006", f"icons.{key}", "the icon file is not in the package"))
            continue
        try:
            dimensions = png_size(files[name])
        except ValueError:
            dimensions = None
        if dimensions != (size, size):
            found.append(Finding("TCC-M006", name, f"must be a {size}x{size} PNG"))
    return found


def _authorization(path: str, auth: Any) -> list[Finding]:
    if not isinstance(auth, dict) or auth.get("type") not in AUTH_TYPES:
        return [Finding("TCC-C005", path, f"authorization.type must be one of {AUTH_TYPES}")]
    reference, kind = auth.get("referenceId"), auth["type"]
    if kind == "None" and reference is not None:
        return [Finding("TCC-C005", path, "referenceId must not be present when the type is None")]
    if kind != "None" and (not isinstance(reference, str) or not 1 <= len(reference) <= 128):
        return [Finding("TCC-C005", path, "referenceId (1-128 characters) is required unless the type is None")]
    return []


def _connector(index: int, connector: dict[str, Any], version: str, files: dict[str, bytes]) -> list[Finding]:
    path, found = f"agentConnectors[{index}]", []
    if not connector.get("id") or len(connector["id"]) > 64 or not connector.get("displayName"):
        found.append(Finding("TCC-C001", path, "needs an id (64 characters at most) and a displayName"))
    source = (connector.get("toolSource") or {})
    if list(source) != ["remoteMcpServer"]:
        return [*found, Finding("TCC-C002", path, "toolSource must hold exactly remoteMcpServer")]
    server = source["remoteMcpServer"]
    if not _https(server.get("mcpServerUrl")):
        found.append(Finding("TCC-C003", path, "mcpServerUrl must be a valid HTTPS URL"))
    tool_file = (server.get("mcpToolDescription") or {}).get("file")
    if version == "1.28" and not tool_file:
        found.append(Finding("TCC-C004", path, "manifest 1.28 requires mcpToolDescription"))
    if tool_file and tool_file.removeprefix("./") not in files:
        found.append(Finding("TCC-C004", path, "mcpToolDescription names a file that is not in the package"))
    return [*found, *_authorization(path, server.get("authorization"))]


def _connectors(manifest: dict[str, Any], files: dict[str, bytes]) -> list[Finding]:
    connectors = manifest.get("agentConnectors") or []
    found = [Finding("TCC-C001", "agentConnectors", "at most 10 connectors")] if len(connectors) > 10 else []
    ids = [c.get("id") for c in connectors]
    if len(set(ids)) != len(ids):
        found.append(Finding("TCC-C001", "agentConnectors", "connector ids must be unique"))
    for index, connector in enumerate(connectors):
        found += _connector(index, connector, str(manifest.get("manifestVersion")), files)
    return found


def validate_manifest(manifest: dict[str, Any], files: dict[str, bytes]) -> list[Finding]:
    """Every problem with the manifest and the files it points at."""
    skills = manifest.get("agentSkills") or []
    found = [*_identity(manifest), *_listing(manifest), *_icons(manifest, files), *_connectors(manifest, files)]
    if len(skills) > 20:
        found.append(Finding("ASKILL-M002", "agentSkills", "at most 20 skills"))
    for index, entry in enumerate(skills):
        folder = entry.get("folder") if isinstance(entry, dict) else None
        if not folder:
            found.append(Finding("ASKILL-M001", f"agentSkills[{index}]", "folder is required"))
        elif len(folder) > 256:
            found.append(Finding("ASKILL-M003", f"agentSkills[{index}]", "folder path is over 256 characters"))
    return found
