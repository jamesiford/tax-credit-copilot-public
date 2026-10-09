"""The `filter=` grammar, parsed once and compiled into SQL predicates.

The wire form is the one `frontend/src/lib/gridFilter.js` writes:

    col:expr;col:expr

    text     ``employee_id:~ABC``          contains, case-insensitive
    numeric  ``avg_weekly_hours:>=35``     comparator
             ``weeks_worked:10..52``       inclusive range
    enum     ``status:qualified|declined`` multi-select

Two rules hold this together:

* **The column must be on a whitelist supplied by the caller.** The value comes
  from a query string, so the column name is never interpolated unless it
  matched a key the endpoint declared. Values are always bound parameters.
* **An unparseable term is DROPPED, not passed through.** A predicate that
  silently matches everything is worse than no filter, because the page says it
  is filtering and the total says otherwise. The parser reports back what it
  actually applied so the response can say so.

Filed in `tools/` rather than beside a router because both `api/` and
`infrastructure/` compile it, and infrastructure may not import from api.
"""

from __future__ import annotations

from typing import Any

#: Longest first: ``>=`` must win over ``>``.
_COMPARATORS = (">=", "<=", ">", "<", "=")

Predicate = tuple[str, list[Any]]


def _number(text: str) -> float | None:
    try:
        return float(text.strip())
    except (TypeError, ValueError):
        return None


def _numeric_predicate(column: str, expr: str) -> Predicate | None:
    if ".." in expr:
        low, _, high = expr.partition("..")
        a, b = _number(low), _number(high)
        if a is None or b is None:
            return None
        return f"{column} >= ? AND {column} <= ?", [min(a, b), max(a, b)]
    for op in _COMPARATORS:
        if expr.startswith(op):
            value = _number(expr[len(op):])
            return None if value is None else (f"{column} {op} ?", [value])
    # A bare number reads as ">=", matching the browser: every numeric column
    # here answers an "at least" question, and an exact match on a two-decimal
    # average matches nothing.
    value = _number(expr)
    return None if value is None else (f"{column} >= ?", [value])


def _text_predicate(column: str, expr: str) -> Predicate | None:
    needle = expr[1:] if expr.startswith("~") else expr
    needle = needle.strip()
    if not needle:
        return None
    # LIKE wildcards in the needle would let a filter widen itself, so they are
    # escaped rather than honoured.
    escaped = needle.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    return f"LOWER({column}) LIKE ?", [f"%{escaped.lower()}%"]


def _enum_predicate(column: str, expr: str) -> Predicate | None:
    values = [part.strip() for part in expr.split("|") if part.strip()]
    if not values:
        return None
    marks = ", ".join("?" for _ in values)
    return f"{column} IN ({marks})", list(values)


_BUILDERS = {
    "numeric": _numeric_predicate,
    "text": _text_predicate,
    "enum": _enum_predicate,
}


def compile_filters(
    wire: str | None, columns: dict[str, tuple[str, str]]
) -> tuple[str, list[Any], dict[str, str]]:
    """Compile ``filter=`` into ``(sql, values, applied)``.

    `columns` maps a wire column name to ``(sql_expression, type)``. Anything
    not in it is ignored — the endpoint decides what is filterable, not the
    caller.

    `applied` is what actually compiled, echoed back so the response can state
    which filters are in force rather than the page assuming its own request
    took effect.
    """
    clauses: list[str] = []
    values: list[Any] = []
    applied: dict[str, str] = {}
    for term in str(wire or "").split(";"):
        name, sep, expr = term.partition(":")
        if not sep:
            continue
        name, expr = name.strip(), expr.strip()
        spec = columns.get(name)
        if not spec or not expr:
            continue
        sql_column, kind = spec
        built = _BUILDERS[kind](sql_column, expr)
        if built is None:
            continue
        clause, params = built
        clauses.append(f"({clause})")
        values.extend(params)
        applied[name] = expr
    return (" AND " + " AND ".join(clauses)) if clauses else "", values, applied
