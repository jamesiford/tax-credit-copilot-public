"""The committed synthetic payroll sample, relabelled to a draft's state, for the draft preview. [F05.4]

Reads `data/payroll_pay_periods.csv` directly, whatever `DATA_SOURCE` says: a preview on the sample must never touch a customer's
payroll by accident. The rows are generated, de-identified by construction, and relabelled from the sample's own state to the
draft's so the engine finds work in the state the draft is about. Nothing here is a client's figure.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "payroll_pay_periods.csv"
_SAMPLE_STATE = "GA"

#: What a preview says about its data, so no screen shows a sample figure as a client's.
SAMPLE_DESCRIPTION = "Committed synthetic sample payroll (generated; not a client's data), relabelled to the draft's state"


def sample_rows(state: str) -> list[dict[str, Any]]:
    """The sample's rows with their worksite state relabelled to `state`; empty when the sample file is absent."""
    if not SAMPLE_CSV.exists():
        return []
    rows: list[dict[str, Any]] = []
    with SAMPLE_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            site = row["Worksite_ID"]
            if not site.startswith(f"{_SAMPLE_STATE}_"):
                continue
            rows.append({**row, "Worksite_ID": f"{state}_{site[len(_SAMPLE_STATE) + 1:]}", "Tax_Year": int(row["Tax_Year"]),
                         "Hours_Worked": float(row["Hours_Worked"]), "Gross_Wages": float(row["Gross_Wages"])})
    return rows
