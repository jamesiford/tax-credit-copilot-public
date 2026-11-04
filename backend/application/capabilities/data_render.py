"""A query result as an envelope: facts, the lane each block travels in, and provenance. [CH-16d]

Nothing here computes or interprets. Every value in `facts` is the row as the source returned it,
every cell in a table is that value printed by the platform's one formatter, and the numeric
guard checks the finished reply against these same facts, so a figure is shown only if the data
produced it.

**The lanes.** A result whose rows describe individual employees marks its table `user` and lists
`rows` in `user_only_facts`; `lanes.py` is what keeps both from a model. The rest of the result
(the heading, the row count, the source line, the notes) is safe for both: they describe the
query, not a person.

**Display.** Facts keep every row the cap allowed. The table shows the first `DISPLAY_ROWS`,
because a channel message that carries five hundred rows is not delivered, and says so when it
cuts: the reader is never left to infer that a list is the whole list.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import AUDIENCE_USER, Block, Provenance, ToolResult
from application.data.classify import USER
from application.data.plan import ResultColumn
from application.data.service import QueryResult

DISPLAY_ROWS = 50
_YEAR_LABELS = ("tax_year", "year", "base_tax_year")
_NUMBER_TYPES = (int, float, Decimal)


def _formatter(column: ResultColumn) -> str:
    """How a number in this column prints: dollars as dollars, years as years, headcount with its decimals."""
    if column.unit == "USD":
        return "money"
    if column.logical in _YEAR_LABELS or column.logical.endswith("_tax_year"):
        return "year"
    return "headcount" if column.unit == "headcount" else "number"


def cell(value: Any, column: ResultColumn) -> str:
    """One table cell. Text is verbatim (a code like 00123 is not a number), `None` is the dash."""
    if value is None:
        return s.ABSENT
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (date, datetime)):
        return s.cell(value, "date")
    if isinstance(value, _NUMBER_TYPES):
        return s.cell(value, _formatter(column))
    return str(value)


def _header(column: ResultColumn) -> str:
    return f"{column.label} ({column.unit})" if column.unit else column.label


def _facts(result: QueryResult) -> dict[str, Any]:
    p = result.provenance
    names = [c.label for c in result.columns]
    return {
        "dataset": p.dataset, "audience": result.audience, "client_id": p.client_id,
        "tax_years": list(p.tax_years), "method": p.method,
        "row_count": p.row_count, "displayed_rows": min(p.row_count, DISPLAY_ROWS),
        "row_limit": p.row_limit, "truncated": p.truncated,
        "as_of": p.as_of, "source": p.source_line,
        "columns": [{"name": c.label, "kind": c.kind, "unit": c.unit,
                     "person_level": c.label in result.employee_level_labels} for c in result.columns],
        "rows": [dict(zip(names, row)) for row in result.rows],
        "select": list(p.select), "group_by": list(p.group_by),
        "measures": [dict(m) for m in p.measures], "filters": [dict(f) for f in p.filters],
        "notes": list(p.notes),
        **({"small_groups": dict(p.small_groups)} if p.small_groups else {}),
    }


def _table(result: QueryResult) -> Block:
    shown = result.rows[:DISPLAY_ROWS]
    body = [[cell(v, c) for v, c in zip(row, result.columns)] for row in shown]
    return Block("table", rows=(tuple(_header(c) for c in result.columns), *(tuple(r) for r in body)),
                 audience=AUDIENCE_USER if result.audience == USER else "both")


def _blocks(result: QueryResult) -> list[Block]:
    p = result.provenance
    out = [s.heading(f"Query result · {p.dataset}")]
    if not result.rows:
        out.append(s.paragraph("No rows matched. That is a result about the data, not an error."))
    else:
        out.append(_table(result))
    if len(result.rows) > DISPLAY_ROWS:
        out.append(s.callout(
            f"Showing the first {s.cell(DISPLAY_ROWS, 'count')} of {s.cell(p.row_count, 'count')} rows here. "
            "Narrow the question, or ask for an aggregate, to see the rest."))
    if result.audience == USER:
        out.append(s.callout("These rows describe individual employees. They are shown to you and are not given to any AI model."))
    out.extend(s.callout(note) for note in p.notes)
    out.append(s.paragraph(f"{p.source_line}. As of {s.cell(p.as_of, 'date')}."))
    return out


def _provenance(result: QueryResult) -> Provenance:
    run = result.provenance.run
    sets = [x for x in (run.step1_assumption_set_id, run.onezero_assumption_set_id) if x] if run else []
    return Provenance(
        run_id=run.run_id if run else None, rule_pack_version=run.rule_pack_version if run else None,
        assumption_set_id=" + ".join(sets) or None, source=result.provenance.source_line,
    )


def to_tool_result(result: QueryResult) -> ToolResult:
    """The envelope for a query result. The person-level lane is declared, not implied."""
    user = result.audience == USER
    return ToolResult(
        tool="data_query", facts=_facts(result), blocks=tuple(_blocks(result)), provenance=_provenance(result),
        warnings=(*result.provenance.notes, *(("Sensitive: this result lists individual employees.",) if user else ())),
        user_only_facts=("rows",) if user else (),
    )
