"""Deployment values for the plugin: where they come from and what makes one a placeholder. [CH-10]

Values come from a JSON file (`--config`), and an environment variable of the same
name (`TCC_COWORK_<KEY>`) overrides the file, so a pipeline can inject one value
without editing a file that lives in a gitignored overlay.

The app id is a UUID v5 of a seed, not a random UUID: a Cowork package id must stay
the same across versions or an update installs as a second plugin, and "rebuild it
from the same inputs" must be enough to get it back.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENV_PREFIX = "TCC_COWORK_"
DEFAULT_SEED = "tcc-channel.cowork-plugin"
SEED_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # RFC 4122 URL namespace
SUPPORTED_MANIFEST_VERSIONS = ("1.28", "1.29")
ZERO_GUID = "00000000-0000-0000-0000-000000000000"

REQUIRED = (
    "developer_name", "developer_website_url", "developer_privacy_url", "developer_terms_url",
    "gateway_mcp_url", "oauth_reference_id",
)
DEFAULTS = {
    "version": "1.0.0", "manifest_version": "1.29", "accent_color": "#0F6CBD", "app_id_seed": DEFAULT_SEED, "app_id": "",
}
_PLACEHOLDER = re.compile(r"<[^>]+>|\bexample\.(com|org|net|invalid)\b|^0{8}-0{4}-0{4}-0{4}-0{12}$", re.IGNORECASE)


class ConfigError(ValueError):
    """The configuration is missing a value or names a manifest version this builder does not know."""


@dataclass(frozen=True)
class PluginSettings:
    """Everything the manifest template needs, already resolved."""

    values: dict[str, str]

    @property
    def app_id(self) -> str:
        """The explicit id when one is configured, else the deterministic UUID v5 of the seed."""
        return self.values["app_id"] or app_id_for(self.values["app_id_seed"])

    @property
    def manifest_version(self) -> str:
        """`1.29` (URL-only connectors) or `1.28` (which needs a tool-description file)."""
        return self.values["manifest_version"]

    def placeholders(self) -> list[str]:
        """The required values that still look like placeholders: a build with any is not publishable."""
        return [key for key in REQUIRED if _PLACEHOLDER.search(self.values[key])]

    def template_values(self) -> dict[str, str]:
        """The substitutions for `{{name}}` markers in the manifest template."""
        return {**self.values, "app_id": self.app_id}


def app_id_for(seed: str) -> str:
    """The deterministic app id for `seed`: the same seed always yields the same id."""
    return str(uuid.uuid5(SEED_NAMESPACE, seed))


def _read_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read the configuration file {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path} must hold a JSON object")
    return loaded


def load_settings(config: Path | None = None, environ: dict[str, str] | None = None) -> PluginSettings:
    """File first, then environment, then defaults; every required value must end up non-empty."""
    environ = dict(os.environ) if environ is None else environ
    merged: dict[str, str] = dict(DEFAULTS)
    for key, value in _read_file(config).items():
        if not key.startswith("_"):
            merged[key] = str(value)
    for key in (*REQUIRED, *DEFAULTS):
        override = environ.get(ENV_PREFIX + key.upper())
        if override:
            merged[key] = override
    missing = [key for key in REQUIRED if not merged.get(key, "").strip()]
    if missing:
        raise ConfigError("missing configuration: " + ", ".join(missing))
    if merged["manifest_version"] not in SUPPORTED_MANIFEST_VERSIONS:
        raise ConfigError(f"manifest_version must be one of {SUPPORTED_MANIFEST_VERSIONS}")
    return PluginSettings(merged)
