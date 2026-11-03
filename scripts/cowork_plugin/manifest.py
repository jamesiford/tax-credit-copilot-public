"""Renders `manifest.json` from the template, and the 1.28 tool-description file. [CH-10]

The template holds `{{name}}` markers, never real values. Substitution happens on the
parsed JSON, not on text, so a value containing a quote cannot break the document.

Manifest 1.29 connectors are URL-only. At 1.28 a connector must name a
`mcpToolDescription` file that is inside the package; that file is generated here
from the live catalog, through the same `describe` the gateway's `tools/list` uses,
so it cannot disagree with what the server offers. Cowork discovers tools from the
server and ignores the file, which is why it is only built when 1.28 is asked for.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from cowork_plugin.settings import PluginSettings

BACKEND = Path(__file__).resolve().parents[2] / "backend"
TOOL_FILE = "tools/tcc-channel-tools.json"
_MARKER = re.compile(r"\{\{([a-z_]+)\}\}")


class TemplateError(ValueError):
    """The template names a value the settings do not hold."""


def _substitute(node: Any, values: dict[str, str]) -> Any:
    if isinstance(node, str):
        def fill(match: re.Match[str]) -> str:
            if match.group(1) not in values:
                raise TemplateError(f"the template uses {{{{{match.group(1)}}}}} but no such value exists")
            return values[match.group(1)]

        return _MARKER.sub(fill, node)
    if isinstance(node, list):
        return [_substitute(item, values) for item in node]
    if isinstance(node, dict):
        return {key: _substitute(value, values) for key, value in node.items()}
    return node


def tool_description() -> dict[str, Any]:
    """Every tool the gateway offers, as `tools/list` shows it, generated from the catalog."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from application.capabilities import catalog
    from channel.mcp import describe

    return {"tools": [describe(spec) for spec in catalog.offered()]}


def render_manifest(template: Path, settings: PluginSettings) -> dict[str, Any]:
    """The manifest for `settings`, with the 1.28 tool-description reference added when that version is asked for."""
    manifest = _substitute(json.loads(template.read_text(encoding="utf-8")), settings.template_values())
    if settings.manifest_version == "1.28":
        for connector in manifest.get("agentConnectors", []):
            connector["toolSource"]["remoteMcpServer"]["mcpToolDescription"] = {"file": "./" + TOOL_FILE}
    return manifest


def dumps(document: dict[str, Any]) -> bytes:
    """The bytes written to the package: stable key order, two-space indent, one trailing newline."""
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
