"""Family operations of the engine CLI: the oracle side of the C# differential fuzzer for the ported families.

Request  : {"id", "op": "call", "family", "fn", "args"}     (``family`` is one of FAMILIES)
Response : {"k": "call", "id", "fn", "args", "out"}           a result tree, or
           {"k": "call", "id", "fn", "args", "err", "msg"}    the Python exception type and ``str(exception)``

The response is the golden line format of the exporters (``golden_rec``), so the C# replay of a golden and the fuzzer
share one comparison. ``args`` uses the exporters' encoding: ``{"$date"}``, ``{"$dt"}``, ``{"$dec"}`` tags, floats as
``repr`` (NaN/Infinity allowed), ints never silently floats. It is echoed back after the run because a call may add what
it observed (the payroll-wage lookups of the credit functions and the forecast, ``wage_calls``).

Each family calls the SAME production code path the matching exporter records, by importing the exporter's own helpers
(``export_proximity``'s call, ``export_gold.table_out``, ``export_baseyear.run_cbyt``, ``export_forecast.run``,
``export_credit_math.traced``), so a fuzz mismatch cannot be a difference between two harnesses. Imports are lazy: a
batch that asks for one family pays for that family only.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
import golden_rec as gr  # noqa: E402

FAMILIES = ("proximity", "gold_projection", "baseyear", "simulation", "credit_math")


def decode(x):
    """Tagged JSON to Python values (the inverse of ``golden_rec.enc`` for dates, datetimes and decimals)."""
    if isinstance(x, dict):
        if len(x) == 1:
            if "$date" in x:
                return date.fromisoformat(x["$date"])
            if "$dt" in x:
                return datetime.fromisoformat(x["$dt"])
            if "$dec" in x:
                return Decimal(x["$dec"])
        return {k: decode(v) for k, v in x.items()}
    if isinstance(x, list):
        return [decode(v) for v in x]
    return x


# --------------------------------------------------------------------------- proximity


def _proximity(fn: str, args: dict):
    from domain.calculation import proximity as prox
    from domain.calculation.floors import StatutoryFloors

    kw = decode(args)
    if "floors" in kw:
        f = kw["floors"]
        code = f["program_code"]
        kw["floors"] = StatutoryFloors(code, f["tax_year"], f["min_hours"], f["min_wages"], {}, {}, code.lower() + ".json")
    return getattr(prox, fn)(**kw)


# --------------------------------------------------------------------------- gold projection

_TABLE_OF = {
    "employee_period_fact_rows": "employee_period_fact", "employee_eligibility_rows": "employee_eligibility",
    "onezero_matrix_rows": "onezero_matrix", "unit_month_summary_rows": "unit_month_summary",
}


def _ns(d):
    return None if d is None else SimpleNamespace(**d)


def _trend(d):
    if d is None:
        return None
    return SimpleNamespace(**{**d, "tranche_events": [SimpleNamespace(**e) for e in d["tranche_events"]]})


def _gold(fn: str, args: dict):
    import export_gold as eg
    from tools import gold_projection as gp
    from tools.tokens import record_token

    a = decode(args)
    if fn == "_dec":
        return eg.cell(gp._dec(a["value"], a["places"]))
    if fn == "_day":
        return eg.cell(gp._day(a["value"]))
    if fn == "_flag":
        return eg.cell(gp._flag(a["value"]))
    if fn == "record_token":
        return record_token(a["account_id"], a["program_code"], a["tax_year"], a["employee_id"])
    if fn == "calculation_id":
        return gp.calculation_id(**a)
    if fn in _TABLE_OF:
        return eg.table_out(_TABLE_OF[fn], getattr(gp, fn)(**a))
    if fn == "run_method_summary_row":
        s = a.pop("result")
        res = SimpleNamespace(annual_average=s["annual_average"], eligible_employees=[0] * s["n_eligible"], total_hours_and_wages=[0] * s["n_totals"],
                              employee_unit_matrix=[0] * s["n_matrix"], flags=s["flags"], months=s["months"])
        return eg.table_out("run_method_summary", [gp.run_method_summary_row(res, **a)])
    if fn == "unit_year_master_row":
        a.pop("series", None)
        stair, trend, unit_year, stamp = _ns(a.pop("stair")), _trend(a.pop("trend")), a.pop("unit_year"), a.pop("appended_at")
        return eg.table_out("unit_year_master", [gp.unit_year_master_row(**a, stair=stair, trend=trend, unit_year=unit_year, appended_at=stamp)])
    if fn == "unit_credit_installment_rows":
        a.pop("series", None)
        trend, years, stamp = _trend(a.pop("trend")), a.pop("years_with_data"), a.pop("appended_at")
        return eg.table_out("unit_credit_installment", gp.unit_credit_installment_rows(trend, years_with_data=years, appended_at=stamp, **a))
    raise KeyError(fn)


# --------------------------------------------------------------------------- base year


def _baseyear(fn: str, args: dict):
    import export_baseyear as eb
    from tools import unit_trend as ut

    if fn == "compute_base_year_tranches":
        out = eb.traced(args["trail"], lambda: eb.result_tree(eb.run_cbyt(args)))
        return {**out["result"], **({"trail": out["trail"]} if "trail" in out else {})}
    if fn == "tranche_columns":
        return ut.tranche_columns(eb.run_cbyt(args), args["years"])
    raise KeyError(fn)


# --------------------------------------------------------------------------- simulation and forecast


def _simulation(fn: str, args: dict):
    import export_forecast as ef

    a = decode(args)
    try:
        return ef.run(fn, a)
    finally:
        if "wage_calls" in a:
            args["wage_calls"] = a["wage_calls"]


# --------------------------------------------------------------------------- credit math


def _credit(fn: str, args: dict):
    import export_credit_math as ec
    from tools import credit_math as cm
    from tools import pack_lookup as pl
    from tools import program_credit as pc

    a = args
    try:
        if fn in ("apply_one_zero_program_credit", "apply_one_zero_state_credit"):
            return ec.make_run(a)()
        if fn == "program_per_job_usd":
            return pc.program_per_job_usd(a["key"])
        if fn == "state_per_job_usd":
            return cm.state_per_job_usd(a["key"])
        if fn in ("combine_program_entity_credits", "combine_entity_credits"):
            call = pc.combine_program_entity_credits if fn == "combine_program_entity_credits" else cm.combine_entity_credits
            return ec.traced(a, lambda: call(a["key"], a["fein_breakdown"]))
        if fn == "credit_from_pack":
            return ec.traced(a, lambda: pc.credit_from_pack(a["doc"], tuple(a["names"]), a["average_headcount"], a["prior"], a["threshold_override"]))
        if fn == "load_year_pack":
            pack, resolved = cm.load_year_pack(a["pack_file"], a["tax_year"])
            return {"pack": pack, "year_resolved": resolved}
        if fn == "resolve_statutory_floors":
            f = cm.resolve_statutory_floors(a["program_code"], a["tax_year"])
            return {"fields": gr.enc(f), "as_dict": f.as_dict(), "prototype_verify": f.prototype_verify}
        if fn == "resolve_tax_year_convention":
            return cm.resolve_tax_year_convention(a["program_code"], a["tax_year"])
        if fn == "authored_years":
            return cm.authored_years(a["pack_file"])
        if fn == "is_year_scoped":
            return cm.is_year_scoped(a["pack_file"])
        if fn == "pack_file_for":
            return pl.pack_file_for(a["key"])
        if fn == "load_pack_one_zero":
            return {"pack": gr.enc(cm.load_pack_one_zero(a["key"], a["tax_year"])), "ingestion_calls": []}
        raise KeyError(fn)
    except Exception as e:
        raise _Normalised(type(e).__name__, ec.norm(str(e), ec.worlds_mod.RULES.resolve(), None)) from None


class _Normalised(Exception):
    """An exception whose message already has machine paths replaced by placeholders."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


DISPATCH = {"proximity": _proximity, "gold_projection": _gold, "baseyear": _baseyear, "simulation": _simulation, "credit_math": _credit}


def respond(req: dict) -> str:
    """Answers one ``call`` request with a golden-format line (never raises)."""
    fn, args = req["fn"], req["args"]
    rec = {"k": "call", "id": req.get("id"), "fn": fn}
    try:
        rec["out"] = gr.enc(DISPATCH[req["family"]](fn, args))
    except _Normalised as e:
        rec["err"], rec["msg"] = e.kind, str(e)
    except Exception as e:  # the exception type and message are part of the contract
        rec["err"], rec["msg"] = type(e).__name__, str(e)
    rec["args"] = args
    return json.dumps(rec, separators=(",", ":"), ensure_ascii=True)
