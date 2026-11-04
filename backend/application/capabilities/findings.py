"""`findings_list` — what agents found, and what a human has decided about it.

A finding is a judgement that changes a number on a filed return. The list is
at the grain a human decides at (one policy question, not 36,016 rows), and an
unresolved finding is counted apart from one that was decided "accept".
"""
from __future__ import annotations

from application.capabilities import _support as s
from application.capabilities.errors import ClientNotFound
from application.capabilities.envelope import Provenance, ToolResult


def findings_list(client_id: int, tax_year: int, state: str | None = None) -> ToolResult:
    """Findings for one client-year, open ones first.

    Sensitive: instance-grain findings carry an employee id in their evidence.
    The blocks name no employee; `facts` keeps them because a decision is made
    against a finding id.
    """
    from application.queries.list_findings import FindingsNotAvailable, ListFindingsQuery
    from application.services import get_mediator

    try:
        facts = get_mediator().send(
            ListFindingsQuery(client_id=client_id, tax_year=tax_year, state=state)
        )
    except FindingsNotAvailable as exc:
        raise ClientNotFound(str(exc)) from exc

    summary = facts["summary"]
    if summary["none_found"]:
        blocks = [s.paragraph("No findings were raised for this client-year.")]
    else:
        rows = []
        for finding in facts["findings"]:
            population = finding.get("population") or {}
            rows.append((
                str(finding["title"]),
                "Policy" if finding["grain"] == "policy" else "Instance",
                s.cell(population.get("instances"), "count") if population else s.ABSENT,
                "Open" if finding["requires_decision"] else "Decided",
            ))
        blocks = [
            s.paragraph(
                f"{s.cell(summary['requires_decision'], 'count')} of "
                f"{s.cell(summary['total'], 'count')} decisions are open, covering "
                f"{s.cell(summary['instances'], 'count')} underlying records."
            ),
            s.table(("Finding", "Grain", "Records", "Status"), rows),
        ]
    return s.result(
        "findings_list", facts, blocks,
        provenance=Provenance(source="payroll exception detection, run live"),
        warnings=["Sensitive: instance findings identify individual employees."],
    )
