"""Closed observations: an endpoint name never grants permission to its side-effect chain."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit


class Refused(RuntimeError):
    """Only fixed reason codes cross the diagnostic boundary."""


@dataclass(frozen=True)
class Case:
    group: str
    route: str
    effect: str
    private: bool = True
    rows: int = 25
    pages: int = 1
    bytes: int = 1_048_576
    seconds: int = 15
    concurrency: int = 1


CASES = {
    "health": Case("framework", "GET /api/health", "settled-status", False),
    "eligibility": Case("reads_calc", "GET /api/eligibility/{tax_year}", "gold-read"),
    "drafts": Case("drafts_runs", "GET /api/v2/program-drafts", "operational-read"),
    "rules": Case("claims_artifacts_rules", "GET /api/rules", "unbounded-claim-scan", rows=100),
    "gateway": Case("gateway", "POST /channel/v1/tools/client_eligibility", "mandatory-audit"),
    "ai": Case("ai", "POST /api/chat", "narration-or-remote"),
    "sealed": Case("workspace_sealed", "GET /api/workspace", "sealed-unavailable"),
    "artifact": Case("claims_artifacts_rules",
                     "GET /api/clients/{client_id}/artifacts/{artifact_id}", "artifact-access-audit"),
    "export": Case("drafts_runs", "GET /api/v2/program-drafts/{draft_id}/export/manifest", "synthetic-only"),
    "situation": Case("claims_artifacts_rules", "GET /api/v2/clients/{client_id}/situation", "synthetic-only"),
    "canonical": Case("ai", "POST /api/capabilities/{tool}", "synthetic-only"),
}
LIVE_EFFECTS = frozenset(("settled-status", "gold-read", "operational-read"))
METHODS = frozenset(("min_max", "pay_period"))
PROGRAMS = frozenset(("GA_JTC",))


def admitted_case(name: str) -> Case:
    case = CASES.get(name)
    if case is None or case.effect not in LIVE_EFFECTS:
        raise Refused("side-effect-or-unknown")
    return case


def request_path(name: str, account: int, year: int, program: str, method: str) -> str:
    case = admitted_case(name)
    if (type(account) is not int or not 1 <= account <= 2**63 - 1
            or type(year) is not int or not 1900 <= year <= 2100
            or program not in PROGRAMS or method not in METHODS):
        raise Refused("selection")
    path = case.route.split(" ", 1)[1].replace("{tax_year}", str(year))
    if name == "eligibility":
        return path + "?" + urlencode({"account_id": account, "state": "GA", "program_code": program,
                                       "limit": 25, "offset": 0, "sort": "employee_id", "order": "asc"})
    return path + ("?limit=25&offset=0" if name == "drafts" else "")


def origin(value: str, *, local: bool = False) -> str:
    try:
        parts = urlsplit(value)
        valid = (parts.path in ("", "/") and not parts.query and not parts.fragment
                 and not parts.username and not parts.password
                 and parts.hostname and parts.scheme == ("http" if local else "https"))
        if local:
            valid = valid and parts.hostname == "127.0.0.1" and parts.port is not None
        if not valid:
            raise Refused("origin")
    except ValueError:
        raise Refused("origin") from None
    return value.rstrip("/")


def check_rows(tree: object, limit: int, depth: int = 0) -> None:
    if depth > 30:
        raise Refused("shape-bound")
    if isinstance(tree, list):
        if len(tree) > limit:
            raise Refused("row-bound")
        for value in tree:
            check_rows(value, limit, depth + 1)
    elif isinstance(tree, dict):
        if len(tree) > 250:
            raise Refused("shape-bound")
        for value in tree.values():
            check_rows(value, limit, depth + 1)
