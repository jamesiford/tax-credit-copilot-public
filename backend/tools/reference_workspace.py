"""Cached Reference Dataset workspace service for the primary local portal."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any

from .reference_compare import compare_access_bundle, load_access_bundle
from .reference_onezero import ReferenceOneZeroRun, run_reference_onezero
from .reference_runner import write_private_report
from .reference_source import (
    CertifiedFiguresMismatch,
    LakehousePayrollAdapter,
    ReferencePayrollRow,
    ReferenceSourceSnapshot,
    TccPayrollAdapter,
    certified_figures,
    load_assumption_set_for_id,
    statutory_floors_for,
)
from .reference_step1 import ReferenceStep1Run, run_reference_step1

from data.source.from_reference import REFERENCE_ACCOUNT_ID, REFERENCE_ACCOUNT_NAME
from tools.tokens import record_token

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent

# Methodology sets are CONFIGURATION, not documentation. They were read from
# docs/data/ until a docs reorganisation moved them and the engine stopped
# booting - production code should never depend on the layout of a docs folder.
# They now live beside the rule packs they are versioned alongside.
_METHODOLOGY = Path(__file__).resolve().parent.parent / "rules" / "methodology"
_DEFAULT_SOURCE = _BACKEND_ROOT / "data" / "payroll"
_DEFAULT_OUTPUT = _BACKEND_ROOT / "data" / "reference_output"
_STEP1_ASSUMPTIONS = _METHODOLOGY / "reference-dataset-assumptions.v8.json"
_ONEZERO_ASSUMPTIONS = _METHODOLOGY / "reference-onezero-assumptions.v7.json"
# Superseded step-1 sets, read as DOCUMENTS for the history timeline only. They
# are no longer executable (see RETIRED_ASSUMPTION_SETS in reference_source).
_STEP1_ASSUMPTIONS_V1 = _METHODOLOGY / "reference-dataset-assumptions.v1.json"
_ONEZERO_ASSUMPTIONS_V1 = _METHODOLOGY / "reference-onezero-assumptions.v1.json"
_STEP1_ASSUMPTIONS_V2 = _METHODOLOGY / "reference-dataset-assumptions.v2.json"
_ONEZERO_ASSUMPTIONS_V2 = _METHODOLOGY / "reference-onezero-assumptions.v2.json"
_STEP1_ASSUMPTIONS_V3 = _METHODOLOGY / "reference-dataset-assumptions.v3.json"
_ONEZERO_ASSUMPTIONS_V3 = _METHODOLOGY / "reference-onezero-assumptions.v3.json"
_STEP1_ASSUMPTIONS_V4 = _METHODOLOGY / "reference-dataset-assumptions.v4.json"
_STEP1_ASSUMPTIONS_V5 = _METHODOLOGY / "reference-dataset-assumptions.v5.json"
_STEP1_ASSUMPTIONS_V6 = _METHODOLOGY / "reference-dataset-assumptions.v6.json"
_STEP1_ASSUMPTIONS_V7 = _METHODOLOGY / "reference-dataset-assumptions.v7.json"
_ONEZERO_ASSUMPTIONS_V4 = _METHODOLOGY / "reference-onezero-assumptions.v4.json"
_ONEZERO_ASSUMPTIONS_V5 = _METHODOLOGY / "reference-onezero-assumptions.v5.json"
_ONEZERO_ASSUMPTIONS_V6 = _METHODOLOGY / "reference-onezero-assumptions.v6.json"
_METHODOLOGY_WORKBOOK = _REPO_ROOT / "stakeholder-docs" / "GA JTC One Zero Methodology Overview.xlsx"
_HISTORICAL_WAGES_PDF = _REPO_ROOT / "stakeholder-docs" / "JTCHistoricalWages_Jul 2025.pdf"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _active_floors():
    """Statutory floors for the active assumption set, resolved from its year pack."""
    return statutory_floors_for(_read_json(_STEP1_ASSUMPTIONS))


def _fiscal_identity(state: ReferenceWorkspaceState) -> dict[str, Any]:
    """Which window this run measured, where the window came from, and how the
    programme labels it.

    The window here is BA-01's — the certified run takes it explicitly and never
    derives one. Resolving the client's own rule alongside it and reporting
    whether the two agree is what turns "we assumed" into "we checked".
    """
    from domain.calculation.fiscal import window_from_client_rules
    from infrastructure.payroll.fiscal_source import client_fiscal_window
    from tools.credit_math import resolve_tax_year_convention

    assumptions = _read_json(_STEP1_ASSUMPTIONS)
    program = str(assumptions.get("program_code") or "GA_JTC")
    tax_year = int(assumptions.get("tax_year") or 0)
    config = assumptions["assumptions"]["BA-01"]["config"]
    begin = date.fromisoformat(config["fiscal_year_begin"])
    end = date.fromisoformat(config["fiscal_year_end"])

    convention = resolve_tax_year_convention(program, tax_year)
    applied = window_from_client_rules(
        begin, end, convention["label"],
        note=f"Configured window, BA-01 of {assumptions['assumption_set_id']}.",
    )

    account_id = REFERENCE_ACCOUNT_ID if state.snapshot.source_kind == "lakehouse" else None
    from_source = client_fiscal_window(account_id, tax_year, convention["label"])

    return {
        "program_code": program,
        "applied": applied.as_dict(),
        "from_source_system": from_source.as_dict(),
        "agrees_with_source": (
            from_source.basis == "client_rules"
            and (from_source.begin, from_source.end) == (begin, end)
        ),
        "convention": convention,
        "tax_year_applied": applied.tax_year,
    }


@dataclass
class ReferenceWorkspaceState:
    fingerprint: str
    created_at: str
    code_commit: str
    snapshot: ReferenceSourceSnapshot = field(repr=False)
    step1: ReferenceStep1Run = field(repr=False)
    onezero: ReferenceOneZeroRun = field(repr=False)
    comparison: dict[str, Any] | None = field(default=None, repr=False)
    comparison_source: str | None = None
    token_to_employee: dict[str, str] = field(default_factory=dict, repr=False)
    employee_to_token: dict[str, str] = field(default_factory=dict, repr=False)
    equivalence: dict[str, Any] | None = field(default=None, repr=False)


def _observed_figures(step1: ReferenceStep1Run) -> dict[str, int]:
    return {
        "employees_evaluated": len(step1.common_totals),
        "min_max_eligible": sum(1 for row in step1.min_max.values() if row.eligible),
        "pay_period_eligible": sum(1 for row in step1.pay_period.values() if row.eligible),
    }


class ReferenceWorkspaceService:
    """Build and cache one sealed Reference run over the immutable local source."""

    def __init__(
        self,
        source_dir: Path = _DEFAULT_SOURCE,
        output_dir: Path = _DEFAULT_OUTPUT,
        access_output_path: Path | None = None,
        source_kind: str | None = None,
    ) -> None:
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        # The sealed run used to read the four CSVs whatever `DATA_SOURCE` said,
        # which left the same client resolving from two different sources on one
        # screen. Under `lakehouse` it now comes out of the lakehouse like every
        # other view, and the equivalence gate below is what makes that safe.
        from tools.fabric_source import resolve_data_source_alias

        raw_source_kind = (source_kind or os.getenv("DATA_SOURCE") or "csv").strip().lower()
        self.source_kind = resolve_data_source_alias(raw_source_kind)
        configured_access = access_output_path or (
            Path(os.environ["REFERENCE_ACCESS_OUTPUT_PATH"])
            if os.getenv("REFERENCE_ACCESS_OUTPUT_PATH")
            else None
        )
        self.access_output_path = configured_access
        self._state: ReferenceWorkspaceState | None = None
        self._lock = RLock()

    def _adapter(self):
        if self.source_kind == "lakehouse":
            return LakehousePayrollAdapter()
        return TccPayrollAdapter(source_dir=self.source_dir)

    def _methodology_fingerprint(self) -> list[list[Any]]:
        # The two assumption-set JSON files are tracked and committed - their
        # absence is a corrupted checkout and stays a loud failure. The
        # methodology workbook and historical wages PDF were removed from the
        # repository (B05, stakeholder-docs/) and are never coming back; a
        # missing one is a documented, stable fact rather than an error, or
        # this (live, runtime) sealed workspace would 500 on every call.
        files = [_STEP1_ASSUMPTIONS, _ONEZERO_ASSUMPTIONS]
        missing = [path.name for path in files if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Reference workspace inputs missing: {', '.join(missing)}")
        fingerprint = [
            [str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns]
            for path in files
        ]
        for path in (_METHODOLOGY_WORKBOOK, _HISTORICAL_WAGES_PDF):
            if path.exists():
                fingerprint.append([str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns])
            else:
                fingerprint.append([path.name, None, None])
        return fingerprint

    def _fingerprint(self) -> str:
        payload = self._methodology_fingerprint()
        if self.source_kind == "lakehouse":
            # A lakehouse has no mtime to watch, so the Delta version is what
            # tells us the source moved.
            from data.source.from_fabric import FabricLakehouseReader

            reader = FabricLakehouseReader()
            lineage = reader.table_lineage("Payroll") or {}
            payload.append([f"{reader.schema}.Payroll", lineage.get("version"), lineage.get("files")])
        else:
            files = [
                self.source_dir / name
                for name in ("One.csv", "Two.csv", "Three.csv", "Four.csv")
            ]
            missing = [path.name for path in files if not path.exists()]
            if missing:
                raise FileNotFoundError(f"Reference workspace inputs missing: {', '.join(missing)}")
            payload = [
                [str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns]
                for path in files
            ] + payload
        return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()

    def get(self, *, force: bool = False) -> ReferenceWorkspaceState:
        if force and self.source_kind == "lakehouse":
            # A forced refresh must actually re-read the lakehouse; otherwise it
            # rebuilds from the process cache and reports the same Delta version
            # however many times someone presses it.
            from data.source.from_fabric import clear_cache

            clear_cache()
        fingerprint = self._fingerprint()
        with self._lock:
            if not force and self._state is not None and self._state.fingerprint == fingerprint:
                return self._state
            snapshot = self._adapter().scan()
            step1 = run_reference_step1(snapshot)
            equivalence = self._check_certified(snapshot, step1)
            onezero = run_reference_onezero(step1)
            comparison = None
            comparison_source = None
            if self.access_output_path and self.access_output_path.exists():
                comparison = compare_access_bundle(
                    load_access_bundle(self.access_output_path),
                    step1,
                    onezero,
                )
                comparison_source = str(self.access_output_path)
            employees = sorted(step1.common_totals)
            # Derived the same way as `application/queries/get_eligibility`, so a
            # token minted by the per-client read resolves here. Keying it to the
            # calculation_id instead made the drill 404 on every row the
            # per-client views render, which is where the drill is opened from.
            floors = _active_floors()
            employee_to_token = {
                employee_id: record_token(
                    REFERENCE_ACCOUNT_ID,
                    floors.program_code,
                    floors.tax_year,
                    employee_id,
                )
                for employee_id in employees
            }
            state = ReferenceWorkspaceState(
                fingerprint=fingerprint,
                created_at=datetime.now(timezone.utc).isoformat(),
                code_commit=_git_commit(),
                snapshot=snapshot,
                step1=step1,
                onezero=onezero,
                comparison=comparison,
                comparison_source=comparison_source,
                employee_to_token=employee_to_token,
                token_to_employee={token: employee for employee, token in employee_to_token.items()},
                equivalence=equivalence,
            )
            write_private_report(step1, onezero, snapshot.manifest_dict(), self.output_dir)
            self._state = state
            return state

    @staticmethod
    def _check_certified(
        snapshot: ReferenceSourceSnapshot, step1: ReferenceStep1Run
    ) -> dict[str, Any]:
        """Refuse to serve a source that does not reproduce the certified result.

        The point of reading the reference client from the lakehouse is the claim
        that it is the SAME client — so the claim has to be tested at the point
        it is made, not only in CI. A source that produces different figures
        under the certified banner is worse than no source at all.
        """
        expected = certified_figures()
        observed = _observed_figures(step1)
        matches = observed == expected
        if not matches and snapshot.source_kind != "csv":
            raise CertifiedFiguresMismatch(
                f"{snapshot.source_kind} source did not reproduce the certified reference "
                f"result: expected {expected}, got {observed}. Refusing to serve it as "
                f"the certified run."
            )
        return {
            "source_kind": snapshot.source_kind,
            "expected": expected,
            "observed": observed,
            "matches": matches,
        }

    @staticmethod
    def _selection_reason(
        row: ReferencePayrollRow,
        assumptions: dict[str, Any],
    ) -> str:
        fiscal_config = assumptions["BA-01"]["config"]
        selection_config = assumptions["BA-02"]["config"]
        fiscal_begin = date.fromisoformat(fiscal_config["fiscal_year_begin"])
        fiscal_end = date.fromisoformat(fiscal_config["fiscal_year_end"])
        if row.pay_date < fiscal_begin:
            return "excluded_pay_date_before_fy"
        if row.pay_date > fiscal_end:
            return "excluded_pay_date_after_fy"
        if (
            row.pay_period_end > fiscal_end
            and selection_config.get("pay_period_end_must_not_exceed_fiscal_year_end", True)
        ):
            return "excluded_ppe_after_fy"
        if (
            row.pay_period_end < fiscal_begin
            and not selection_config.get("include_prior_fy_ppe_paid_in_fiscal_year", False)
        ):
            return "excluded_ppe_before_fy"
        if row.pay_period_end > fiscal_end:
            return "included_ppe_after_fy_end"
        if row.pay_period_end < fiscal_begin:
            return "included_prior_ppe_paid_in_fy"
        if row.pay_period_start < fiscal_begin <= row.pay_period_end:
            return "included_transcends_fy_start"
        return "included"

    @staticmethod
    def _run_ref(state: ReferenceWorkspaceState) -> dict[str, str]:
        return {
            "step1_calculation_id": state.step1.calculation_id,
            "onezero_calculation_id": state.onezero.calculation_id,
            "source_manifest_sha256": state.step1.source_manifest_sha256,
        }

    def run_ref(self) -> dict[str, str]:
        return self._run_ref(self.get())

    def summary(self) -> dict[str, Any]:
        state = self.get()
        step1 = state.step1.summary_dict()
        onezero = state.onezero.summary_dict()
        manifest = state.snapshot.manifest_dict()
        threshold_config = _active_floors().as_dict()
        return {
            "workspace": {
                "id": "reference-dataset-client",
                "name": "Reference Dataset Client",
                # The account AND year the sealed run describes. The shell needs
                # both to warn when a sealed view is on screen under a different
                # selection — a year mismatch was previously silent, which is the
                # worse of the two because nothing on screen looked wrong.
                "account_id": REFERENCE_ACCOUNT_ID,
                "client_name": REFERENCE_ACCOUNT_NAME,
                "tax_year": threshold_config["tax_year"],
                "program_code": threshold_config["program_code"],
                "single_workspace": True,
                "private_data": True,
            },
            "run": {
                "created_at": state.created_at,
                "code_commit": state.code_commit,
                "step1_calculation_id": state.step1.calculation_id,
                "onezero_calculation_id": state.onezero.calculation_id,
                "source_manifest_sha256": state.step1.source_manifest_sha256,
                "step1_assumption_set_id": state.step1.assumption_set_id,
                "step1_assumption_set_sha256": state.step1.assumption_set_sha256,
                "onezero_assumption_set_id": state.onezero.onezero_assumption_set_id,
                "onezero_assumption_set_sha256": state.onezero.onezero_assumption_set_sha256,
                "methodology_workbook_sha256": state.onezero.methodology_workbook_sha256,
                "historical_wages_pdf_sha256": state.onezero.historical_wages_pdf_sha256,
                "source_kind": state.snapshot.source_kind,
            },
            "equivalence": state.equivalence,
            "fiscal": _fiscal_identity(state),
            "source": manifest,
            "selection": step1["selection_counts"],
            "boundary": step1["boundary_controls"],
            "collapse": step1["collapse_counts"],
            "eligibility": {
                "employees_with_totals": step1["employees_with_totals"],
                "min_max": step1["min_max"],
                "pay_period": step1["pay_period"],
                "reconciliation": step1["eligibility_reconciliation"],
                "pay_period_controls": step1["pay_period_controls"],
                "denominator_invariant": step1["denominator_invariant"],
                "thresholds": {
                    "minimum_average_weekly_hours": threshold_config["minimum_average_weekly_hours"],
                    "minimum_average_weekly_wages_usd": threshold_config["minimum_average_weekly_wages_usd"],
                    "source_tax_year": threshold_config["source_tax_year"],
                    "dol_report_year": threshold_config["dol_report_year"],
                    "lowest_wage_county": threshold_config["lowest_wage_county"],
                    "program_code": threshold_config["program_code"],
                    "statutory_source": threshold_config["source"],
                    "prototype_verify": threshold_config["prototype_verify"],
                },
            },
            "onezero": {
                "min_max": onezero["min_max"],
                "pay_period": onezero["pay_period"],
            },
            "comparison": self.comparison_summary(state),
            "exceptions": {
                "step1": step1["exceptions"],
                "onezero": onezero["exceptions"],
            },
            "stages": [
                {"id": "source", "label": "Source & normalize", "status": "complete"},
                {"id": "eligibility", "label": "Eligibility", "status": "complete"},
                {"id": "onezero", "label": "One/Zero", "status": "review_required"},
                {
                    "id": "compare",
                    "label": "Compare to Access",
                    "status": "reconciled" if state.comparison and state.comparison["reconciled"]
                    else "discrepancies" if state.comparison else "awaiting_outputs",
                },
            ],
        }

    def source_rows(self, *, query: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        state = self.get()
        assumptions = load_assumption_set_for_id(state.step1.assumption_set_id)["assumptions"]
        needle = query.strip().lower()
        rows = state.snapshot.rows
        if needle:
            rows = [
                row for row in rows
                if needle in " ".join((
                    row.employee_id,
                    row.unit_id,
                    row.fein,
                    row.job_title,
                    row.pay_period_start.isoformat(),
                    row.pay_period_end.isoformat(),
                    row.pay_date.isoformat(),
                )).lower()
            ]
        rows = sorted(rows, key=lambda row: (row.source_file, row.source_row))
        total = len(rows)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        page = rows[offset:offset + limit]
        return {
            "run": self._run_ref(state),
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": [
                {
                    "record_token": state.employee_to_token[row.employee_id],
                    "employee_id": row.employee_id,
                    "job_title": row.job_title,
                    "unit_id": row.unit_id,
                    "fein": row.fein,
                    "pay_period_start": row.pay_period_start.isoformat(),
                    "pay_period_end": row.pay_period_end.isoformat(),
                    "pay_date": row.pay_date.isoformat(),
                    "pay_frequency_code": row.pay_frequency_code,
                    "hours": str(row.hours),
                    "wages": str(row.wages),
                    "source_file": row.source_file,
                    "source_row": row.source_row,
                    "selection_decision": self._selection_reason(row, assumptions),
                }
                for row in page
            ],
        }

    def eligibility_rows(
        self,
        *,
        query: str = "",
        status: str = "all",
        proximity: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        state = self.get()
        needle = query.strip().lower()
        floors = _active_floors()
        hours_floor = Decimal(str(floors.min_weekly_hours))
        wages_floor = Decimal(str(floors.min_weekly_wages))
        rows: list[dict[str, Any]] = []
        for employee_id, totals in state.step1.common_totals.items():
            min_max = state.step1.min_max[employee_id]
            pay_period = state.step1.pay_period[employee_id]
            if min_max.eligible and pay_period.eligible:
                method_status = "both"
            elif min_max.eligible:
                method_status = "min_max_only"
            elif pay_period.eligible:
                method_status = "pay_period_only"
            else:
                method_status = "neither"
            if status != "all" and method_status != status:
                continue
            if needle and needle not in employee_id.lower():
                continue
            near_floor = any(
                abs(value - floor) <= floor * Decimal("0.05")
                for value, floor in (
                    (min_max.rounded_avg_weekly_hours, hours_floor),
                    (min_max.rounded_avg_weekly_wages, wages_floor),
                    (pay_period.rounded_avg_weekly_hours, hours_floor),
                    (pay_period.rounded_avg_weekly_wages, wages_floor),
                )
            )
            if proximity == "near_floor" and not near_floor:
                continue
            rows.append({
                "record_token": state.employee_to_token[employee_id],
                "employee_id": employee_id,
                "status": method_status,
                "near_floor": near_floor,
                "totals": {"hours": str(totals.total_hours), "wages": str(totals.total_wages)},
                "min_max": {
                    "weeks": str(min_max.denominator_weeks),
                    "avg_hours": str(min_max.rounded_avg_weekly_hours),
                    "avg_wages": str(min_max.rounded_avg_weekly_wages),
                    "passed_hours": min_max.passed_hours,
                    "passed_wages": min_max.passed_wages,
                    "eligible": min_max.eligible,
                },
                "pay_period": {
                    "weeks": str(pay_period.denominator_weeks),
                    "avg_hours": str(pay_period.rounded_avg_weekly_hours),
                    "avg_wages": str(pay_period.rounded_avg_weekly_wages),
                    "passed_hours": pay_period.passed_hours,
                    "passed_wages": pay_period.passed_wages,
                    "eligible": pay_period.eligible,
                },
            })
        rows.sort(key=lambda item: (item["status"], item["employee_id"]))
        total = len(rows)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        return {
            "run": self._run_ref(state),
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": rows[offset:offset + limit],
        }

    def employee(self, record_token: str) -> dict[str, Any] | None:
        state = self.get()
        assumptions = load_assumption_set_for_id(state.step1.assumption_set_id)["assumptions"]
        employee_id = state.token_to_employee.get(record_token)
        if not employee_id:
            return None
        raw_rows = sorted(
            [row for row in state.snapshot.rows if row.employee_id == employee_id],
            key=lambda row: (row.pay_period_start, row.source_file, row.source_row),
        )
        return {
            "record_token": record_token,
            "employee_id": employee_id,
            "run": {
                **self._run_ref(state),
                "step1_assumption_set_id": state.step1.assumption_set_id,
                "step1_assumption_set_sha256": state.step1.assumption_set_sha256,
                "onezero_assumption_set_id": state.onezero.onezero_assumption_set_id,
                "onezero_assumption_set_sha256": state.onezero.onezero_assumption_set_sha256,
                "methodology_workbook_sha256": state.onezero.methodology_workbook_sha256,
                "historical_wages_pdf_sha256": state.onezero.historical_wages_pdf_sha256,
                "code_commit": state.code_commit,
                "created_at": state.created_at,
            },
            "thresholds": {
                "minimum_average_weekly_hours": str(_active_floors().min_weekly_hours),
                "minimum_average_weekly_wages_usd": str(_active_floors().min_weekly_wages),
            },
            "exceptions": {
                "step1": list(state.step1.exceptions),
                "onezero": list(state.onezero.exceptions),
            },
            "boundary": dict(state.step1.boundary_controls),
            "raw_source_rows": [
                {
                    "source_file": row.source_file,
                    "source_row": row.source_row,
                    "job_title": row.job_title,
                    "unit_id": row.unit_id,
                    "fein": row.fein,
                    "pay_period_start": row.pay_period_start.isoformat(),
                    "pay_period_end": row.pay_period_end.isoformat(),
                    "pay_date": row.pay_date.isoformat(),
                    "pay_frequency_code": row.pay_frequency_code,
                    "hours": str(row.hours),
                    "wages": str(row.wages),
                    "selection_decision": self._selection_reason(row, assumptions),
                }
                for row in raw_rows
            ],
            "step1": state.step1.employee_drill(employee_id),
            "onezero": state.onezero.employee_drill(employee_id),
            "access_differences": self._employee_access_differences(state, employee_id),
        }

    def onezero_summary(self, method: str) -> dict[str, Any]:
        state = self.get()
        result = state.onezero.min_max if method == "min_max" else state.onezero.pay_period
        return {
            **result.aggregate_dict(),
            "run": self._run_ref(state),
            "calculation_id": state.onezero.calculation_id,
            "assumption_set_id": state.onezero.onezero_assumption_set_id,
            "summary": [row.private_dict() for row in result.summary],
            "overlap_flags": [
                {
                    **flag,
                    "record_token": state.employee_to_token.get(flag["employee_id"]),
                }
                for flag in result.overlap_flags
            ],
        }

    def contributors(self, *, method: str, unit_id: str, fein: str, month_index: int) -> list[dict[str, Any]]:
        state = self.get()
        result = state.onezero.min_max if method == "min_max" else state.onezero.pay_period
        contributors: dict[str, dict[str, Any]] = {}
        for row in result.matrix:
            if row.unit_id != unit_id or row.fein != fein or not row.months[month_index]:
                continue
            contributors[row.employee_id] = {
                "record_token": state.employee_to_token[row.employee_id],
                "employee_id": row.employee_id,
                "counted": row.months[month_index],
                "segment_id": row.segment_id,
            }
        return [contributors[key] for key in sorted(contributors)]

    def calculation_walk(self) -> dict[str, Any]:
        state = self.get()
        def enrich_step(
            step: dict[str, Any],
            *,
            calculation_id: str,
            code_ref: str,
            config_hash: str,
        ) -> dict[str, Any]:
            return {
                **step,
                "calculation_id": calculation_id,
                "code_ref": f"{code_ref}@{state.code_commit}",
                "source_hash": state.step1.source_manifest_sha256,
                "config_hash": config_hash,
                "timestamp": state.created_at,
            }

        return {
            "run_context": {
                "workspace": "Reference Dataset Client",
                "created_at": state.created_at,
                "code_commit": state.code_commit,
                "source_manifest_sha256": state.step1.source_manifest_sha256,
                "step1_assumption_set_id": state.step1.assumption_set_id,
                "step1_assumption_set_sha256": state.step1.assumption_set_sha256,
                "onezero_assumption_set_id": state.onezero.onezero_assumption_set_id,
                "onezero_assumption_set_sha256": state.onezero.onezero_assumption_set_sha256,
                "methodology_workbook_sha256": state.onezero.methodology_workbook_sha256,
                "historical_wages_pdf_sha256": state.onezero.historical_wages_pdf_sha256,
            },
            "steps": [
                *[
                    enrich_step(
                        step.to_dict(),
                        calculation_id=state.step1.calculation_id,
                        code_ref="tools/reference_step1.py:run_reference_step1",
                        config_hash=state.step1.assumption_set_sha256,
                    )
                    for step in state.step1.steps
                ],
                *[
                    enrich_step(
                        step.to_dict(),
                        calculation_id=state.onezero.calculation_id,
                        code_ref="tools/reference_onezero.py:run_reference_onezero",
                        config_hash=state.onezero.onezero_assumption_set_sha256,
                    )
                    for step in state.onezero.steps
                ],
            ],
        }

    def assumptions(self) -> dict[str, Any]:
        state = self.get()
        return {
            "run": self._run_ref(state),
            "step1": {**_read_json(_STEP1_ASSUMPTIONS), "sha256": _file_sha256(_STEP1_ASSUMPTIONS)},
            "onezero": {**_read_json(_ONEZERO_ASSUMPTIONS), "sha256": _file_sha256(_ONEZERO_ASSUMPTIONS)},
            # The statutory floors the active set measures against. From v8 these
            # are NOT in BA-06 — they are resolved from the year pack [ADR-005] —
            # so the UI reads them here rather than out of the assumption body.
            "statutory": _active_floors().as_dict(),
            "history": {
                "step1": [
                    {
                        "assumption_set_id": _read_json(path)["assumption_set_id"],
                        "sha256": _file_sha256(path),
                        "status": _read_json(path)["status"],
                    }
                    for path in (
                        _STEP1_ASSUMPTIONS_V1,
                        _STEP1_ASSUMPTIONS_V2,
                        _STEP1_ASSUMPTIONS_V3,
                        _STEP1_ASSUMPTIONS_V4,
                        _STEP1_ASSUMPTIONS_V5,
                        _STEP1_ASSUMPTIONS_V6,
                        _STEP1_ASSUMPTIONS_V7,
                    )
                ],
                "onezero": [
                    {
                        "assumption_set_id": _read_json(path)["assumption_set_id"],
                        "sha256": _file_sha256(path),
                        "status": _read_json(path)["status"],
                    }
                    for path in (
                        _ONEZERO_ASSUMPTIONS_V1,
                        _ONEZERO_ASSUMPTIONS_V2,
                        _ONEZERO_ASSUMPTIONS_V3,
                        _ONEZERO_ASSUMPTIONS_V4,
                        _ONEZERO_ASSUMPTIONS_V5,
                        _ONEZERO_ASSUMPTIONS_V6,
                    )
                ],
            },
        }

    @staticmethod
    def comparison_summary(state: ReferenceWorkspaceState) -> dict[str, Any]:
        if state.comparison is None:
            return {
                "run": ReferenceWorkspaceService._run_ref(state),
                "status": "not_supplied",
                "message": "The partner's Access outputs have not been supplied.",
                "required_stages": [
                    "common_employee_totals",
                    "min_max_eligibility",
                    "pay_period_eligibility",
                    "min_max_onezero_summary",
                    "pay_period_onezero_summary",
                ],
            }
        return {
            "run": ReferenceWorkspaceService._run_ref(state),
            "status": "reconciled" if state.comparison["reconciled"] else "discrepancies",
            "source": Path(state.comparison_source).name if state.comparison_source else None,
            "stages_compared": state.comparison["stages_compared"],
            "first_divergent_stage": state.comparison["first_divergent_stage"],
            "reconciled": state.comparison["reconciled"],
            "stage_summaries": state.comparison["stage_summaries"],
        }

    def comparison_stage(self, stage_name: str) -> dict[str, Any] | None:
        state = self.get()
        if state.comparison is None:
            return None
        stage = next(
            (item for item in state.comparison["stages"] if item["stage"] == stage_name),
            None,
        )
        if stage is None:
            return None
        return {
            **stage,
            "run": self._run_ref(state),
            "differences": [
                {
                    **difference,
                    "record_token": state.employee_to_token.get(str(difference["key"][0]))
                    if difference.get("key")
                    else None,
                }
                for difference in stage["differences"]
            ],
        }

    @staticmethod
    def _employee_access_differences(state: ReferenceWorkspaceState, employee_id: str) -> list[dict[str, Any]]:
        if state.comparison is None:
            return []
        return [
            {"stage": stage["stage"], **difference}
            for stage in state.comparison["stages"]
            for difference in stage["differences"]
            if difference.get("key") and difference["key"][0] == employee_id
        ]
