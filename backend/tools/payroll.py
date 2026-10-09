"""Payroll data tools."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data" / "payroll.csv"
WINDOW_START = date(2024, 12, 1)
WINDOW_MONTHS = 18


def _load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not _DATA.exists():
        return rows
    with _DATA.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["annual_wage"] = int(r["annual_wage"])
            r["hours_by_month"] = [int(h) for h in r["hours_by_month"].split(";")]
            rows.append(r)
    return rows
