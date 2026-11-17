"""Small value-free checks; errors contain approved setting names only."""

import json
import ipaddress
import math
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

BOOL = {"true": True, "1": True, "yes": True, "on": True,
        "false": False, "0": False, "no": False, "off": False}


def guid(text):
    try:
        return str(UUID(text)).lower() == text.lower()
    except (ValueError, AttributeError):
        return False


def audience(text):
    return guid(text) or text.startswith("api://") and guid(text[6:])


def https(text, origin=False):
    try:
        url = urlsplit(text)
        host = url.hostname or ""
        try:
            ipaddress.ip_address(host)
            valid_host = True
        except ValueError:
            valid_host = len(host) <= 253 and all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in host.split("."))
        return bool(url.scheme == "https" and valid_host and url.port != 0
                    and not url.username and not url.password and not url.query
                    and not url.fragment and (not origin or url.path in ("", "/"))
                    and not any(c.isspace() or ord(c) < 32 for c in text))
    except ValueError:
        return False


def number(settings, name, errors, low=0, high=3600, integer=False):
    text = settings.get(name, "").strip()
    if not text:
        return
    try:
        value = int(text) if integer else float(text)
        if not math.isfinite(value) or not low <= value <= high:
            errors.add(name)
    except (ValueError, OverflowError):
        errors.add(name)


def flag(settings, name, errors, runtime=False):
    text = settings.get(name, "").strip().lower()
    allowed = BOOL if not runtime else {k: v for k, v in BOOL.items() if k not in ("on", "off")}
    if text and text not in allowed:
        errors.add(name)
    return allowed.get(text, False)


def allowlist(text):
    try:
        value = json.loads(text)
        return isinstance(value, dict) and bool(value) and all(
            guid(key) and isinstance(ids, list) and bool(ids)
            and all(type(item) is int and 0 < item <= 9223372036854775807 for item in ids)
            for key, ids in value.items())
    except (TypeError, ValueError):
        return False


def headers(text):
    try:
        value = json.loads(text)
        return isinstance(value, dict) and all(
            re.fullmatch(r"[A-Za-z0-9-]+", key) and isinstance(item, str)
            and "\r" not in item and "\n" not in item for key, item in value.items())
    except (TypeError, ValueError):
        return False


def resources(settings, errors):
    root = Path(settings.get("TCC_REPOSITORY_ROOT", ""))
    rules = Path(settings.get("RULES_DIR", root / "backend" / "rules"))
    expected = [
        root / "docs" / "data" / "schema" / "tcc-schema.sqlserver.sql",
        root / "backend" / "data" / "payroll.csv",
        rules.parent / "data" / "payroll_pay_periods.csv",
        rules / "registry" / "programs.json",
    ]
    try:
        if not all(path.is_file() for path in expected):
            errors.add("TCC_REPOSITORY_ROOT")
        if not list((root / "docs" / "data" / "schema" / "migrations").glob("*.sql")):
            errors.add("TCC_REPOSITORY_ROOT")
        if not (rules / "lookups").is_dir() or not (rules / "methodology").is_dir():
            errors.add("RULES_DIR")
    except OSError:
        errors.add("TCC_REPOSITORY_ROOT")
