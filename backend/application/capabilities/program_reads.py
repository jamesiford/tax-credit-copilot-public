"""`program_catalog`: the programs the platform knows, for the channel. [F05.11, ADR-013]

The same read the portal's Program manager makes (`ListProgramCatalogQuery`, `GetProgramDetailQuery`), shaped for a chat: a table
to show and compact facts to narrate from. Every figure is the platform's (a count the registry or the claims store holds, a
year a pack names); nothing is computed here, and every row says it is not verified. A catalog the claims store cannot count is
shown without engagement counts and says so, never as zero clients. Drafts are never read here.
"""
from __future__ import annotations

from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.errors import NotCalculated

_SOURCE = "program registry and rule packs"
_NOTE = "Not verified. A rule pack that validates is well-formed, not legally correct: a person must verify each value against the primary source."


def _years(years: list[int]) -> str:
    return ", ".join(s.cell(y, "year") for y in years) if years else "none authored"


def _engagement(row: dict[str, Any]) -> str:
    e = row.get("engagement")
    if e is None:
        return s.ABSENT
    return f"{s.cell(e['clients'], 'count')} ({s.cell(e['in_scope'], 'count')} in scope)"


def _list(rows: list[dict[str, Any]], available: bool) -> ToolResult:
    calculable = [r for r in rows if r["calculable"]]
    table = s.table(
        ("Program", "State", "Lifecycle", "Authored years", "Calculable", "Clients"),
        [(f"{r['name']} ({r['code']})", r["state"] or r["jurisdiction"]["level"], r["lifecycle"], _years(r["authored_years"]),
          "Yes" if r["calculable"] else f"No: {r['not_calculable_reason']}", _engagement(r)) for r in rows],
    )
    blocks = [
        s.heading("Programs the platform knows"),
        s.paragraph(f"{s.cell(len(rows), 'count')} programs are registered; {s.cell(len(calculable), 'count')} can be calculated for their authored years."),
        table, s.callout(_NOTE),
    ]
    facts = {"programs": rows, "total": len(rows), "calculable": len(calculable), "engagement_available": available, "verification_note": _NOTE}
    warnings = [] if available else ["Engagement counts are unavailable right now; they are not zero."]
    return s.result("program_catalog", facts, blocks, provenance=Provenance(source=_SOURCE), warnings=warnings)


def _detail(p: dict[str, Any]) -> ToolResult:
    errors = [i for i in p["validation"]["pack"] if i["severity"] == "error"][:5]
    years = [{"tax_year": y["tax_year"], "unverified": y["unverified"], "source": y["source"]} for y in p["years"]]
    blocks = [
        s.heading(f"{p['name']} ({p['code']})"),
        s.paragraph(f"Lifecycle: {p['lifecycle']}. Authored years: {_years(p['authored_years'])}. Pack file {p['pack']['file']}."),
    ]
    if p["blockers"]:
        blocks.append(s.bullets(p["blockers"]))
    if years:
        blocks.append(s.table(("Tax year", "Still flagged unverified", "Source"),
                              [(s.cell(y["tax_year"], "year"), "Yes" if y["unverified"] else "No", y["source"] or s.ABSENT) for y in years]))
    blocks.append(s.callout(_NOTE))
    facts = {"code": p["code"], "name": p["name"], "state": p["state"], "lifecycle": p["lifecycle"], "calculable": p["calculable"],
             "not_calculable_reason": p["not_calculable_reason"], "authored_years": p["authored_years"], "unverified_years": p["unverified_years"],
             "years": years, "pack": {"file": p["pack"]["file"], "citation": p["pack"]["citation"], "engine_profile": p["pack"]["engine_profile"]},
             "engagement": p["engagement"], "blockers": p["blockers"],
             "validation": {"valid": p["validation"]["valid"], "error_count": p["validation"]["error_count"], "first_errors": errors},
             "verification_note": _NOTE}
    return s.result("program_catalog", facts, blocks, provenance=Provenance(source=_SOURCE))


def program_catalog(program_code: str | None = None) -> ToolResult:
    """The list when no code is given, else one program's detail."""
    from application.program_catalog import UnknownProgram
    from application.queries.program_catalog_reads import GetProgramDetailQuery, ListProgramCatalogQuery
    from application.services import get_mediator

    mediator = get_mediator()
    if program_code:
        try:
            return _detail(mediator.send(GetProgramDetailQuery(code=program_code.strip())))
        except UnknownProgram as exc:
            raise NotCalculated(f"No program {program_code!r} is in the registry.") from exc
    page = mediator.send(ListProgramCatalogQuery())
    if not page["programs"]:
        raise NotCalculated("The program registry lists no programs.")
    return _list(page["programs"], page["engagement_available"])
