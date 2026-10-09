"""[F0 · ROADMAP-V] Author Fabric-shaped MeridianCore seed CSVs.

Produces the Microsoft Fabric Lakehouse `employees` shape (the real 39-column
schema the partner's payroll lands in) from the EXISTING MeridianCore pay-period
data, so the data is the same MeridianCore book (GA + TN + the rest) just
reshaped — the reverse of `tools/fabric_source.py:map_fabric_employees_row`.

Reading these back through the mapper reconstructs today's pay-period rows
exactly, so every demo number (GA 60.59 average headcount, $328K GJTC, …) holds:
"shape is the Fabric shape, data is the same MeridianCore data." That round-trip
is the POC-02 reconciliation (see tests/test_fabric_source.py).

Outputs to `backend/data/fabric_seed/`:
  * ``Employees.csv``   — 39-col Fabric `employees` shape (synthetic PII; no real SSNs).
  * ``Locations.csv``   — MeridianCore locations (FEIN / entity / city per worksite).
  * ``Paycode.csv`` / ``Termcode.csv`` / ``WOTC_PayCode.csv`` — reference tables.

The user uploads these to overwrite the Lakehouse tables; the app then reads the
schema-enabled `dbo/employees` Delta table via OneLake (`DATA_SOURCE=fabric`).

Deterministic (hash-seeded per employee) so re-running is stable. SYNTHETIC data
only — SSNs use the invalid 9xx area so nothing resembles a real identifier.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PAY_PERIODS = _HERE / "payroll_pay_periods.csv"
_OUT_DIR = _HERE / "fabric_seed"

# Full Fabric `employees` schema (order matters — mirrors the Lakehouse sample).
_EMPLOYEE_COLUMNS = [
    "Social_Security_Number", "Employee_ID", "DOB", "First_Name", "MI", "Last_Name",
    "Suffix", "Home_Address", "City", "State", "Zip", "Country", "Hire_Date",
    "Rehire_Date", "Term_Date", "Last_Day_Worked", "Term_Reason", "SUI_Acct",
    "Job_Title", "Months_of_Service", "Location_ID", "FEIN", "Worksite_ID",
    "Work_State", "Pay_Period_Start", "Pay_Period_End", "Check_Date",
    "Pay_Frequency", "Hours", "Gross_Wages", "Pay_Rate", "Rate_Type", "Currency",
    "Earning_Code", "Employment_Type", "Wage_Type", "Status", "Work_Email", "Branch",
]

_FIRST = ["Angela", "Thomas", "Lisa", "Richard", "Debra", "Maria", "James", "Karen",
          "Robert", "Linda", "Michael", "Patricia", "David", "Jennifer", "William",
          "Susan", "Joseph", "Nancy", "Charles", "Sandra"]
_LAST = ["Wright", "Reed", "Diaz", "Johnson", "Wood", "Chen", "Ford", "Smith", "Brown",
         "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
         "White", "Harris", "Martin"]
_STREETS = ["Lake", "Cherry", "Pine", "River", "Park", "Highland", "Center", "Maple",
            "Oak", "Washington", "Spruce", "Meadow", "Hill", "View"]
_SUFFIXES = ["St", "Ln", "Dr", "Ave", "Blvd"]


def _h(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16)


def _mdy(iso: str) -> str:
    """ISO `YYYY-MM-DD` -> Fabric `M/D/YYYY` (no leading zeros), mirroring the sample."""
    d = date.fromisoformat(iso[:10])
    return f"{d.month}/{d.day}/{d.year}"


def _site_lookup() -> dict[str, dict]:
    """{site_id: {city, state, name}} from the physical-site registry (best effort)."""
    out: dict[str, dict] = {}
    try:
        from data.sites import SITES  # type: ignore
        for s in SITES:
            out[s.site_id] = {"city": s.city, "state": s.state, "name": s.name}
    except Exception:  # noqa: BLE001 — registry optional; fall back to state-derived
        pass
    return out


def _split_worksite(worksite_id: str) -> tuple[str, str]:
    """`GA_SAV_DC` -> (`GA`, `SAV_DC`). The mapper rebuilds `GA_` + `SAV_DC`."""
    if len(worksite_id) > 3 and worksite_id[2] == "_":
        return worksite_id[:2], worksite_id[3:]
    return "", worksite_id


def _load_pay_periods() -> list[dict]:
    with _PAY_PERIODS.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build(out_dir: Path | None = None, as_of: date | None = None) -> dict[str, int]:
    """Write the seed CSVs into ``out_dir`` (default: the tracked ``fabric_seed/``).

    ``as_of`` fixes the date `Months_of_Service` is measured from. Tests pass
    both, so a test run never rewrites a tracked file and the output does not
    change with the calendar.
    """
    out = Path(out_dir) if out_dir is not None else _OUT_DIR
    ref = as_of or date.today()
    rows = _load_pay_periods()
    sites = _site_lookup()
    out.mkdir(parents=True, exist_ok=True)

    # Stable Location_ID per worksite (in first-seen order).
    worksites: list[str] = []
    for r in rows:
        if r["Worksite_ID"] not in worksites:
            worksites.append(r["Worksite_ID"])
    location_id = {wid: f"MC{ i+1 :04d}" for i, wid in enumerate(worksites)}

    # Per-employee stable profile (PII synthesized once; hire date = earliest PPS).
    profiles: dict[str, dict] = {}
    hire: dict[str, str] = {}
    for r in rows:
        eid = r["Employee_ID"]
        pps = r["Pay_Period_Start"]
        if eid not in hire or pps < hire[eid]:
            hire[eid] = pps
    for eid in sorted(hire):
        h = _h(eid)
        first = _FIRST[h % len(_FIRST)]
        last = _LAST[(h // 7) % len(_LAST)]
        area = 900 + (h % 100)
        profiles[eid] = {
            "ssn": f"{area:03d}-{(h // 11) % 100:02d}-{(h // 13) % 10000:04d}",
            "first": first, "mi": chr(65 + (h // 17) % 26), "last": last,
            "dob": f"{1 + (h // 3) % 12}/{1 + (h // 5) % 28}/{1962 + (h % 34)}",
            "home": f"{100 + (h % 9900)} {_STREETS[h % len(_STREETS)]} {_SUFFIXES[(h // 19) % len(_SUFFIXES)]}",
            "zip": f"{10000 + (h % 89999):05d}",
            "sui": f"{100000 + (h % 900000)}",
            "email": f"{first.lower()}.{last.lower()}{eid[-3:]}@meridiancore.example",
        }

    # --- Employees.csv (one row per pay-period line, the same grain the partner uses) ---
    emp_path = out / "Employees.csv"
    with emp_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_EMPLOYEE_COLUMNS)
        w.writeheader()
        for r in rows:
            eid = r["Employee_ID"]
            p = profiles[eid]
            work_state, raw_worksite = _split_worksite(r["Worksite_ID"])
            site = sites.get(r["Worksite_ID"], {})
            city = site.get("city", "")
            hours = float(r["Hours_Worked"])
            gross = float(r["Gross_Wages"])
            pps, ppe = r["Pay_Period_Start"], r["Pay_Period_End"]
            span_days = (date.fromisoformat(ppe) - date.fromisoformat(pps)).days + 1
            rate = round(gross / hours, 2) if hours else 0.0
            hire_iso = hire[eid]
            months_service = max(0, (ref.year - date.fromisoformat(hire_iso).year) * 12
                                 + ref.month - date.fromisoformat(hire_iso).month)
            w.writerow({
                "Social_Security_Number": p["ssn"], "Employee_ID": eid, "DOB": p["dob"],
                "First_Name": p["first"], "MI": p["mi"], "Last_Name": p["last"], "Suffix": "",
                "Home_Address": p["home"], "City": city, "State": work_state, "Zip": p["zip"],
                "Country": "US", "Hire_Date": _mdy(hire_iso), "Rehire_Date": "",
                "Term_Date": "", "Last_Day_Worked": "", "Term_Reason": "", "SUI_Acct": p["sui"],
                "Job_Title": r["Job_Title"], "Months_of_Service": months_service,
                "Location_ID": location_id[r["Worksite_ID"]], "FEIN": r["Entity_FEIN"],
                "Worksite_ID": raw_worksite, "Work_State": work_state,
                "Pay_Period_Start": _mdy(pps), "Pay_Period_End": _mdy(ppe),
                "Check_Date": _mdy(r["Pay_Date"]), "Pay_Frequency": "Weekly" if span_days <= 7 else "Biweekly",
                "Hours": f"{hours:.2f}", "Gross_Wages": f"${gross:,.2f} ",
                "Pay_Rate": f"${rate:,.2f} ", "Rate_Type": "Hourly", "Currency": "USD",
                "Earning_Code": r["Pay_Code"], "Employment_Type": "Full-Time",
                "Wage_Type": "Hourly", "Status": "Active", "Work_Email": p["email"],
                "Branch": site.get("name", raw_worksite),
            })

    # --- Locations.csv (one row per worksite) ---
    try:
        from data.entities import entity_name
    except Exception:  # noqa: BLE001
        def entity_name(fein: str) -> str:  # type: ignore
            return fein
    fein_by_worksite: dict[str, str] = {}
    for r in rows:
        fein_by_worksite.setdefault(r["Worksite_ID"], r["Entity_FEIN"])
    loc_cols = ["EmployerLocationID", "FEIN", "SEIN", "EntityName", "InternalLocationName",
                "ExternalLocationName", "LocationType", "DateOpened", "DateClosed",
                "Street", "City", "State", "PostalCode", "CountryCode"]
    with (out / "Locations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=loc_cols)
        w.writeheader()
        for wid in worksites:
            work_state, raw = _split_worksite(wid)
            site = sites.get(wid, {})
            fein = fein_by_worksite.get(wid, "")
            w.writerow({
                "EmployerLocationID": location_id[wid], "FEIN": fein, "SEIN": "",
                "EntityName": entity_name(fein), "InternalLocationName": site.get("name", raw),
                "ExternalLocationName": "MeridianCore", "LocationType": "Distribution",
                "DateOpened": "", "DateClosed": "", "Street": "",
                "City": site.get("city", ""), "State": work_state, "PostalCode": "",
                "CountryCode": "US",
            })

    # --- Reference tables (small, static) ---
    _write_ref(out / "Paycode.csv", ["Earning_Code", "Description"], [
        ("Regular", "Regular Wages"), ("Overtime", "Overtime Wages"), ("Holiday", "Holiday Pay"),
        ("PTO", "Paid Time Off"), ("Bonus", "Spot Bonus"), ("PerDiem", "Per Diem"),
    ])
    _write_ref(out / "Termcode.csv", ["Term_Reason", "Description"], [
        ("Resigned", "Employee Resigned"), ("Ended", "Assignment Ended"),
        ("Terminated", "Terminated for Cause"), ("Layoff", "Laid Off"), ("NoShow", ""),
    ])
    _write_ref(out / "WOTC_PayCode.csv", ["Earning_Code", "WOTC_Includable"], [
        ("Regular", "Y"), ("Overtime", "Y"), ("Holiday", "Y"), ("PTO", "N"),
        ("Bonus", "Y"), ("PerDiem", "N"),
    ])

    return {"employees_rows": len(rows), "worksites": len(worksites), "employees": len(profiles)}


def _write_ref(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


if __name__ == "__main__":
    stats = build()
    print(f"Wrote Fabric seed CSVs to {_OUT_DIR}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
