"""Reference dataset -> the source schema shape.

Reshapes the partner's four reconciliation CSVs into its own source
schema. The point is not the data — we already have that — it is to write and
test the Bronze -> Silver projection against the shape the partner will actually
hand us, before the real feed arrives.

The client
----------
The reference dataset is a real client of the partner and is confidential. It is already
de-identified at source: employee and unit IDs are surrogate keys, the two FEINs
are masked placeholders (123456789 / 234567890), and job titles are generic role
names. It is given the codename **Candle Bottle** — a chain of restaurants and
stores — so it can sit alongside synthetic clients in a demo without being
confused for one, and without naming the real employer.

What is faithful, and what is synthesised
-----------------------------------------
Faithful — every field the certified calculation reads, carried through
unchanged:

    EmployeeId, WorksiteLocationId, PayPeriodStart, PayPeriodEnd,
    PaycheckDate, Hours, Wages, FEIN, PayFrequencyId, JobTitle

Synthesised — required by the schema, absent from the CSVs, and **not read by
the v7 calculation**, so parity cannot move:

    AccountId, EntityId, LocationId  surrogate keys we assign
    PayCodeId                        the CSVs carry no pay code; all rows get
                                     'REG'. BA-07 cannot be driven from source
                                     until the partner supplies the lookup (Q5).
    Address, StateCountyZip          needed for county -> Georgia tier, which
                                     affects credit VALUE, never headcount
    HireDate, TerminationDate        absent from the CSVs; would tighten
                                     Min-Max spans if we had them
    CreateDate / ModifyDate          audit columns

`tests/test_source_roundtrip.py` is the guarantee: reference CSV -> source shape
-> BCS -> engine must still produce 10,236 employees, 539 Min-Max and 656 Pay
Period.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .schema import (
    Account,
    Address,
    Employment,
    Entity,
    EntityFiscalYearRules,
    SourceDataset,
    Location,
    PayCode,
    PayFrequency,
    Payroll,
    StateCountyZip,
)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_REFERENCE_DIR = _BACKEND_ROOT / "data" / "payroll"
_REFERENCE_FILES = ("One.csv", "Two.csv", "Three.csv", "Four.csv")

# Codename for the reference client. Not the real employer's name.
REFERENCE_ACCOUNT_ID = 1001
REFERENCE_ACCOUNT_NAME = "Candle Bottle"

# BA-01. The reference client's 53-week payroll calendar — not expressible as a
# month-end fiscal year, which is why the engine takes an explicit window.
REFERENCE_FISCAL_BEGIN = date(2023, 7, 28)
REFERENCE_FISCAL_END = date(2024, 8, 2)

# INFERRED. See schema.PayFrequency — the real lookup was never supplied.
_PAY_FREQUENCY_LABELS = {
    1: "Weekly (inferred: 7-day spans)",
    2: "Semi-monthly (inferred: 15- and 14-day spans)",
    4: "Semi-monthly, 16th-31st (inferred: 16-day spans)",
}

# Georgia counties by tier, used to give each synthetic worksite a plausible
# county. Tier drives credit VALUE, never headcount, so nothing here can move
# the certified figures.
_GA_COUNTIES = [
    ("Fulton", "30303", "Atlanta"),
    ("DeKalb", "30030", "Decatur"),
    ("Cobb", "30060", "Marietta"),
    ("Chatham", "31401", "Savannah"),
    ("Bibb", "31201", "Macon"),
    ("Muscogee", "31901", "Columbus"),
    ("Richmond", "30901", "Augusta"),
    ("Clarke", "30601", "Athens"),
    ("Lowndes", "31601", "Valdosta"),
    ("Dougherty", "31701", "Albany"),
]


def _parse_date(value: str | None) -> date | None:
    """Reference CSVs use M/D/YYYY. The partner's source stores real `date` columns;
    this is the one place the ambiguity has to be resolved."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str | None) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except Exception:  # noqa: BLE001 — a malformed number is data, not a crash
        return None


def _read_reference_rows(source_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in _REFERENCE_FILES:
        path = source_dir / name
        if not path.exists():
            raise FileNotFoundError(f"reference source missing: {path}")
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for ordinal, raw in enumerate(csv.DictReader(fh), start=2):
                # The CSVs carry trailing padding rows with no employee id.
                if not (raw.get("TCCEmployeeId") or "").strip():
                    continue
                raw["_file"] = name
                raw["_row"] = ordinal
                rows.append(raw)
    return rows


def build_reference_source_dataset(
    source_dir: Path | None = None,
    *,
    account_id: int = REFERENCE_ACCOUNT_ID,
    account_name: str = REFERENCE_ACCOUNT_NAME,
) -> SourceDataset:
    """Reshape the four reference CSVs into the partner's source schema."""
    source_dir = Path(source_dir) if source_dir else _REFERENCE_DIR
    raw_rows = _read_reference_rows(source_dir)

    # --- dimensions, discovered from the data -----------------------------
    feins = sorted({(r.get("FEIN") or "").strip() for r in raw_rows if (r.get("FEIN") or "").strip()})
    unit_ids = sorted(
        {(r.get("TCCUnitId") or "").strip() for r in raw_rows if (r.get("TCCUnitId") or "").strip()},
        key=lambda v: int(v) if v.isdigit() else 0,
    )

    fiscal_rule = EntityFiscalYearRules(
        fiscal_year_rules_id=1,
        name=f"{account_name} — 53-week payroll calendar",
        fiscal_year_begin=REFERENCE_FISCAL_BEGIN,
        fiscal_year_end=REFERENCE_FISCAL_END,
        rule_expression="53-week payroll calendar; confirmed with the partner",
    )

    # Entity ids are 1-based positions in the sorted FEIN list, so the mapping
    # is stable across runs — a run manifest that records entity_id must mean
    # the same thing tomorrow.
    entity_by_fein: dict[str, int] = {fein: i for i, fein in enumerate(feins, start=1)}
    entities = [
        Entity(
            entity_id=entity_by_fein[fein],
            account_id=account_id,
            name=f"{account_name} Entity {entity_by_fein[fein]}",
            federal_tax_id=fein,
            # First entity is the parent; the rest hang off it. Gives CALC-06
            # a real hierarchy to walk instead of a flat list.
            parent_entity_id=None if entity_by_fein[fein] == 1 else 1,
            fiscal_year_rules_id=fiscal_rule.fiscal_year_rules_id,
        )
        for fein in feins
    ]
    primary_entity_id = entities[0].entity_id if entities else 1

    # Each unit gets an address and a Georgia county, cycling the county list.
    # SYNTHESISED: county drives credit value, never headcount.
    state_county_zips: list[StateCountyZip] = []
    addresses: list[Address] = []
    locations: list[Location] = []
    location_by_unit: dict[str, int] = {}

    for idx, (county, zip_code, city) in enumerate(_GA_COUNTIES, start=1):
        state_county_zips.append(
            StateCountyZip(
                state_county_zip_id=idx,
                state_abbr="GA",
                state_name="Georgia",
                county_name=county,
                zip_code=zip_code,
            )
        )

    for i, unit in enumerate(unit_ids, start=1):
        county, zip_code, city = _GA_COUNTIES[(i - 1) % len(_GA_COUNTIES)]
        scz_id = ((i - 1) % len(_GA_COUNTIES)) + 1
        addresses.append(
            Address(
                address_id=i,
                street_address_1=f"{100 + i} Peachtree Way",
                city_name=city,
                state_county_zip_id=scz_id,
                zip_code_original=zip_code,
                state_original="GA",
            )
        )
        locations.append(
            Location(
                location_id=i,
                account_id=account_id,
                entity_id=primary_entity_id,
                location_name=f"Unit {unit}",
                client_location_id=unit,   # the client's own id, preserved
                address_id=i,
            )
        )
        location_by_unit[unit] = i

    pay_codes = [
        PayCode(
            pay_code_id=1,
            account_id=account_id,
            pay_code="REG",
            description="Regular (assigned — reference CSVs carry no pay code)",
            is_futa=True,
        )
    ]

    pay_frequencies = [
        PayFrequency(pay_frequency_id=k, name=v) for k, v in sorted(_PAY_FREQUENCY_LABELS.items())
    ]

    # --- employment: one row per employee, job title from first sighting ---
    employment_by_employee: dict[int, Employment] = {}
    for r in raw_rows:
        try:
            emp_id = int((r.get("TCCEmployeeId") or "").strip())
        except ValueError:
            continue
        if emp_id in employment_by_employee:
            continue
        unit = (r.get("TCCUnitId") or "").strip()
        employment_by_employee[emp_id] = Employment(
            employment_id=len(employment_by_employee) + 1,
            employee_id=emp_id,
            hire_location_id=location_by_unit.get(unit),
            current_location_id=location_by_unit.get(unit),
            status="Active",
            job_title=(r.get("JobTitle") or "").strip() or None,
            # SYNTHESISED: hire and termination dates are absent from the CSVs.
            # Left null rather than invented — a fabricated hire date would look
            # authoritative and is not.
            hire_date=None,
            termination_date=None,
        )

    # --- payroll fact -----------------------------------------------------
    payroll: list[Payroll] = []
    unknown_units = 0
    for i, r in enumerate(raw_rows, start=1):
        emp_raw = (r.get("TCCEmployeeId") or "").strip()
        try:
            emp_id = int(emp_raw)
        except ValueError:
            continue

        unit = (r.get("TCCUnitId") or "").strip()
        location_id = location_by_unit.get(unit)
        if location_id is None:
            unknown_units += 1
            continue

        fein = (r.get("FEIN") or "").strip()
        freq_raw = (r.get("PayFrequency") or "").strip()
        try:
            freq_id = int(freq_raw) if freq_raw else 0
        except ValueError:
            freq_id = 0

        payroll.append(
            Payroll(
                payroll_id=i,
                account_id=account_id,
                employee_id=emp_id,
                entity_id=entity_by_fein.get(fein, primary_entity_id),
                location_id=location_id,
                worksite_location_id=location_id,
                pay_frequency_id=freq_id,
                pay_period_start=_parse_date(r.get("PayPeriodStart")),
                pay_period_end=_parse_date(r.get("PayPeriodEnd")),
                pay_date=_parse_date(r.get("PaycheckDate")),
                hours=_parse_decimal(r.get("Hours")),
                wages=_parse_decimal(r.get("Wages")),
                pay_code_id=1,
                client_employee_id=emp_raw,
                inload_payroll_id=None,
            )
        )

    if unknown_units:
        raise ValueError(f"{unknown_units} payroll rows referenced an unmapped unit")

    account = Account(
        account_id=account_id,
        account_eid=account_id,
        name=account_name,
        billing_state="GA",
        billing_city="Atlanta",
        billing_postal_code="30303",
        actual_number_of_employees=len(employment_by_employee),
        external_name=account_name,
    )

    return SourceDataset(
        account=account,
        entities=entities,
        locations=locations,
        addresses=addresses,
        state_county_zips=state_county_zips,
        employments=sorted(employment_by_employee.values(), key=lambda e: e.employment_id),
        pay_codes=pay_codes,
        pay_frequencies=pay_frequencies,
        fiscal_year_rules=[fiscal_rule],
        payroll=payroll,
    )
