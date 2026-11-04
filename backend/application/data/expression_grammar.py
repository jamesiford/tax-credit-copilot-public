"""The closed grammar a derived column's expression may be written in. [RM-04]

A derived column (`pay_year`, `pay_month`) is the one place the semantic model carries SQL text of
its own, and that text is interpolated into every statement that selects, filters, groups or
aggregates the column. It is reviewed by a person, but a reviewed string can still drift: an edit
adds a subquery, a literal, a comment. So the model refuses to be built with an expression that is
not made only of:

- the column references `{t}.[Col]` (T-SQL) or `{t}."Col"` (SQLite), naming a column the
  column declares it `depends_on`, each dialect naming exactly that set;
- the functions `YEAR`, `MONTH`, `COALESCE`, `CAST ... AS INTEGER` and `strftime`;
- the two `strftime` formats `'%Y'` and `'%Y%m'`;
- integer literals of up to four digits, `+`, `*`, parentheses, commas and spaces.

No subselect, no other string literal, no `;`, no comment, no other function. Widening the grammar
is a change to this file and its test, which is the point.
"""
from __future__ import annotations

import re
from collections.abc import Collection

FUNCTIONS = frozenset({"YEAR", "MONTH", "COALESCE", "CAST", "STRFTIME"})
KEYWORDS = frozenset({"AS", "INTEGER"})
LITERALS = frozenset({"'%Y'", "'%Y%m'"})

_TOKEN = re.compile(
    r"""\{t\}\.\[(?P<tsql>[A-Za-z_][A-Za-z0-9_]*)\]
      | \{t\}\."(?P<lite>[A-Za-z_][A-Za-z0-9_]*)"
      | (?P<string>'[^']*')
      | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<number>\d{1,4})(?!\d)
      | (?P<punct>[(),+*])
      | (?P<space>\s+)""",
    re.VERBOSE,
)


def _tokens(expression: str) -> tuple[list[tuple[str, str]], str | None]:
    """The tokens, or `(partial, the text it could not read)`."""
    found, position = [], 0
    while position < len(expression):
        match = _TOKEN.match(expression, position)
        if match is None:
            return found, expression[position:position + 12]
        kind = match.lastgroup
        if kind != "space":
            found.append((kind, match.group(kind)))
        position = match.end()
    return found, None


def _token_problem(kind: str, text: str, dialect: str) -> str | None:
    if kind in ("tsql", "lite") and kind != dialect:
        return f"{text}: a {kind} column reference in the {dialect} expression"
    if kind == "word" and text.upper() not in FUNCTIONS | KEYWORDS:
        return f"{text!r} is not an allowed function or keyword"
    if kind == "string" and text not in LITERALS:
        return f"the literal {text} is not an allowed format"
    return None


def _parenthesis_problem(tokens: list[tuple[str, str]]) -> str | None:
    depth = 0
    for kind, text in tokens:
        if kind == "punct" and text in "()":
            depth += 1 if text == "(" else -1
            if depth < 0:
                return "a closing parenthesis with no opening one"
    return None if depth == 0 else "unbalanced parentheses"


def expression_problems(expression: str, depends_on: Collection[str], *, dialect: str) -> list[str]:
    """Everything wrong with one dialect's expression (`dialect` is `tsql` or `lite`); empty if it is allowed."""
    tokens, unreadable = _tokens(expression)
    found = [None if unreadable is None else f"cannot be read at {unreadable!r}", _parenthesis_problem(tokens)]
    found += [_token_problem(kind, text, dialect) for kind, text in tokens]
    referenced = {text for kind, text in tokens if kind in ("tsql", "lite")}
    if referenced != set(depends_on):
        found.append(f"references {sorted(referenced)} but depends_on is {sorted(depends_on)}")
    return [problem for problem in found if problem]


def check_expression(logical: str, expression: tuple[str, str], depends_on: Collection[str]) -> None:
    """Raise `ValueError` unless both dialect forms of a derived column are inside the grammar."""
    problems = [
        f"{dialect}: {problem}"
        for text, dialect in zip(expression, ("tsql", "lite"))
        for problem in expression_problems(text, depends_on, dialect=dialect)
    ]
    if problems:
        raise ValueError(f"{logical}: derived expression outside the allowed grammar: " + "; ".join(problems))
