"""Parsers for single settings that need more than `environ.get`: a closed set, a flag, a JSON map, a URL. [03]

Each takes the mapping it is given and reads no process. A value that cannot be understood raises
`ValueError` naming the setting, because a guess here (a case rule, a path style, an endpoint) decides
which table or host a read goes to.
"""
from __future__ import annotations

import json
from collections.abc import Mapping


def choice(environ: Mapping[str, str], name: str, allowed: tuple[str, ...], default: str) -> str:
    """The lower-cased value of `name`, which must be one of `allowed`."""
    value = (environ.get(name) or default).strip().lower()
    if value not in allowed:
        raise ValueError(f"{name}={value!r} is not one of {', '.join(allowed)}")
    return value


def table_map(environ: Mapping[str, str]) -> dict[str, str]:
    """`SOURCE_TABLE_MAP`: a JSON object of strings, logical table name to physical name."""
    raw = (environ.get("SOURCE_TABLE_MAP") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"SOURCE_TABLE_MAP is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
        raise ValueError('SOURCE_TABLE_MAP must be a JSON object of strings, e.g. {"Payroll": "payroll_v2"}')
    return dict(parsed)


def onelake_endpoint(environ: Mapping[str, str]) -> str | None:
    """`ONELAKE_ENDPOINT`: a full URL without a trailing slash, or None."""
    value = (environ.get("ONELAKE_ENDPOINT") or "").strip().rstrip("/")
    if value and not value.startswith(("https://", "http://")):
        raise ValueError(
            "ONELAKE_ENDPOINT must be a full URL, e.g. https://<workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com"
        )
    return value or None


def optional_flag(environ: Mapping[str, str], name: str) -> bool | None:
    """A boolean that was either stated or not. A value that is neither true nor false is refused, not guessed."""
    raw = (environ.get(name) or "").strip().lower()
    if not raw:
        return None
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name}={raw!r} is not a boolean; use true or false")


def optional_int(value: str | None) -> int | None:
    """An integer setting with no default: unset or blank is None, never a made-up value."""
    return int(value) if value and value.strip() else None


def tuned_int(environ: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    """A tuning knob: never below `minimum`, and an unparseable value is the default (tuning, not policy)."""
    try:
        return max(minimum, int(environ.get(name, str(default))))
    except ValueError:
        return default
