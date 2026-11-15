"""JSON codec and dispatcher shared by the golden exporter and the engine CLI.

Why one module: the goldens and the differential fuzzer must speak the *same*
schema, or a mismatch could be the harness rather than the port. Both call
``execute(request)``, which runs the production engine (``backend/domain``) and
returns a JSON-able response.

Request  : {"id", "op", "rows"?, "params"?}
Response : {"id", "ok": true, "result": <tree>, "trail": <tree>|null, "float_digest": "<sha256>"}
           {"id", "ok": false, "error": "<Python exception type name>"}

Encoding rules (mirrored by the C# harness):
* dates -> ISO strings; dataclass results -> objects with field order preserved;
* floats are emitted with ``repr`` (what ``json.dumps`` does) and re-read as
  doubles; an int is never silently a float, so ``35`` and ``35.0`` differ;
* ``float_digest`` is SHA-256 over the IEEE-754 little-endian bytes of every float
  in the result tree in traversal order, so bit equality never depends on the
  text round trip.
Only new files under ``parity/`` are written; no existing Python is touched.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from domain.calculation import fiscal as fiscal_mod  # noqa: E402
from domain.calculation import headcount as hc  # noqa: E402
from domain.calculation import onezero as oz  # noqa: E402
from domain.calculation.floors import StatutoryFloors, program_name  # noqa: E402
from domain.calculation.trail import TrailRecorder  # noqa: E402


def _d(s: str | None) -> date | None:
    return None if s is None else date.fromisoformat(s)


def build_methodology(block: dict | None) -> oz.OneZeroMethodology:
    return oz.OneZeroMethodology(**(block or {}))


def build_pack(p: dict) -> oz.OneZeroPack:
    return oz.OneZeroPack(
        min_weekly_hours=p["min_weekly_hours"],
        min_weekly_wages=p["min_weekly_wages"],
        wage_basis=p.get("wage_basis", "regular"),
        geographic_granularity=p.get("geographic_granularity", "unit"),
        pt_aggregation=bool(p.get("pt_aggregation", False)),
        headcount_unit_field=p.get("headcount_unit_field", "Worksite_ID"),
        citation=p.get("citation", ""),
        pt_band_hours=tuple(p["pt_band_hours"]) if p.get("pt_band_hours") is not None else None,
        pt_weight=p.get("pt_weight"),
        measuring_date=p.get("measuring_date", "last_day"),
        entity_combination=p.get("entity_combination", "permitted"),
        included_pay_codes=tuple(p["included_pay_codes"]) if p.get("included_pay_codes") is not None else None,
        excluded_pay_codes=tuple(p["excluded_pay_codes"]) if p.get("excluded_pay_codes") is not None else None,
        tax_year=p.get("tax_year"),
        methodology=build_methodology(p.get("methodology")),
    )


KNOWN = ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date",
         "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State"]


def project(rows: list[dict]) -> list[dict]:
    """Rows reduced to the columns the port models (extra columns are not carried; see findings)."""
    return [{k: r[k] for k in KNOWN if k in r} for r in rows]


def to_tree(x: Any) -> Any:
    """Plain-JSON view of an engine value (dates become ISO strings, dataclasses objects)."""
    if isinstance(x, oz.OneZeroResult):
        return {
            "method": x.method,
            "tax_year": x.tax_year,
            "analysis_start_month": x.analysis_start_month.isoformat(),
            "months": [m.isoformat() for m in x.months],
            "total_hours_and_wages": to_tree(x.total_hours_and_wages),
            "eligible_employees": to_tree(x.eligible_employees),
            "employee_unit_matrix": to_tree(x.employee_unit_matrix),
            "summary": to_tree(x.summary),
            "average_headcount": to_tree(x.average_headcount),
            "annual_average": x.annual_average,
            "flags": to_tree(x.flags),
            "all_averages": to_tree(x.all_averages),
        }
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, dict):
        return {k: to_tree(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_tree(v) for v in x]
    if isinstance(x, (set, frozenset)):
        raise TypeError("sets have no stable order and must not reach a result tree")
    return x


def float_digest(tree: Any) -> str:
    h = hashlib.sha256()

    def walk(x: Any) -> None:
        if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
            return
        if isinstance(x, float):
            h.update(struct.pack("<d", x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        else:
            raise TypeError(type(x).__name__)

    walk(tree)
    return h.hexdigest()


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _run_method(op: str, req: dict) -> tuple[Any, dict | None]:
    pr = req["params"]
    pack = build_pack(pr["pack"])
    fn = oz.run_pay_period_method if op == "pay_period" else oz.run_min_max_method
    rec = TrailRecorder(title=pr.get("trail_title", ""), citation=pr.get("trail_citation", "")) if pr.get("with_trail") else None
    window = tuple(_d(v) for v in pr["fiscal_window"]) if pr.get("fiscal_window") else None
    res = fn(
        req["rows"],
        tax_year=pr["tax_year"],
        analysis_start_month=_d(pr["analysis_start_month"]),
        pack=pack,
        fiscal_year_end_month=pr.get("fiscal_year_end_month", 12),
        fiscal_window=window,
        recorder=rec,
    )
    return res, (rec.to_dict() if rec else None)


def _helpers(req: dict) -> Any:
    pr = req["params"]
    name = pr["name"]
    a = pr.get("args", [])
    if name == "fiscal_year_of":
        return oz.fiscal_year_of(_d(a[0]), a[1])
    if name == "fiscal_window_start":
        return oz.fiscal_window_start(a[0], a[1])
    if name == "twelve_month_ends":
        return oz._twelve_month_ends(_d(a[0]))
    if name == "measuring_date_for_month":
        return oz._measuring_date_for_month(_d(a[0]), a[1])
    if name == "adjusted_target":
        return oz._adjusted_target_for_month(_d(a[0]), _d(a[1]), a[2])
    if name == "infer_frequency":
        return oz._infer_frequency(a[0])
    if name == "round_half_up":
        return oz._round_half_up(a[0], a[1])
    if name == "classify_eligibility":
        w, ph, pw = oz._classify_eligibility(a[0], build_pack(pr["pack"]))
        return [w, ph, pw]
    if name == "qualifies":
        return oz.qualifies_as_pay_period(a[0], build_methodology(pr.get("methodology")))
    raise ValueError(f"unknown helper {name}")


def _fiscal(req: dict) -> Any:
    pr = req["params"]
    name = pr["name"]
    a = pr["args"]
    if name == "resolve_tax_year":
        return fiscal_mod.resolve_tax_year(_d(a[0]), _d(a[1]), a[2])
    if name == "window_from_client_rules":
        return fiscal_mod.window_from_client_rules(_d(a[0]), _d(a[1]), a[2], note=a[3] if len(a) > 3 else "").as_dict()
    if name == "assumed_calendar_window":
        w = fiscal_mod.assumed_calendar_window(a[0], a[1])
        return {**w.as_dict(), "_assumed": w.assumed, "_is_calendar": w.is_calendar, "_matters": w.convention_matters}
    raise ValueError(f"unknown fiscal op {name}")


def execute(req: dict) -> dict:
    """Run one request through the production engine; never raises."""
    rid = req.get("id")
    try:
        op = req["op"]
        trail = None
        if op in ("pay_period", "min_max"):
            res, trail = _run_method(op, req)
            result = to_tree(res)
        elif op == "preprocess":
            pr = req["params"]
            rec = TrailRecorder() if pr.get("with_trail") else None
            window = tuple(_d(v) for v in pr["fiscal_window"]) if pr.get("fiscal_window") else None
            out = oz.preprocess(
                req["rows"], tax_year=pr["tax_year"], fiscal_year_end_month=pr.get("fiscal_year_end_month", 12),
                fiscal_window=window, methodology=build_methodology(pr.get("methodology")), recorder=rec,
            )
            result = to_tree(project(out))
            trail = rec.to_dict() if rec else None
        elif op == "first_measurable_month":
            pr = req["params"]
            result = oz.first_measurable_month(req["rows"], (_d(pr["window"][0]), _d(pr["window"][1]))).isoformat()
        elif op == "unreachable_months":
            result = oz.unreachable_months(req["rows"], [_d(m) for m in req["params"]["months"]])
        elif op == "apply_pay_code_policy":
            result = to_tree(project(oz.apply_pay_code_policy(req["rows"], build_pack(req["params"]["pack"]))))
        elif op == "average_headcount":
            pr = req["params"]
            window = tuple(_d(v) for v in pr["window"]) if pr.get("window") else None
            result = hc.average_headcount(req["rows"], pr["state"], pr["tax_year"], build_pack(pr["pack"]), window)
        elif op == "rows_for_state_year":
            pr = req["params"]
            window = tuple(_d(v) for v in pr["window"]) if pr.get("window") else None
            result = to_tree(project(hc.rows_for_state_year(req["rows"], pr["state"], pr["tax_year"], window)))
        elif op == "row_states":
            result = [hc.row_state(r) for r in req["rows"]]
        elif op == "states_present":
            result = hc.states_present(req["rows"])
        elif op == "helper":
            result = to_tree(_helpers(req))
        elif op == "fiscal":
            result = to_tree(_fiscal(req))
        elif op == "floors":
            pr = req["params"]
            f = StatutoryFloors(program_code=pr["program_code"], tax_year=pr["tax_year"], min_weekly_hours=pr["min_weekly_hours"],
                                min_weekly_wages=pr["min_weekly_wages"], basis=pr["basis"], provenance=pr["provenance"], pack_file=pr["pack_file"])
            result = {"as_dict": to_tree(f.as_dict()), "prototype_verify": f.prototype_verify, "program_name": program_name(pr["pack_file"])}
        else:
            raise ValueError(f"unknown op {op}")
        return {"id": rid, "ok": True, "result": result, "trail": trail, "float_digest": float_digest([result, trail])}
    except Exception as e:  # the oracle's failures are part of the contract
        return {"id": rid, "ok": False, "error": type(e).__name__}
