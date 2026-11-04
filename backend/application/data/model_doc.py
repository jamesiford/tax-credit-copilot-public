"""Render the semantic model as Markdown, so the documentation cannot drift from the data. [CH-16a]

`docs/data/SEMANTIC-MODEL.md` is generated from the model by
`scripts/generate-semantic-model-doc.py`, and a test fails if the committed file differs
from this output. A hand-maintained description of what an agent may query is the kind of
document that is right on the day it is written; generating it makes that permanent.
"""
from __future__ import annotations

from application.data.model_excluded import EXCLUDED_SOURCE_TABLES, EXCLUDED_WAREHOUSE_TABLES
from application.data.semantic_model import Column, Dataset, SemanticModel

_HEADER = """\
# Semantic model

> Generated from `backend/application/data/` by `scripts/generate-semantic-model-doc.py`. Do not
> edit by hand: a test fails when this file and the model disagree.

The agent reached from Teams, Microsoft 365 Copilot and Cowork may ask questions of the
payroll and the enriched data, but it never writes SQL. It fills in a structured query; the
platform checks it against the model below, builds the statement from the model's own
physical names, binds every value and scopes it to one client before anything runs. This
page lists what exists, what one row means, and which tool is authoritative when more than
one can answer.

## How to read it

- **Grain** is what one row is. Counting rows counts that, which is not always people.
- **Sensitivity** describes the *raw* value. `employee_level` is one person's pay or hours:
  rows that carry it go to the person asking and are not shown to a model, while an aggregate
  over a group (a count by location, an average by month) can be narrated. `blocked` columns
  exist in the tables and can never be selected, filtered or grouped. People appear only as a
  record token.
- **Currency**: Gold keeps superseded runs. `live run` pins the client's current run and
  `is_current` takes the current row, so a restated figure is never mixed with the filed one.
- **Method**: where a dataset holds both statutory readings (`min_max` and `pay_period`), the
  method is always returned beside the answer and never chosen silently.
- **The fixed tools stay authoritative.** For the credit figure, eligibility or what the engine
  concluded, quote `client_eligibility`, `client_trend`, `client_at_risk` or `simulate`. A data
  query returns exact rows and aggregates; it does not interpret them, and where it can
  reproduce an engine figure it equals it (an equivalence test enforces that).
- **Small groups**: an aggregate over one or two people is close to a person's own figure.
  The privacy design is the delivery lane, not this model.
"""

_FOOTER = """\
## Changing the model

1. Add the column or table to the DDL (or the source schema) as usual.
2. `tests/test_semantic_model_drift.py` now fails. Model the column in the right
   `application/data/model_*.py` (mark anything that could identify a person `blocked`), or
   list it under `excluded_columns` / `model_excluded.py` with a reason.
3. Regenerate this page: `python scripts/generate-semantic-model-doc.py`.
"""


def _allowed(column: Column) -> str:
    aggs = ", ".join(sorted(a.value for a in column.aggregations)) or "none"
    ops = ", ".join(sorted(o.value for o in column.operators)) or "none"
    return f"agg: {aggs}; filter: {ops}"


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def _column_row(column: Column) -> str:
    unit = column.unit or ""
    return (
        f"| `{column.logical}` | {column.type.value} | {column.role.value} | {column.sensitivity.value} "
        f"| {unit} | {_cell(column.description)} | {_allowed(column)} |"
    )


def _index_row(dataset: Dataset) -> str:
    level = "yes" if dataset.employee_level else "no"
    return (
        f"| `{dataset.name}` | {dataset.source.value} | `{dataset.schema.value}.{dataset.table}` "
        f"| {level} | {dataset.currency.value} | {_cell(dataset.grain)} |"
    )


def _facts(dataset: Dataset) -> list[str]:
    lines = [f"- Client key: `{dataset.tenant_column}` (applied for you, always the first predicate)."]
    if dataset.year_column:
        lines.append(f"- Tax year: `{dataset.year_column}`.")
    if dataset.method_column:
        lines.append(f"- Method: `{dataset.method_column}` (`min_max` | `pay_period`; returned with every row).")
    if dataset.month_columns:
        lines.append(f"- Months: `{dataset.month_columns[0]}` to `{dataset.month_columns[-1]}` (fiscal months).")
    if dataset.period_columns:
        lines.append("- Dates: " + ", ".join(f"`{c}`" for c in dataset.period_columns) + ".")
    for join in dataset.joins:
        pairs = ", ".join(f"`{a}` = `{join.name}.{b}`" for a, b in join.on)
        lines.append(f"- Join `{join.name}` -> `{join.target}` on {pairs} (many-to-one, left join).")
    return lines


def _dataset_section(dataset: Dataset) -> str:
    queryable = [c for c in dataset.columns if c.queryable]
    blocked = [c.logical for c in dataset.columns if not c.queryable]
    out = [f"### `{dataset.name}`", "", _cell(dataset.description), "", f"**Grain:** {_cell(dataset.grain)}", ""]
    out += _facts(dataset) + [""]
    out += ["| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |", "| --- | --- | --- | --- | --- | --- | --- |"]
    out += [_column_row(c) for c in queryable]
    if blocked:
        out += ["", "Never queryable: " + ", ".join(f"`{b}`" for b in blocked) + "."]
    if dataset.engine_notes:
        out += ["", "**Relation to the engine's tools**", ""]
        out += [f"- `{topic}`: {_cell(note)}" for topic, note in dataset.engine_notes]
    return "\n".join(out) + "\n"


def _excluded(title: str, table: dict[str, str]) -> str:
    rows = [f"| `{name}` | {_cell(reason)} |" for name, reason in sorted(table.items())]
    return "\n".join([f"### {title}", "", "| Table | Why it is not queryable |", "| --- | --- |", *rows]) + "\n"


def render_markdown(model: SemanticModel) -> str:
    """The whole page for `model`; deterministic, so it can be compared byte for byte."""
    parts = [_HEADER, "## Datasets", "", "| Dataset | Source | Table | Employee level | Currency | One row is |",
             "| --- | --- | --- | --- | --- | --- |", *(_index_row(d) for d in model.datasets), ""]
    parts += ["## Dataset reference", ""] + [_dataset_section(d) for d in model.datasets]
    parts += ["## Deliberately not queryable", "", _excluded("Warehouse", EXCLUDED_WAREHOUSE_TABLES),
              _excluded("Lakehouse source", EXCLUDED_SOURCE_TABLES), _FOOTER]
    return "\n".join(parts).rstrip() + "\n"
