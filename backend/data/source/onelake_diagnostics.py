"""Diagnose OneLake access one step at a time, with what each failure usually means. [03.1]

Used by `scripts/check-onelake-access.py`. Every step is a small function so it can be tested
with fakes; none of them prints or logs a token. A step reports `ok`, a one-line `detail`, and,
on failure, the likely cause, because the same few errors account for almost every first-run
problem against a private-link workspace.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from config import get_settings

from . import onelake

#: Substring of an error -> what it usually means. First match wins; ordered most specific first.
_MEANINGS: tuple[tuple[str, str], ...] = (
    ("IncorrectEndpointError", "wrong host kind: the Delta reader lists files over the BLOB API, so ONELAKE_ENDPOINT must be "
                               "the *.blob.fabric.microsoft.com host, not the dfs host."),
    ("DeniedByPolicy", "the request went to the public path, or the private link is not in use. Set ONELAKE_ENDPOINT to the "
                       "workspace private blob host and run this from a network that resolves it."),
    ("AuthorizationFailure", "authenticated but not authorised: the identity needs a Contributor, Member or Admin role on the "
                             "workspace (Viewer sees only the SQL analytics endpoint)."),
    ("not authorized", "authenticated but not authorised: the identity needs a Contributor, Member or Admin role on the "
                       "workspace (Viewer sees only the SQL analytics endpoint)."),
    ("403", "authenticated but not authorised: check the workspace role (Contributor, Member or Admin) granted to this identity."),
    ("401", "the token was rejected: wrong tenant or an expired login. Run `az login` against the right tenant."),
    ("ArtifactNotFound", "the lakehouse or table was not found. A paused capacity answers the same way; check the workspace "
                         "name or id, ONELAKE_PATH_STYLE, SOURCE_SCHEMA and the table-name settings."),
    ("TableNotFound", "no Delta table at that path: check SOURCE_SCHEMA (empty for a lakehouse that is not schema-enabled), "
                      "SOURCE_TABLE_PREFIX, SOURCE_TABLE_CASE and SOURCE_TABLE_MAP."),
    ("not a Delta table", "no Delta table at that path: check SOURCE_SCHEMA and the table-name settings."),
    ("timed out", "the connection did not complete: a slow capacity, or the private host is not reachable from this network "
                  "(VPN, jumpbox or private DNS)."),
    ("dns error", "the host name did not resolve: private DNS is not in effect on this machine."),
)


@dataclass(frozen=True)
class Step:
    name: str
    ok: bool
    detail: str
    hint: str = ""


def explain(error: str) -> str:
    """What an error from the storage path usually means; empty when it is not one we know."""
    lowered = error.lower()
    for needle, meaning in _MEANINGS:
        if needle.lower() in lowered:
            return meaning
    return ""


def target_host() -> str:
    endpoint = get_settings().data_source.onelake_endpoint
    return urlparse(endpoint).hostname if endpoint else onelake.ONELAKE_PUBLIC_HOST


def classify_addresses(addresses: list[str]) -> tuple[bool, str]:
    """(all private, description). A private-link host resolves to private addresses only."""
    private = [a for a in addresses if ipaddress.ip_address(a).is_private]
    public = [a for a in addresses if a not in private]
    if public:
        return False, f"resolves to a PUBLIC address ({', '.join(public)}): the private link's DNS is not in effect"
    return True, f"resolves to private address(es): {', '.join(private)}"


def check_dns(host: str, *, resolver: Callable[..., list] = socket.getaddrinfo) -> Step:
    try:
        addresses = sorted({info[4][0] for info in resolver(host, 443)})
    except OSError as exc:
        return Step("dns", False, f"{host} did not resolve ({exc})", explain("dns error"))
    private, description = classify_addresses(addresses)
    configured_private = bool(get_settings().data_source.onelake_endpoint)
    hint = "" if private or not configured_private else "Run this from the VPN or jumpbox that resolves the private name."
    return Step("dns", private or not configured_private, f"{host} {description}", hint)


def check_token(get_token: Callable[[], str] = onelake.storage_token) -> Step:
    try:
        get_token()
    except Exception as exc:  # noqa: BLE001 - report any credential failure rather than raise it
        return Step("token", False, f"{type(exc).__name__}: {str(exc)[:200]}", "Run `az login` against the right tenant.")
    return Step("token", True, "storage token acquired (not shown)")


def check_table(open_table: Callable[[], dict], table: str) -> Step:
    try:
        lineage = open_table()
    except Exception as exc:  # noqa: BLE001 - the point is to translate whatever came back
        text = f"{type(exc).__name__}: {exc}"
        return Step("delta", False, text[:300], explain(text))
    return Step("delta", True, f"{table}: Delta version {lineage.get('version')}, {lineage.get('files')} file(s)")
