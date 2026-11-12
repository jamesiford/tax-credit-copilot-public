"""The client book's entry shape: a contract with its consumers, not a column list. [06]

`list_accounts()` (both readers) returns dicts with these keys, and `application/client_book.py`, the portfolio and
the warm-up read them. They are named for the entry, not for any lake: which physical column carries each is the
source mapping's business.
"""
from __future__ import annotations

from typing import Any

#: logical `Account` field -> the key it has in a client-book entry.
BOOK_FIELDS: tuple[tuple[str, str], ...] = (
    ("account_id", "AccountId"), ("name", "Name"), ("billing_state", "BillingState"),
    ("actual_number_of_employees", "ActualNumberOfEmployees"), ("industry_type_id", "IndustryTypeId"),
)


def book_entry(row: dict[str, Any]) -> dict[str, Any]:
    """One `Account` row (keyed by logical field) as a client-book entry; fields the lake did not carry are absent."""
    return {key: row[name] for name, key in BOOK_FIELDS if name in row}
