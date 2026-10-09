"""Run the engine for one client-year and write the result to the warehouse.

A **command**: it changes what the business believes. Before this existed the
v2 run endpoint appended a summary to a module-level dict, which evaporated on
restart and which no read could ever query — a run that reported success and
persisted nothing.

Three things shape the handler.

**The engine is called, not changed.** `domain/calculation/` is certified and
moves from the read path to the write path by being invoked from here instead of
from a query. Nothing in this file computes a statutory quantity.

**A run covers one client-year at employee grain and the WHOLE SERIES at unit
grain.** `employee_period_fact`, `employee_eligibility` and `onezero_matrix`
describe the requested year. `unit_year_master` and `unit_credit_installment`
cannot: a base year is inferred from the years around it and a tranche pays out
across the five that follow, so writing one year in isolation would produce a
unit series stitched from different runs. Both are tagged with this `run_id`.

**Append-only.** A rerun writes a new `run_id`, marks the prior unit rows
`is_current = 0` and the prior manifests `superseded`. Nothing is updated in
place, because a superseded figure may already be on a filed return.
"""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.mediator import Command

logger = logging.getLogger(__name__)

_METHODS = ("min_max", "pay_period")
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RunClientCalculationCommand(Command):
    """Recalculate one client-year and persist it.

    Per client-year because that is the unit of work, not because a run is
    something an operator starts. The decided model is pipeline-driven: payroll
    lands, the enrichment run assesses it, and a client in the system has been
    assessed. This command is what that sweep dispatches, and what a rules
    change or corrected payroll re-dispatches. It is a refresh, not the thing
    that makes a client appear.
    """

    client_id: int = 0
    tax_year: int = 0
    state: str = "GA"
    #: Which years to record a CLAIM for. Empty means every year the payroll
    #: covers, which is the pipeline model: a client that has been run has been
    #: assessed, not assessed for one year. `tax_year` still scopes the Gold
    #: run itself, because a manifest is per client-year.
    #:
    #: Narrowing this was why Northwind showed one filled cell where its peers
    #: showed six. A targeted recalculation passes the single year it wants.
    assess_tax_years: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.client_id <= 0:
            raise ValueError("client_id is required and must be positive")
        if self.tax_year <= 0:
            raise ValueError("tax_year is required and must be positive")


class RunFailed(RuntimeError):
    """The run did not produce a usable, validated result."""


def _code_commit() -> str:
    """The commit the engine ran at. `char(40)`, so it must not exceed 40."""
    configured = os.getenv("GIT_COMMIT")
    if configured:
        return configured.strip()[:40]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()[:40]
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"


def _assumption_identity() -> list[dict[str, str]]:
    """The active assumption sets, with a content hash of each.

    The label alone is not enough: an edited set under an unchanged id would
    replay differently, which is exactly what a manifest exists to rule out.
    """
    import hashlib
    import json

    methodology = _REPO_ROOT / "backend" / "rules" / "methodology"
    out: list[dict[str, str]] = []
    for filename in (
        "reference-dataset-assumptions.v8.json",
        "reference-onezero-assumptions.v7.json",
    ):
        path = methodology / filename
        if not path.exists():
            continue
        raw = path.read_bytes()
        out.append({
            "set_id": str(json.loads(raw).get("assumption_set_id") or path.stem),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return out


def _base_year_for(
    unit_id: str,
    unit_years: dict[int, dict[str, Any]],
    reachable_by_year: dict[int, int],
    overrides: dict[str, int],
    infer: Any,
) -> tuple[int, str]:
    """The base a location is measured from, and where it came from.

    A saved choice (WI-21) wins when the payroll still supports it: the year
    exists and is complete. Otherwise the run infers one, as it always has, and
    says so — a saved base the payroll no longer supports is logged, not
    silently honoured, because a partial year makes a flattering base.
    """
    chosen = overrides.get(unit_id)
    if chosen is not None:
        year = unit_years.get(chosen)
        if year is not None and int(year.get("months_with_headcount") or 0) >= reachable_by_year.get(chosen, 12):
            return chosen, "override"
        logger.warning(
            "saved base year TY%s for %s is not a complete year in this run; inferring instead",
            chosen, unit_id,
        )
    base_year = infer(unit_years, reachable_by_year=reachable_by_year)
    if base_year is None or base_year not in unit_years:
        base_year = min(unit_years)
    return base_year, "inferred"


def _open_year_reading(
    unit_year: dict[str, Any], trend: Any, statute: dict[str, Any], threshold: float,
) -> Any:
    """An open year's on-track reading. See `application.open_year.open_year_reading`."""
    from application.open_year import open_year_reading

    return open_year_reading(unit_year.get("average_headcount"), trend, statute, threshold)


def _replay_unit_series(
    *, client_id: int, state: str, program_code: str, payroll: list[dict[str, Any]],
    run_id: str, appended_at: Any,
) -> tuple[list[tuple], list[tuple], list[tuple], list[tuple], list[tuple]]:
    """Every priceable year, both methods, at unit grain with the credit layer.

    Reuses the same statutory lookups the read path uses rather than restating
    them — a second implementation of the threshold or the per-job rate is a
    second chance to disagree with the grid.

    Returns the month grain as well. It used to be written only for the year the
    run was requested for, while the unit grain covered every year, so the grid
    showed an average against twelve em dashes for five years out of six — which
    reads as missing data rather than as a year nobody asked about.

    AND the employee grain, for the same reason. This loop already computes
    `all_averages`, `total_hours_and_wages` and `employee_unit_matrix` for every
    year and was discarding all three, so `employee_eligibility` and
    `onezero_matrix` held one year while `unit_year_master` held six. "Who
    qualifies" then had to re-run the engine on every page load to answer for a
    year the run had already computed and thrown away.

    `employee_period_fact` is widened too. It is much the largest table — one
    row per employee per pay period — but it is what places an employee at a
    worksite, so without it the near-threshold cohort is empty for every year
    except the one the run was asked for. Writes are allowed to be slow; a page
    that cannot answer is not.
    """
    from application.queries._client_run import ClientRunNotAvailable, resolve_client_run
    from application.queries.get_unit_trend import (
        _MIN_REACHABLE_MONTHS,
        _candidate_years,
        _designation_at,
        _year_benefit,
    )
    from domain.calculation.onezero import (
        run_min_max_method, run_pay_period_method, unreachable_months,
    )
    from domain.calculation.rollups import rollup_matrix_by_two_fields
    from tools import gold_projection as gp
    from application.open_year import MIN_OPEN_MONTHS as _MIN_OPEN_MONTHS, is_open
    from tools.unit_trend import (
        STATUS_IN_PROGRESS, aggregate_units, build_unit_series, infer_base_year,
        unit_status, unit_trend,
    )

    master_rows: list[tuple] = []
    installment_rows: list[tuple] = []
    # WI-21. Base years a human chose, read ONCE for the run. A read failure
    # fails the run: silently falling back would drop a decision on the floor.
    from application.wiring import get_override_repository

    overrides = get_override_repository().base_years(client_id, program_code)
    month_rows: list[tuple] = []
    eligibility_rows: list[tuple] = []
    matrix_rows: list[tuple] = []
    period_rows: list[tuple] = []
    method_summary_rows: list[tuple] = []
    # Payroll is per YEAR, not per method, so it is captured on the first pass
    # and reused on the second. Projecting it twice would double the largest
    # table in the warehouse for no additional truth.
    payroll_by_year: dict[int, list[dict[str, Any]]] = {}

    for method in _METHODS:
        runner = run_min_max_method if method == "min_max" else run_pay_period_method
        per_year_units: dict[int, list[dict[str, Any]]] = {}
        reachable_by_year: dict[int, int] = {}
        declines: dict[int, str] = {}
        # Years still running (TY2026). Read on their closed months, never
        # priced into the credit series, never claimed. See application/open_year.
        open_years: set[int] = set()

        for tax_year in _candidate_years(state):
            try:
                run = resolve_client_run(
                    account_id=client_id, state=state, tax_year=tax_year, rows=payroll,
                )
            except ClientRunNotAvailable as exc:
                declines[tax_year] = str(exc)
                continue

            result = runner(run.rows, **run.engine_kwargs())
            unreached = unreachable_months(run.rows, result.months)
            reachable = len(result.months) - len(unreached)
            year_open = is_open(run.window.end)
            if year_open and reachable < _MIN_OPEN_MONTHS:
                # An open year is read over its closed months, so the twelve-month
                # test below does not apply — but two months is too early to say
                # anything a reader should repeat.
                declines[tax_year] = (
                    f"year in progress: {reachable} month(s) closed, fewer than "
                    f"{_MIN_OPEN_MONTHS} to read a pace from"
                )
                continue
            if not year_open and reachable < _MIN_REACHABLE_MONTHS:
                declines[tax_year] = (
                    f"payroll reaches {reachable} of {len(result.months)} monthly "
                    f"measuring dates; a twelve-month average would be mostly zeroes"
                )
                continue

            summary = [
                {"unit_id": row["Worksite_ID"], "fein": row["Entity_FEIN"], **row}
                for row in rollup_matrix_by_two_fields(
                    result.employee_unit_matrix, "Worksite_ID", "Entity_FEIN"
                )
            ]
            per_year_units[tax_year] = aggregate_units(summary)
            reachable_by_year[tax_year] = reachable
            if year_open:
                # "Change the denominator from 12 months to 8 or 9" — the months
                # after the checkpoint are zero because they have not happened.
                open_years.add(tax_year)
                for unit in per_year_units[tax_year]:
                    unit["average_headcount"] = round(unit["total"] / reachable, 2) if reachable else 0.0
                    unit["months_closed"] = reachable
            month_rows.extend(gp.unit_month_summary_rows(
                result.summary, client_id=client_id, tax_year=tax_year,
                method=method, run_id=run_id, unreachable=unreached,
            ))
            # The employee grain for THIS year, from the result already in hand.
            eligibility_rows.extend(gp.employee_eligibility_rows(
                totals=result.total_hours_and_wages, averages=result.all_averages,
                client_id=client_id, program_code=program_code,
                tax_year=tax_year, method=method, run_id=run_id,
            ))
            matrix_rows.extend(gp.onezero_matrix_rows(
                result.employee_unit_matrix, client_id=client_id,
                program_code=program_code, tax_year=tax_year,
                method=method, run_id=run_id,
            ))
            if tax_year not in payroll_by_year:
                payroll_by_year[tax_year] = run.rows
            method_summary_rows.append(gp.run_method_summary_row(
                result, client_id=client_id, program_code=program_code,
                tax_year=tax_year, method=method, run_id=run_id,
                unit_fein_rows=len(summary), appended_at=appended_at,
            ))

        if not per_year_units:
            continue

        years = sorted(per_year_units)
        # Statute is versioned by tax year [ADR-005], so the benefit is resolved
        # PER YEAR. It used to be read once from `years[-1]` and applied to the
        # whole series, which prices a TY2020 credit at TY2025's rate — the
        # retroactive scan is exactly the feature that would misreport. Georgia
        # has held $3,500 across every authored year, so nothing moves today;
        # the packs are read rather than assumed so it stays that way.
        #
        # That $3,500 is the T1B40 / Military Zone / Opportunity Zone band — the
        # one open to ANY lawful business. Standard Tier 1 pays $4,000 but is
        # restricted to Eligible Business Enterprises, which two of the demo
        # clients (retail, food service) are not. Repricing to $4,000 without a
        # per-worksite industry flag would overstate exactly those two.
        benefit_by_year = {
            year: _year_benefit(program_code, year) for year in years
        }
        latest_benefit = benefit_by_year[years[-1]]
        series = build_unit_series(per_year_units)

        for unit_id, unit_years in sorted(series.items()):
            # An open year is neither a base nor a priced year: its tranches
            # would be opened on months that have not happened.
            closed = {y: u for y, u in unit_years.items() if y not in open_years} or unit_years
            base_year, base_source = _base_year_for(
                unit_id, closed, reachable_by_year, overrides, infer_base_year,
            )

            latest_designation = _designation_at(unit_id, max(unit_years), client_id)
            threshold = (
                float(latest_designation["min_new_jobs"]) if latest_designation
                else latest_benefit["threshold"]
            )
            # A negotiated designation is a CURRENT fact about the location, so
            # it overrides the pack in every year — unchanged, and flagged
            # prototype data (DISC-10). Absent one, each year uses its own.
            per_year = {
                year: {
                    "threshold": threshold if latest_designation else benefit["threshold"],
                    "per_job_usd": benefit["per_job_usd"],
                }
                for year, benefit in benefit_by_year.items()
            }
            trend = unit_trend(
                closed, state=state, base_year=base_year, threshold=threshold,
                per_job_usd=latest_benefit["per_job_usd"],
                tranche_years=latest_benefit["benefit_period_years"],
                benefit_by_year=per_year,
            )
            by_year = {y.year: y for y in trend.years}

            for tax_year in years:
                unit_year = unit_years.get(tax_year)
                if unit_year is None:
                    continue
                stair = by_year.get(tax_year)
                status = None
                if tax_year in open_years and tax_year != base_year:
                    stair, status = _open_year_reading(
                        unit_year, trend, per_year.get(tax_year, {}), threshold,
                    ), STATUS_IN_PROGRESS
                designation = _designation_at(unit_id, tax_year, client_id)
                feins = unit_year.get("feins") or []
                months_reachable = reachable_by_year.get(tax_year, 12)

                master_rows.append(gp.unit_year_master_row(
                    client_id=client_id,
                    worksite_id=unit_id,
                    # A unit can host several legal entities; naming one of them
                    # would misattribute the others.
                    entity_fein=str(feins[0]) if len(feins) == 1 else None,
                    program_code=program_code,
                    method=method,
                    tax_year=tax_year,
                    stair=stair,
                    trend=trend,
                    unit_year=unit_year,
                    base_year=base_year,
                    base_year_source=base_source,
                    months_reachable=months_reachable,
                    declined=False,
                    decline_reason=None,
                    threshold_source="designation" if latest_designation else "rule_pack",
                    status=status or unit_status(
                        tax_year=tax_year, base_year=base_year,
                        qualified=bool(stair.qualified) if stair else False,
                        months_with_headcount=unit_year["months_with_headcount"],
                        months_reachable=months_reachable,
                    ),
                    tier=(designation or {}).get("tier"),
                    designation=(designation or {}).get("designation"),
                    tier_source="prototype" if designation else "unassigned",
                    run_id=run_id,
                    appended_at=appended_at,
                ))

            installment_rows.extend(gp.unit_credit_installment_rows(
                trend, client_id=client_id, worksite_id=unit_id,
                program_code=program_code, method=method,
                # An open year's installment is still a forecast.
                years_with_data=[y for y in years if y not in open_years],
                run_id=run_id, appended_at=appended_at,
            ))

    for tax_year, rows in sorted(payroll_by_year.items()):
        period_rows.extend(gp.employee_period_fact_rows(
            rows, client_id=client_id, program_code=program_code,
            tax_year=tax_year, run_id=run_id,
        ))

    return (
        master_rows, installment_rows, month_rows,
        eligibility_rows, matrix_rows, period_rows, method_summary_rows,
    )


def handle_run_client_calculation(command: RunClientCalculationCommand) -> dict[str, Any]:
    """Execute the engine and persist every Gold and provenance row it implies."""
    from application.queries._client_run import resolve_client_run
    from application.wiring import get_gold_writer, get_mediator
    from domain.calculation.onezero import (
        run_min_max_method, run_pay_period_method, unreachable_months,
    )
    from domain.warehouse import RunManifest
    from infrastructure.persistence.fabric_warehouse import _MANIFEST_COLUMNS
    from infrastructure.persistence.warehouse_gold import GoldWriteFailed
    from tools import gold_projection as gp

    state = command.state.upper()
    started = gp.utc_now()
    run_id = uuid.uuid4().hex

    run = resolve_client_run(
        account_id=command.client_id, state=state, tax_year=command.tax_year,
    )
    engine_kwargs = run.engine_kwargs()
    results = {
        "min_max": run_min_max_method(run.rows, **engine_kwargs),
        "pay_period": run_pay_period_method(run.rows, **engine_kwargs),
    }

    assumptions = _assumption_identity()
    appended_at = gp.utc_now()

    manifest = RunManifest(
        run_id=run_id,
        client_id=command.client_id,
        program_code=run.program_code,
        tax_year=command.tax_year,
        fiscal_year_begin=run.window.begin,
        fiscal_year_end=run.window.end,
        run_started_at=started,
        run_completed_at=None,
        # Written at the START of the run. The writer stamps completion only
        # once every Gold row is down, so a run that dies mid-write stays
        # visibly unfinished instead of claiming a success it never reached.
        run_status="running",
        step1_assumption_set_id=assumptions[0]["set_id"] if assumptions else None,
        step1_assumption_sha256=assumptions[0]["sha256"] if assumptions else None,
        onezero_assumption_set_id=assumptions[1]["set_id"] if len(assumptions) > 1 else None,
        onezero_assumption_sha256=assumptions[1]["sha256"] if len(assumptions) > 1 else None,
        rule_pack_version=str(run.floors.as_dict().get("source") or ""),
        code_commit=_code_commit(),
        calculation_id=gp.calculation_id(
            client_id=command.client_id,
            program_code=run.program_code,
            tax_year=command.tax_year,
            window_begin=run.window.begin,
            window_end=run.window.end,
            floors=run.floors.as_dict(),
            assumption_ids=[a["set_id"] for a in assumptions],
            rows=run.rows,
        ),
        triggered_by=command.actor,
    )

    eligibility_rows: list[tuple] = []
    matrix_rows: list[tuple] = []
    month_rows: list[tuple] = []
    method_summary_rows: list[tuple] = []
    for method, result in results.items():
        eligibility_rows.extend(gp.employee_eligibility_rows(
            totals=result.total_hours_and_wages, averages=result.all_averages,
            client_id=command.client_id, program_code=run.program_code,
            tax_year=command.tax_year, method=method, run_id=run_id,
        ))
        matrix_rows.extend(gp.onezero_matrix_rows(
            result.employee_unit_matrix, client_id=command.client_id,
            program_code=run.program_code, tax_year=command.tax_year,
            method=method, run_id=run_id,
        ))
        month_rows.extend(gp.unit_month_summary_rows(
            result.summary, client_id=command.client_id, tax_year=command.tax_year,
            method=method, run_id=run_id,
            unreachable=unreachable_months(run.rows, result.months),
        ))
        method_summary_rows.append(gp.run_method_summary_row(
            result, client_id=command.client_id, program_code=run.program_code,
            tax_year=command.tax_year, method=method, run_id=run_id,
            unit_fein_rows=len(result.summary), appended_at=appended_at,
        ))

    (
        master_rows, installment_rows, replay_month_rows,
        replay_eligibility, replay_matrix, replay_periods, replay_summaries,
    ) = _replay_unit_series(
        client_id=command.client_id, state=state, program_code=run.program_code,
        payroll=_all_payroll(command.client_id),
        run_id=run_id, appended_at=appended_at,
    )

    # The requested year's rows stay the ones computed above — it is the run
    # this command was asked for. The replay only fills the OTHER years, so
    # widening the series cannot move the year anybody is looking at.
    #
    # `(tax_year, method)` is at index 1 and 2 on all three method-keyed
    # projections; period fact has no method, so it keys on year alone.
    requested = {(command.tax_year, method) for method in results}

    def not_requested(row: tuple) -> bool:
        return (row[1], row[2]) not in requested

    month_rows.extend(row for row in replay_month_rows if not_requested(row))
    eligibility_rows.extend(row for row in replay_eligibility if not_requested(row))
    matrix_rows.extend(row for row in replay_matrix if not_requested(row))
    method_summary_rows.extend(row for row in replay_summaries if not_requested(row))
    period_rows = gp.employee_period_fact_rows(
        run.rows, client_id=command.client_id, program_code=run.program_code,
        tax_year=command.tax_year, run_id=run_id,
    )
    period_rows.extend(row for row in replay_periods if row[1] != command.tax_year)

    completed = gp.utc_now()
    manifest_row = tuple(getattr(manifest, column) for column in _MANIFEST_COLUMNS)

    writer = get_gold_writer()
    counts = writer.write_run({
        "client_id": command.client_id,
        "program_code": run.program_code,
        "run_id": run_id,
        "run_completed_at": completed,
        "run_manifest_columns": _MANIFEST_COLUMNS,
        "run_manifest_row": manifest_row,
        "employee_period_fact": period_rows,
        "employee_eligibility": eligibility_rows,
        "onezero_matrix": matrix_rows,
        "unit_month_summary": month_rows,
        "run_method_summary": method_summary_rows,
        "unit_year_master": master_rows,
        "unit_credit_installment": installment_rows,
    })

    # A claim makes the client appear on the portfolio page. Dispatched rather
    # than inlined so the claim store stays the one owner of that decision.
    from application.commands.assess_client import AssessClientCommand

    claim = get_mediator().send(AssessClientCommand(
        client_id=command.client_id,
        program_code=run.program_code,
        tax_years=command.assess_tax_years,
        actor=command.actor,
    ))

    violations = writer.validate()
    if violations:
        raise GoldWriteFailed(
            "run "
            f"{run_id} violated section 9: "
            + "; ".join(f"{v['query']} ({v['row_count']} rows)" for v in violations)
        )

    return {
        "run_id": run_id,
        "client_id": command.client_id,
        "tax_year": command.tax_year,
        "state": run.state,
        "program_code": run.program_code,
        "run_status": "success",
        "run_started_at": started.isoformat() + "Z",
        "run_completed_at": completed.isoformat() + "Z",
        "calculation_id": manifest.calculation_id,
        "code_commit": manifest.code_commit,
        "rows_written": counts,
        "validation": {"queries_run": len(_section_9_count()), "violations": []},
        "summary": {
            "employees_evaluated": len(results["min_max"].total_hours_and_wages),
            "min_max_eligible": len(results["min_max"].eligible_employees),
            "pay_period_eligible": len(results["pay_period"].eligible_employees),
        },
        "claim": {
            "assessed": len(claim.get("assessed", [])),
            "declined": len(claim.get("declined", [])),
        },
    }


def _all_payroll(client_id: int) -> list[dict[str, Any]]:
    """Every year of this client's payroll, loaded once for the unit replay."""
    from infrastructure.payroll.pay_period_source import load_pay_periods

    return load_pay_periods(client_id)


def _section_9_count():
    from infrastructure.persistence.warehouse_gold import SECTION_9_QUERIES

    return SECTION_9_QUERIES
