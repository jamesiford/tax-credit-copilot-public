"""Human resolutions of QC exceptions, and how they reach the calculation.

This is the in-memory store the ingestion router used to own. It lives in the
application layer because two things read it: the resolve command writes it, and
every calculation that loads payroll (`payroll_rows.require_pay_periods(drop_qc=True)`)
filters its rows through it. A payroll reader that had to import a router to find
the store was the dependency the layering rules exist to prevent.

In-memory: it resets on restart. Production persists to the audit store.
"""
from __future__ import annotations

from typing import Any

QC_RESOLUTIONS: dict[str, dict[str, Any]] = {}


def reset_qc_resolutions() -> None:
    """Test hook — clear the in-memory QC resolution store."""
    QC_RESOLUTIONS.clear()


def exception_id(anomaly: dict[str, Any]) -> str:
    """Deterministic id so a resolution sticks to the same anomaly across reloads.

    A scraggly period is keyed by its payroll LINE (`tools.qc.pay_line_keys`),
    not by (employee, worksite, pay_date): several lines share that triple, and
    keying on it gave them one id, so resolving one resolved all of them.
    """
    if anomaly.get("type") == "test_of_twos":
        return f"t2:{anomaly.get('employee_id')}:{anomaly.get('month')}"
    return f"pp:{anomaly.get('line_key')}"


def _drop_rules() -> tuple[dict[tuple[str, str], str], set[str]]:
    """What the resolutions say to remove: `(employee, month) -> worksite to keep`, and line keys."""
    t2_keep: dict[tuple[str, str], str] = {}
    pp_drop: set[str] = set()
    for eid, res in QC_RESOLUTIONS.items():
        parts = eid.split(":")
        if eid.startswith("t2:") and res.get("resolution") == "assign" and res.get("keep_worksite"):
            if len(parts) >= 3:
                t2_keep[(parts[1], parts[2])] = res["keep_worksite"]
        elif eid.startswith("pp:") and res.get("resolution") == "drop":
            pp_drop.add(eid[3:])
    return t2_keep, pp_drop


def _is_dropped(row: dict[str, Any], line_key: str | None, t2_keep: dict, pp_drop: set[str]) -> bool:
    emp = str(row.get("Employee_ID", ""))
    ws = str(row.get("Worksite_ID", ""))
    month = str(row.get("Pay_Date", ""))[:7]
    keep_ws = t2_keep.get((emp, month))
    if keep_ws is not None and ws != keep_ws:
        return True  # double-count reassigned away from this unit
    return line_key in pp_drop  # scraggly line dropped


def apply_calc_drops(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter pay-period rows per the human QC resolutions so a resolved exception
    actually flows into the calculation (option-b correction loop).

    * **test-of-twos** resolved `assign` with `keep_worksite=W` → for that
      (employee, month) the rows at every OTHER unit are dropped, so the head is
      no longer double-counted across units (the engine only dedupes per-unit).
    * **scraggly period** resolved `drop` → that one payroll LINE is removed.
      Other lines paid to the same person at the same site on the same day
      stay; dropping them too would remove wages nobody flagged.

    `accept` / `flag` are annotations — they never change the rows. Applied only
    to the CALC row-sets (see `require_pay_periods(drop_qc=True)`), never to the
    QC detector, so a resolved exception still lists with its status.
    """
    if not QC_RESOLUTIONS:
        return rows
    t2_keep, pp_drop = _drop_rules()
    if not t2_keep and not pp_drop:
        return rows

    from tools.qc import pay_line_keys

    line_keys = pay_line_keys(rows) if pp_drop else [None] * len(rows)
    return [r for r, key in zip(rows, line_keys) if not _is_dropped(r, key, t2_keep, pp_drop)]
