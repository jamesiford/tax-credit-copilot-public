"""Filter values: coerced to the column's type, refused if they look like SQL. [CH-16b]

Every value reaches the database as a bound parameter, so a quote in a value cannot
change the statement. These checks are the second wall, not the first: a model that is
being steered by text from a document or an email may try to put SQL in a filter, and a
rejected value is a signal worth surfacing rather than a string quietly passed along.

The check is deliberately a little paranoid for equality-style filters and relaxed for
the one place free text belongs, a `contains` filter on a free-text dimension, where it
still refuses control characters and is escaped for `LIKE`.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from application.data.errors import SqlLikeValue, ValueNotAllowed, ValueTypeMismatch
from application.data.spec import MAX_TEXT
from application.data.semantic_model import ColType, Column

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")
_SQL_PUNCTUATION = re.compile(r";|--|/\*|\*/|@@|\bxp_\w")
_SQL_QUOTE_TRICK = re.compile(r"['\"`]\s*(?:or|and|union|having|order|group|;|--)\b|['\"`]\s*[=<>]", re.IGNORECASE)
_SQL_STATEMENT = re.compile(
    r"\b(?:select|insert|update|delete|drop|alter|create|truncate|exec|execute|union|merge|grant|declare|waitfor|shutdown)"
    r"\b[\s(]+\S", re.IGNORECASE,
)
_MAX_INT = 10**12


def has_control_characters(text: str) -> bool:
    """True for a control, format (zero-width, bidi) or unassigned character: never part of a plain value."""
    return any(unicodedata.category(ch) in ("Cc", "Cf", "Cn", "Co", "Cs") for ch in text)


def looks_like_sql(text: str) -> bool:
    """True when `text` reads as SQL rather than as a value.

    Checked on the NFKC form, so full-width and compatibility characters cannot hide a
    keyword or a semicolon. False positives (a job title that begins "Select ...") are
    acceptable: the caller is told which field and can rephrase.
    """
    folded = unicodedata.normalize("NFKC", text)
    return bool(_SQL_PUNCTUATION.search(folded) or _SQL_QUOTE_TRICK.search(folded) or _SQL_STATEMENT.search(folded))


def escape_like(text: str) -> str:
    """Escape `LIKE` wildcards (and the escape character) so `contains` means a literal substring."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("[", "\\[")


def coerce(column: Column, raw: Any, *, field: str, plain: bool) -> Any:
    """`raw` as the Python value for `column`'s type, or ValueTypeMismatch / SqlLikeValue / ValueNotAllowed.

    `plain` means an equality-style filter, where text is also screened for SQL.
    """
    kind = column.type
    if kind is ColType.TEXT:
        return _text(column, raw, field, plain)
    if kind is ColType.BOOL:
        return _bool(raw, field)
    if kind is ColType.INT:
        return _int(raw, field)
    if kind is ColType.DECIMAL:
        return _decimal(raw, field)
    return _temporal(kind, raw, field)


def _mismatch(field: str, expected: str) -> ValueTypeMismatch:
    return ValueTypeMismatch(f"the value must be {expected}", field=field)


def _text(column: Column, raw: Any, field: str, plain: bool) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > MAX_TEXT:
        raise _mismatch(field, f"a non-empty string of at most {MAX_TEXT} characters")
    if has_control_characters(raw) or (plain and looks_like_sql(raw)):
        raise SqlLikeValue("the value looks like SQL or contains control characters; give a plain value", field=field)
    if plain and column.choices and raw not in column.choices:
        raise ValueNotAllowed("the value is not one this column holds; see the catalog for its values", field=field)
    return raw


def _bool(raw: Any, field: str) -> bool:
    if not isinstance(raw, bool):
        raise _mismatch(field, "true or false")
    return raw


def _int(raw: Any, field: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or abs(raw) > _MAX_INT:
        raise _mismatch(field, "an integer")
    return raw


def _decimal(raw: Any, field: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise _mismatch(field, "a number")
    if isinstance(raw, float) and not math.isfinite(raw):
        raise _mismatch(field, "a finite number")
    if abs(raw) > _MAX_INT:
        raise _mismatch(field, "a number below one trillion")
    return Decimal(str(raw))


def _temporal(kind: ColType, raw: Any, field: str) -> date | datetime:
    if kind is ColType.DATE and isinstance(raw, str) and _DATE.match(raw):
        parser = date.fromisoformat
    elif kind is ColType.DATETIME and isinstance(raw, str) and (_DATE.match(raw) or _DATETIME.match(raw)):
        parser = datetime.fromisoformat
    else:
        raise _mismatch(field, "an ISO date (YYYY-MM-DD)" if kind is ColType.DATE else "an ISO date or date-time")
    try:
        return parser(raw)
    except ValueError:
        raise _mismatch(field, "a real calendar date") from None
