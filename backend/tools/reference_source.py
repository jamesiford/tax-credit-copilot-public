"""Private Reference Dataset source adapter and de-identified manifest.

This module reads the partner's four TCC payroll chunks as one ordered logical source.
It is deliberately separate from ``api._payperiods`` and the production
``DATA_SOURCE`` switch: raw Reference Dataset rows are local benchmark inputs only.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from .credit_math import StatutoryFloors

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Methodology sets are CONFIGURATION, not documentation. They were read from
# docs/data/ until a docs reorganisation moved them and the engine stopped
# booting - production code should never depend on the layout of a docs folder.
# They now live beside the rule packs they are versioned alongside.
_METHODOLOGY = Path(__file__).resolve().parent.parent / "rules" / "methodology"
_DEFAULT_SOURCE_DIR = Path(__file__).resolve().parent.parent / "data" / "payroll"
_DEFAULT_ASSUMPTIONS = _METHODOLOGY / "reference-dataset-assumptions.v8.json"
_CERTIFIED_FIGURES = _METHODOLOGY / "certified-figures.json"

# The EXECUTABLE assumption sets. v1-v7 remain on disk under docs/data/ as the
# audit trail of how we converged with the partner, and the workspace history endpoint
# still reads them as documents — but they are no longer runnable.
#
# They cannot be: from v8 the statutory floors are resolved from the year-scoped
# rule pack rather than read out of BA-06 [ADR-005], and v1-v7 carry no
# `program_code`/`tax_year` to resolve with. Rather than teach the engine a
# second, legacy read path, we retired them. Published sets are immutable, so
# back-filling the new keys into them was never an option.
_ASSUMPTION_PATHS = {
    "GDS-STEP1-2026-08-25-v8": _DEFAULT_ASSUMPTIONS,
}
_ASSUMPTION_COUNTS = {
    "GDS-STEP1-2026-08-25-v8": 12,
}

# Superseded sets, kept for display and provenance only. Ordered oldest first.
RETIRED_ASSUMPTION_SETS = (
    "GDS-STEP1-2026-07-29-v1",
    "GDS-STEP1-2026-07-29-v2",
    "GDS-STEP1-2026-07-29-v3",
    "GDS-STEP1-2026-07-30-v4",
    "GDS-STEP1-2026-08-05-v5",
    "GDS-STEP1-2026-08-18-v6",
    "GDS-STEP1-2026-08-24-v7",
)

TCC_COLUMNS = (
    "TCCEmployeeId",
    "Tax Year",
    "JobTitle",
    "TCCUnitId",
    "PayPeriodStart",
    "PayPeriodEnd",
    "PaycheckDate",
    "PayFrequency",
    "FEIN",
    "Hours",
    "Wages",
)
_REQUIRED_VALUES = (
    "TCCEmployeeId",
    "Tax Year",
    "TCCUnitId",
    "PayPeriodStart",
    "PayPeriodEnd",
    "PaycheckDate",
    "PayFrequency",
    "FEIN",
)


def _parse_date(value: str) -> date:
    text = value.strip()
    try:
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return date.fromisoformat(text[:10])
        month, day, year = text.split("/")
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid date value: {text!r}") from exc


def _parse_decimal(value: str) -> Decimal:
    text = value.strip().replace("$", "").replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid numeric value") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def load_assumption_set(path: Path = _DEFAULT_ASSUMPTIONS) -> dict[str, Any]:
    """Load and minimally validate the tracked Step 1 assumption set."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    assumption_set_id = payload.get("assumption_set_id")
    if assumption_set_id not in _ASSUMPTION_PATHS:
        raise ValueError("unsupported Reference Dataset assumption set")
    assumptions = payload.get("assumptions") or {}
    last_assumption = _ASSUMPTION_COUNTS[assumption_set_id]
    expected = {f"BA-{index:02d}" for index in range(1, last_assumption + 1)}
    if set(assumptions) != expected:
        raise ValueError(f"Reference Dataset assumption set must contain BA-01 through BA-{last_assumption:02d}")
    return payload


def load_assumption_set_for_id(assumption_set_id: str) -> dict[str, Any]:
    try:
        path = _ASSUMPTION_PATHS[assumption_set_id]
    except KeyError as exc:
        if assumption_set_id in RETIRED_ASSUMPTION_SETS:
            raise ValueError(
                f"assumption set {assumption_set_id} is retired and no longer runnable. "
                f"It predates ADR-005, so it holds statutory floors in BA-06 instead of "
                f"naming a program and tax year to resolve them from. Use "
                f"{next(iter(_ASSUMPTION_PATHS))}."
            ) from exc
        raise ValueError("unsupported Reference Dataset assumption set") from exc
    return load_assumption_set(path)


def statutory_floors_for(assumption_set: dict[str, Any]) -> "StatutoryFloors":
    """Resolve the statutory floors an assumption set measures against.

    An assumption set says HOW to measure; the rule pack says WHAT the threshold
    is. This is the seam between them: the set names a programme and a tax year,
    and the floors come from that year's pack. [ADR-005]
    """
    from .credit_math import resolve_statutory_floors

    program_code = assumption_set.get("program_code")
    tax_year = assumption_set.get("tax_year")
    if not program_code or tax_year is None:
        raise ValueError(
            f"assumption set {assumption_set.get('assumption_set_id')} does not name a "
            f"program_code and tax_year, so its statutory floors cannot be resolved."
        )
    return resolve_statutory_floors(str(program_code), int(tax_year))


@dataclass(frozen=True)
class ReferencePayrollRow:
    source_file: str
    source_row: int
    source_tax_year: int
    employee_id: str
    job_title: str
    unit_id: str
    pay_period_start: date
    pay_period_end: date
    pay_date: date
    pay_frequency_code: str
    fein: str
    hours: Decimal
    wages: Decimal

    def collapse_key(self) -> tuple[str, str, str, date, date, date, str]:
        """BA-04 audit-preserving duplicate key."""
        return (
            self.employee_id,
            self.unit_id,
            self.fein,
            self.pay_period_start,
            self.pay_period_end,
            self.pay_date,
            self.pay_frequency_code,
        )

    def to_engine_dict(self) -> dict[str, Any]:
        """Map into the current deterministic engine's pay-period shape."""
        return {
            "Tax_Year": self.source_tax_year,
            "Employee_ID": self.employee_id,
            "Job_Title": self.job_title,
            "Worksite_ID": self.unit_id,
            "Pay_Period_Start": self.pay_period_start.isoformat(),
            "Pay_Period_End": self.pay_period_end.isoformat(),
            "Pay_Date": self.pay_date.isoformat(),
            "Pay_Frequency": self.pay_frequency_code,
            "Entity_FEIN": self.fein,
            "Hours_Worked": float(self.hours),
            "Gross_Wages": float(self.wages),
            "Pay_Code": "Unknown",
            "_Source_File": self.source_file,
            "_Source_Row": self.source_row,
            "_Source_Tax_Year": self.source_tax_year,
            "_Source_Pay_Frequency": self.pay_frequency_code,
        }


@dataclass
class ReferenceFileManifest:
    file_name: str
    byte_size: int
    sha256: str
    columns: list[str]
    physical_rows: int = 0
    usable_rows: int = 0
    padded_rows: int = 0
    invalid_rows: int = 0
    # Delta identity when the part came from the lakehouse rather than a file.
    lineage: dict[str, Any] | None = None


@dataclass
class ReferenceSourceControls:
    physical_rows: int = 0
    usable_rows: int = 0
    padded_rows: int = 0
    invalid_rows: int = 0
    zero_hour_rows: int = 0
    negative_hour_rows: int = 0
    negative_wage_rows: int = 0
    duplicate_groups: int = 0
    duplicate_group_rows: int = 0
    pay_date_before_period_end_rows: int = 0
    post_fiscal_year_paycheck_rows: int = 0
    distinct_employees: int = 0
    distinct_units: int = 0
    distinct_feins: int = 0
    earliest_period_start: str | None = None
    latest_period_end: str | None = None
    earliest_pay_date: str | None = None
    latest_pay_date: str | None = None


@dataclass
class ReferenceSourceSnapshot:
    assumption_set_id: str
    assumption_set_sha256: str
    files: list[ReferenceFileManifest]
    controls: ReferenceSourceControls
    rows: list[ReferencePayrollRow] = field(repr=False)
    exceptions: list[dict[str, Any]] = field(default_factory=list, repr=False)
    # Which adapter produced this. A viewer must never have to guess whether the
    # certified figures came from the reconciliation CSVs or from the lakehouse.
    source_kind: str = "csv"

    def manifest_dict(self) -> dict[str, Any]:
        """Return the safe aggregate manifest; never include source identifiers."""
        return {
            "assumption_set_id": self.assumption_set_id,
            "assumption_set_sha256": self.assumption_set_sha256,
            "source_kind": self.source_kind,
            "files": [asdict(file) for file in self.files],
            "controls": asdict(self.controls),
            "exception_counts": dict(Counter(item["type"] for item in self.exceptions)),
        }


class TccPayrollAdapter:
    """Read an ordered TCC chunk set with source lineage and aggregate controls."""

    def __init__(
        self,
        source_dir: Path = _DEFAULT_SOURCE_DIR,
        assumption_path: Path = _DEFAULT_ASSUMPTIONS,
    ) -> None:
        self.source_dir = Path(source_dir)
        self.assumption_path = Path(assumption_path)
        self.assumption_set = load_assumption_set(self.assumption_path)
        ordered = self.assumption_set["assumptions"]["BA-08"]["config"]["ordered_files"]
        self.paths = [self.source_dir / file_name for file_name in ordered]

    def rows(self) -> Iterator[dict[str, Any]]:
        """Yield mapped engine rows. Prefer ``scan`` when controls are required."""
        for row in self.scan().rows:
            yield row.to_engine_dict()

    def scan(self) -> ReferenceSourceSnapshot:
        missing = [path.name for path in self.paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Reference Dataset chunks not found: {', '.join(missing)}")

        rows: list[ReferencePayrollRow] = []
        manifests: list[ReferenceFileManifest] = []
        exceptions: list[dict[str, Any]] = []
        employees: set[str] = set()
        units: set[str] = set()
        feins: set[str] = set()
        duplicate_counts: Counter[tuple[str, str, str, date, date, date, str]] = Counter()
        earliest_period_start: date | None = None
        latest_period_end: date | None = None
        earliest_pay_date: date | None = None
        latest_pay_date: date | None = None

        assumptions = self.assumption_set["assumptions"]
        fiscal_end = date.fromisoformat(assumptions["BA-01"]["config"]["fiscal_year_end"])
        controls = ReferenceSourceControls()

        for path in self.paths:
            with path.open(newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                columns = list(reader.fieldnames or [])
                if columns != list(TCC_COLUMNS):
                    raise ValueError(f"{path.name} has unexpected columns")
                manifest = ReferenceFileManifest(
                    file_name=path.name,
                    byte_size=path.stat().st_size,
                    sha256=_sha256(path),
                    columns=columns,
                )
                for source_row, raw in enumerate(reader, start=2):
                    manifest.physical_rows += 1
                    controls.physical_rows += 1
                    normalized = {key: str(raw.get(key, "") or "").strip() for key in TCC_COLUMNS}
                    if not any(normalized.values()):
                        manifest.padded_rows += 1
                        controls.padded_rows += 1
                        continue
                    missing_values = [key for key in _REQUIRED_VALUES if not normalized[key]]
                    if missing_values:
                        manifest.invalid_rows += 1
                        controls.invalid_rows += 1
                        exceptions.append({
                            "type": "missing_required_value",
                            "source_file": path.name,
                            "source_row": source_row,
                            "fields": missing_values,
                        })
                        continue
                    try:
                        row = ReferencePayrollRow(
                            source_file=path.name,
                            source_row=source_row,
                            source_tax_year=int(normalized["Tax Year"]),
                            employee_id=normalized["TCCEmployeeId"],
                            job_title=normalized["JobTitle"],
                            unit_id=normalized["TCCUnitId"],
                            pay_period_start=_parse_date(normalized["PayPeriodStart"]),
                            pay_period_end=_parse_date(normalized["PayPeriodEnd"]),
                            pay_date=_parse_date(normalized["PaycheckDate"]),
                            pay_frequency_code=normalized["PayFrequency"],
                            fein=normalized["FEIN"],
                            hours=_parse_decimal(normalized["Hours"]),
                            wages=_parse_decimal(normalized["Wages"]),
                        )
                    except (TypeError, ValueError) as exc:
                        manifest.invalid_rows += 1
                        controls.invalid_rows += 1
                        exceptions.append({
                            "type": "invalid_value",
                            "source_file": path.name,
                            "source_row": source_row,
                            "reason": type(exc).__name__,
                        })
                        continue

                    manifest.usable_rows += 1
                    controls.usable_rows += 1
                    rows.append(row)
                    employees.add(row.employee_id)
                    units.add(row.unit_id)
                    feins.add(row.fein)
                    duplicate_counts[row.collapse_key()] += 1
                    controls.zero_hour_rows += row.hours == 0
                    controls.negative_hour_rows += row.hours < 0
                    controls.negative_wage_rows += row.wages < 0
                    controls.pay_date_before_period_end_rows += row.pay_date < row.pay_period_end
                    controls.post_fiscal_year_paycheck_rows += row.pay_date > fiscal_end
                    earliest_period_start = min(earliest_period_start or row.pay_period_start, row.pay_period_start)
                    latest_period_end = max(latest_period_end or row.pay_period_end, row.pay_period_end)
                    earliest_pay_date = min(earliest_pay_date or row.pay_date, row.pay_date)
                    latest_pay_date = max(latest_pay_date or row.pay_date, row.pay_date)
                manifests.append(manifest)

        duplicate_sizes = [count for count in duplicate_counts.values() if count > 1]
        controls.duplicate_groups = len(duplicate_sizes)
        controls.duplicate_group_rows = sum(duplicate_sizes)
        controls.distinct_employees = len(employees)
        controls.distinct_units = len(units)
        controls.distinct_feins = len(feins)
        controls.earliest_period_start = earliest_period_start.isoformat() if earliest_period_start else None
        controls.latest_period_end = latest_period_end.isoformat() if latest_period_end else None
        controls.earliest_pay_date = earliest_pay_date.isoformat() if earliest_pay_date else None
        controls.latest_pay_date = latest_pay_date.isoformat() if latest_pay_date else None

        return ReferenceSourceSnapshot(
            assumption_set_id=self.assumption_set["assumption_set_id"],
            assumption_set_sha256=_sha256(self.assumption_path),
            files=manifests,
            controls=controls,
            rows=rows,
            exceptions=exceptions,
            source_kind="csv",
        )


def certified_figures() -> dict[str, int]:
    """The reconciled result the reference dataset must reproduce.

    Read from configuration rather than hard-coded here because the runtime
    equivalence gate is production code and may not import from `tests/`.
    `tests/test_certified_figures_contract.py` asserts this file still agrees
    with the literals in `tests/certified.py`.
    """
    payload = json.loads(_CERTIFIED_FIGURES.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in payload["figures"].items()}


class CertifiedFiguresMismatch(RuntimeError):
    """A source claimed to be the reference dataset but did not reproduce it."""


class LakehousePayrollAdapter:
    """Read the reference client from the Fabric lakehouse in the partner's source shape.

    Produces the same `ReferenceSourceSnapshot` as `TccPayrollAdapter`, sourced
    from Delta rather than from the partner's four CSVs. It rides on
    `source_to_bcs_rows`, which `tests/test_source_roundtrip.py` certifies lossless
    — so this is not a second implementation of the read, it is the same
    projection from a different place.

    Two things differ from the CSV path and both are deliberate:

    - **Lineage is a Delta version, not a file hash.** `sha256` is computed over
      the ordered projected rows so the manifest is still a reproducibility
      claim; the table URI and version say where it came from.
    - **`Worksite_ID` carries its state prefix** (`GA_...`), because the
      pipeline filters by that prefix. Unit identity is relabelled, never
      re-partitioned, so the unit COUNT and every figure derived from it hold.
    """

    def __init__(
        self,
        account_id: int | None = None,
        assumption_path: Path = _DEFAULT_ASSUMPTIONS,
        reader: Any | None = None,
    ) -> None:
        from data.source.from_reference import REFERENCE_ACCOUNT_ID

        self.account_id = REFERENCE_ACCOUNT_ID if account_id is None else int(account_id)
        self.assumption_path = Path(assumption_path)
        self.assumption_set = load_assumption_set(self.assumption_path)
        self._reader = reader

    def reader(self) -> Any:
        if self._reader is None:
            from data.source.from_fabric import FabricLakehouseReader

            self._reader = FabricLakehouseReader()
        return self._reader

    def rows(self) -> Iterator[dict[str, Any]]:
        for row in self.scan().rows:
            yield row.to_engine_dict()

    def scan(self) -> ReferenceSourceSnapshot:
        from data.source.to_bcs import source_to_bcs_rows

        reader = self.reader()
        if not reader.is_configured():
            raise FileNotFoundError(
                "Fabric is not configured: set FABRIC_WORKSPACE and FABRIC_LAKEHOUSE. "
                "Reported separately from a missing account because the two send you "
                "looking in completely different places."
            )
        dataset = reader.for_account(self.account_id)
        if dataset is None:
            raise FileNotFoundError(
                f"account {self.account_id} not found in the Fabric `{reader.schema}` "
                f"schema. Check the account id and that the capacity is running."
            )

        assumptions = self.assumption_set["assumptions"]
        fiscal_end = date.fromisoformat(assumptions["BA-01"]["config"]["fiscal_year_end"])
        controls = ReferenceSourceControls()
        exceptions: list[dict[str, Any]] = []
        rows: list[ReferencePayrollRow] = []
        employees: set[str] = set()
        units: set[str] = set()
        feins: set[str] = set()
        duplicate_counts: Counter[tuple[str, str, str, date, date, date, str]] = Counter()
        earliest_period_start: date | None = None
        latest_period_end: date | None = None
        earliest_pay_date: date | None = None
        latest_pay_date: date | None = None

        table = f"{reader.schema}.Payroll"
        controls.physical_rows = len(dataset.payroll)

        projected = source_to_bcs_rows(dataset)
        # A row the projection dropped for having no period span never reaches
        # `projected`, so it is counted here rather than silently lost.
        controls.invalid_rows = controls.physical_rows - len(projected)
        for _ in range(controls.invalid_rows):
            exceptions.append({"type": "missing_required_value", "source_file": table})

        digest = hashlib.sha256()
        for record in projected:
            if not record.get("Pay_Date"):
                controls.invalid_rows += 1
                exceptions.append({
                    "type": "missing_required_value",
                    "source_file": table,
                    "source_row": record.get("_Source_Payroll_Id"),
                    "fields": ["Pay_Date"],
                })
                continue

            row = ReferencePayrollRow(
                source_file=table,
                source_row=int(record.get("_Source_Payroll_Id") or 0),
                source_tax_year=int(record["Tax_Year"]),
                employee_id=str(record["Employee_ID"]),
                job_title=str(record.get("Job_Title") or ""),
                unit_id=str(record["Worksite_ID"]),
                pay_period_start=date.fromisoformat(record["Pay_Period_Start"]),
                pay_period_end=date.fromisoformat(record["Pay_Period_End"]),
                pay_date=date.fromisoformat(record["Pay_Date"]),
                pay_frequency_code=str(record.get("Pay_Frequency") or ""),
                fein=str(record.get("Entity_FEIN") or ""),
                hours=Decimal(str(record.get("Hours_Worked") or 0)),
                wages=Decimal(str(record.get("Gross_Wages") or 0)),
            )

            digest.update(repr(row.collapse_key()).encode())
            digest.update(f"|{row.hours}|{row.wages}".encode())

            controls.usable_rows += 1
            rows.append(row)
            employees.add(row.employee_id)
            units.add(row.unit_id)
            feins.add(row.fein)
            duplicate_counts[row.collapse_key()] += 1
            controls.zero_hour_rows += row.hours == 0
            controls.negative_hour_rows += row.hours < 0
            controls.negative_wage_rows += row.wages < 0
            controls.pay_date_before_period_end_rows += row.pay_date < row.pay_period_end
            controls.post_fiscal_year_paycheck_rows += row.pay_date > fiscal_end
            earliest_period_start = min(earliest_period_start or row.pay_period_start, row.pay_period_start)
            latest_period_end = max(latest_period_end or row.pay_period_end, row.pay_period_end)
            earliest_pay_date = min(earliest_pay_date or row.pay_date, row.pay_date)
            latest_pay_date = max(latest_pay_date or row.pay_date, row.pay_date)

        duplicate_sizes = [count for count in duplicate_counts.values() if count > 1]
        controls.duplicate_groups = len(duplicate_sizes)
        controls.duplicate_group_rows = sum(duplicate_sizes)
        controls.distinct_employees = len(employees)
        controls.distinct_units = len(units)
        controls.distinct_feins = len(feins)
        controls.earliest_period_start = earliest_period_start.isoformat() if earliest_period_start else None
        controls.latest_period_end = latest_period_end.isoformat() if latest_period_end else None
        controls.earliest_pay_date = earliest_pay_date.isoformat() if earliest_pay_date else None
        controls.latest_pay_date = latest_pay_date.isoformat() if latest_pay_date else None

        manifest = ReferenceFileManifest(
            file_name=table,
            byte_size=0,
            sha256="sha256:" + digest.hexdigest(),
            columns=sorted(projected[0]) if projected else [],
            physical_rows=controls.physical_rows,
            usable_rows=controls.usable_rows,
            invalid_rows=controls.invalid_rows,
            lineage=reader.table_lineage("Payroll"),
        )
        if manifest.lineage:
            manifest.byte_size = int(manifest.lineage.get("bytes") or 0)

        return ReferenceSourceSnapshot(
            assumption_set_id=self.assumption_set["assumption_set_id"],
            assumption_set_sha256=_sha256(self.assumption_path),
            files=[manifest],
            controls=controls,
            rows=rows,
            exceptions=exceptions,
            source_kind="lakehouse",
        )
