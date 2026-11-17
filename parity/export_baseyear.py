"""Golden vectors for the base-year family (stage BY): ``tools/baseyear.py``, ``tools/unit_trend.py``, ``tools/designation.py``
(``detect_designation_splits`` over the injected ``data/designations.py`` registry), ``tools/negotiated.py``, ``tools/reconcile.py`` and the
pure helpers of ``application/queries/get_unit_trend.py`` that ``run_client_calculation.py`` imports.

Every call runs the PRODUCTION function and records its arguments and either the output tree or the exception type and message
(``golden_rec`` conventions: floats keep their ``repr``, non-finite as ``NaN``/``Infinity``, ints stay ints, so int-versus-float shows at every
field). A ``{year: value}`` mapping travels as ``[[year, value], ...]`` so its insertion order is explicit. The tranche engine is recorded twice
per call: ``result`` (the dataclass fields, unrounded) and ``dict`` (``to_dict()``), plus the two totals and, when the arguments ask for one, the
calculation trail the call recorded (with its SHA-256).

Scenarios: every input of ``test_baseyear.py`` / ``test_api_trend.py`` / ``test_ga_depth.py`` / ``test_reconcile.py`` / ``test_designations.py``;
base years, gaps, single and empty series, tranche windows of 0..10 years, rates that differ on purpose per year, half-cent and negative and huge
amounts, overrides whose int-versus-float type leaks into ``round()``; seeded random batches; and realistic unit series built by running the
production engines over the committed synthetic payroll (``backend/data/payroll_pay_periods.csv``, date-shifted into several tax years).

Usage: python parity/export_baseyear.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import contextlib
import copy
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import config  # noqa: E402
import engine_io  # noqa: E402
import golden_rec as gr  # noqa: E402
import scenarios as sc  # noqa: E402
from application.queries import get_unit_trend as gut  # noqa: E402
from data import designations as dz  # noqa: E402
from domain.calculation import onezero as oz  # noqa: E402
from domain.calculation.rollups import rollup_matrix_by_two_fields  # noqa: E402
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder  # noqa: E402
from tools import baseyear as by  # noqa: E402
from tools import credit_math as cm  # noqa: E402
from tools import designation as dsg  # noqa: E402
from tools import negotiated as neg  # noqa: E402
from tools import reconcile as rec  # noqa: E402
from tools import unit_trend as ut  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "baseyear.jsonl.gz"
SEED = 20261120
NAN = float("nan")
INF = float("inf")
TITLE = {"title": "Base-year trail", "citation": "GA JTC base-year mechanics"}


def pairs(d):
    return None if d is None else [[k, v] for k, v in d.items()]


def unpairs(p):
    return None if p is None else {k: v for k, v in p}


def traced(spec, body):
    """Runs ``body`` under a trail recorder when the arguments ask for one; returns ``{"result", "trail"?}``."""
    recorder = TrailRecorder(title=spec["title"], citation=spec["citation"]) if spec else None
    token = set_recorder(recorder) if recorder is not None else None
    try:
        out = {"result": body()}
    finally:
        if token is not None:
            reset_recorder(token)
    if recorder is not None:
        out["trail"] = recorder.to_dict()
    return out


def result_tree(res: by.BaseYearResult) -> dict:
    return {"result": gr.enc(res), "dict": res.to_dict(), "totals": [res.total_annual_credit_usd, res.total_tranche_lifetime_usd]}


# ----------------------------------------------------------------------------- baseyear


def cbyt_args(yearly, *, base_year, threshold=2, per_job=3500, tranche_years=None, base_override=None, hwm_override=None, benefit=None, trail=None, state="GA"):
    return {"state": state, "yearly": pairs(yearly), "base_year": base_year, "threshold": threshold, "per_job_usd": per_job, "tranche_years": tranche_years,
            "base_average_override": base_override, "high_water_mark_override": hwm_override, "benefit": pairs(benefit), "trail": trail}


def run_cbyt(a: dict):
    kw = {}
    if a["tranche_years"] is not None:
        kw["tranche_years"] = a["tranche_years"]
    if a["base_average_override"] is not None:
        kw["base_average_override"] = a["base_average_override"]
    if a["high_water_mark_override"] is not None:
        kw["high_water_mark_override"] = a["high_water_mark_override"]
    if a["benefit"] is not None:
        kw["benefit_by_year"] = unpairs(a["benefit"])
    return by.compute_base_year_tranches(
        a["state"], unpairs(a["yearly"]), base_year=a["base_year"], threshold=a["threshold"], per_job_usd=a["per_job_usd"], **kw)


def cbyt_call(r: gr.Recorder, a: dict, columns: bool = True) -> None:
    def run():
        out = traced(a["trail"], lambda: result_tree(run_cbyt(a)))
        return {**out["result"], **({"trail": out["trail"]} if "trail" in out else {})}
    r.call("compute_base_year_tranches", a, run)
    if columns:
        base = a["base_year"]
        span = a["tranche_years"] if isinstance(a["tranche_years"], int) else 5
        years = list(range(base - 1, base + max(span, 0) + 3))
        args = {**a, "years": years}
        r.call("tranche_columns", args, lambda: ut.tranche_columns(run_cbyt(a), years))
        if len(years) > 3:
            shuffled = [years[2], years[0], years[2], years[-1], years[1]]
            r.call("tranche_columns", {**a, "years": shuffled}, lambda: ut.tranche_columns(run_cbyt(a), shuffled))


def test_scenarios(r: gr.Recorder) -> None:
    seq = lambda s, **kw: cbyt_call(r, cbyt_args(s, base_year=2021, **kw))  # noqa: E731
    seq({2021: 100, 2022: 105, 2023: 104})
    seq({2021: 100, 2022: 105})
    seq({2021: 100, 2022: 101})
    seq({2021: 100, 2022: 105, 2023: 104, 2024: 101, 2025: 103})
    seq({2021: 100, 2022: 130}, hwm_override=150)
    seq({2021: 100, 2022: 105}, base_override=80)
    seq({2021: 100, 2022: 105}, trail=TITLE)
    rates = lambda m: {y: {"threshold": 2, "per_job_usd": v} for y, v in m.items()}  # noqa: E731
    seq({2021: 100, 2022: 105, 2023: 110}, benefit=rates({2022: 3500, 2023: 4000}))
    seq({2021: 100, 2022: 105, 2023: 110}, benefit=rates({2022: 3500, 2023: 9999}))
    seq({2021: 100, 2022: 103, 2023: 103}, benefit={2022: {"threshold": 2, "per_job_usd": 3500}, 2023: {"threshold": 5, "per_job_usd": 3500}})
    seq({2021: 100, 2022: 105, 2023: 110}, benefit=rates({2023: 4000}))
    seq({2021: 100, 2022: 105}, benefit=rates({2022: 3500}))
    seq({2021: 100, 2022: 105, 2023: 110, 2024: 120, 2025: 125, 2026: 118}, benefit=rates({2022: 3500, 2023: 3600, 2024: 3700, 2025: 3800, 2026: 3900}), trail=TITLE)


def edge_scenarios(r: gr.Recorder) -> None:
    c = lambda s, **kw: cbyt_call(r, cbyt_args(s, **kw))  # noqa: E731
    c({}, base_year=2021)
    c({}, base_year=2021, base_override=5)
    c({2021: 50.0}, base_year=2021)
    c({2021: 50.0}, base_year=2021, trail=TITLE)
    c({2022: 60.5, 2023: 70.25}, base_year=2021)  # base year absent: base average 0.0
    c({2022: 60.5, 2023: 70.25}, base_year=2021, hwm_override=65)
    c({2020: 10, 2021: 50, 2019: 99}, base_year=2021)  # earlier years are never evaluated
    c({2021: 50, 2023: 53, 2026: 60, 2024: 10}, base_year=2021)  # gaps and out-of-order keys
    c({2026: 60, 2021: 50, 2023: 53, 2024: 10}, base_year=2021, trail=TITLE)
    for tr in (0, 1, 2, 3, 5, 7, 10, -1):
        c({2021: 100, 2022: 110, 2023: 120, 2024: 90, 2025: 130, 2026: 140}, base_year=2021, tranche_years=tr)
    c({2021: 100, 2022: 110, 2023: 105, 2024: 130, 2030: 160}, base_year=2021, tranche_years=3)
    for th in (0, 0.0, 2, 2.0, 10, 5.5, -1, 1e-9, NAN, INF, -INF):
        c({2021: 100, 2022: 102, 2023: 105, 2024: 99}, base_year=2021, threshold=th)
    for pj in (0, 0.0, 3500, 3500.0, 3500.5, 3501, -3500, 1e16, 1e300, 0.001, NAN, INF, 4000):
        c({2021: 100.5, 2022: 101, 2023: 102.5, 2024: 107.5}, base_year=2021, per_job=pj)
    for bo in (0, 0.0, 80, 80.0, 99.999, -5, 1e9, NAN, INF, 100, 100.0, 105):
        c({2021: 100, 2022: 105, 2023: 110.0, 2024: 105}, base_year=2021, base_override=bo)
    for ho in (0, 0.0, 105, 105.0, 110, 110.0, 150, -1, 104.999, INF, NAN, 1e9):
        c({2021: 100, 2022: 105, 2023: 110.0, 2024: 105}, base_year=2021, hwm_override=ho)
    for avg in (0, 0.0, -5, -0.0, 1e-300, 1e300, 1e308, INF, -INF, NAN, 100.00000000000001, 99.99999999999999):
        c({2021: 100, 2022: avg, 2023: 105}, base_year=2021)
    for half in (0.5, 1.5, 2.5, 3.5, 4.5, 0.005, 0.015, 0.025, 1.005, 2.675):
        c({2021: 10, 2022: 10 + half, 2023: 10 + 2 * half}, base_year=2021, threshold=0, per_job=half * 1000 + 0.5)
        c({2021: 10, 2022: 10 + half}, base_year=2021, threshold=0, per_job=1)
    c({2021: 100, 2022: 105, 2023: 110}, base_year=2021, benefit={2022: {"threshold": 2}, 2023: {"per_job_usd": 4000}})
    c({2021: 100, 2022: 105, 2023: 110}, base_year=2021, benefit={2022: {}, 2023: {"threshold": 50, "per_job_usd": 1.5}}, per_job=3500.0, threshold=2.0)
    c({2021: 100, 2022: 105, 2023: 110}, base_year=2021, benefit={})
    c({2021: 100, 2022: 105, 2023: 110}, base_year=2021, benefit={2020: {"threshold": 50}, 2024: {"threshold": 60}})
    c({2021: 100, 2022: 105, 2023: 110, 2024: 108}, base_year=2021, benefit={2022: {"threshold": 2.0, "per_job_usd": 3500}, 2023: {"threshold": 2, "per_job_usd": 3200.5},
                                                                           2024: {"threshold": 2, "per_job_usd": 4100}}, trail=TITLE)
    c({2021: 100, 2022: 105.5}, base_year=2021, state="ga")
    for st in ("", "ga", "Straße", "ǆa", "\U00010428x"):
        c({2021: 100, 2022: 105}, base_year=2021, state=st, trail=TITLE)
    c({2021: 100, 2022: 105}, base_year=0)
    c({0: 5, 1: 9}, base_year=0)
    c({-3: 5, -2: 9, -1: 10}, base_year=-3)
    c({2**40: 5.0, 2**40 + 1: 9.0}, base_year=2**40)
    # a series the tranche stair walks: dip below threshold, backfill, new high-water marks, window running past the data
    c({2020: 40, 2021: 44, 2022: 43, 2023: 41, 2024: 48, 2025: 47, 2026: 55, 2027: 40}, base_year=2020, trail=TITLE)
    c({2020: 40, 2021: 44, 2022: 43, 2023: 41, 2024: 48, 2025: 47, 2026: 55, 2027: 40}, base_year=2020, base_override=38, hwm_override=45.5)


def random_scenarios(r: gr.Recorder, rng: random.Random, n: int = 520) -> None:
    for _ in range(n):
        base = rng.randint(2015, 2024)
        span = rng.randint(0, 8)
        years = [y for y in range(base - rng.randint(0, 2), base + span + 1) if rng.random() < 0.88 or y == base]
        rng.shuffle(years)
        yearly = {y: rng.choice([round(rng.uniform(0, 90), 2), round(rng.uniform(35, 55), 2), 40, 40.0, 40.005, 41.995, rng.randint(0, 99), float(rng.randint(30, 50))]) for y in years}
        benefit = None
        if rng.random() < 0.55:
            ys = [y for y in range(base - 1, base + span + 3) if rng.random() < 0.8]
            benefit = {}
            for y in ys:
                d = {}
                if rng.random() < 0.9:
                    d["threshold"] = rng.choice([2, 2.0, 5.0, 10, 15.5, 0])
                if rng.random() < 0.9:
                    d["per_job_usd"] = rng.choice([3500, 3500.0, 4000.0, 1500.5, 0.0, 2999.99, 4100])
                benefit[y] = d
        a = cbyt_args(
            yearly, base_year=base, threshold=rng.choice([2, 2.0, 5.0, 10, 0.5, 0, 15.5]), per_job=rng.choice([3500, 3500.0, 4000.0, 1500.5, 0.0, 2999.99]),
            tranche_years=rng.choice([None, None, 5, 3, 1, 4, 6]), base_override=rng.choice([None, None, None, 12.5, 40, 80.0]),
            hwm_override=rng.choice([None, None, None, 30.0, 45, 60.5]), benefit=benefit, trail=TITLE if rng.random() < 0.3 else None,
            state=rng.choice(["GA", "ga", "NC", "sc"]))
        cbyt_call(r, a, columns=rng.random() < 0.6)


# ----------------------------------------------------------------------------- unit_trend


def unit(avg=..., mwh=..., **extra):
    u = dict(extra)
    if avg is not ...:
        u["average_headcount"] = avg
    if mwh is not ...:
        u["months_with_headcount"] = mwh
    return u


def agg_call(r: gr.Recorder, rows: list) -> None:
    r.call("aggregate_units", {"rows": rows}, lambda: ut.aggregate_units(copy.deepcopy(rows)))


def aggregate_scenarios(r: gr.Recorder, rng: random.Random) -> None:
    m = lambda base, step=0.0: [round(base + step * i, 2) for i in range(12)]  # noqa: E731
    agg_call(r, [])
    agg_call(r, [{"unit_id": "GA_1", "fein": "58-1", "month_totals": m(10, 0.5)}])
    agg_call(r, [{"unit_id": "GA_1", "fein": "58-1", "month_totals": m(10)}, {"unit_id": "GA_1", "fein": "58-2", "month_totals": m(2.5)}])
    agg_call(r, [{"unit_id": "GA_1", "fein": "58-2", "month_totals": m(1)}, {"unit_id": "GA_1", "fein": "58-1", "month_totals": m(1)},
                 {"unit_id": "GA_1", "fein": "58-2", "month_totals": m(1)}])
    agg_call(r, [{"Worksite_ID": "GA_9", "Entity_FEIN": "58-9", "month_totals": m(3)}, {"unit_id": "", "Worksite_ID": "GA_8", "month_totals": m(3)}])
    agg_call(r, [{"unit_id": "b", "fein": "x", "month_totals": m(1)}, {"unit_id": "a", "fein": "x", "month_totals": m(1)}, {"unit_id": "B", "month_totals": m(1)},
                 {"unit_id": "\u00e9", "month_totals": m(1)}, {"unit_id": "\U0001f600", "month_totals": m(1)}, {"unit_id": "\uff21", "month_totals": m(1)}])
    agg_call(r, [{"month_totals": [1] * 12}, {"unit_id": None, "month_totals": [1.5] * 12}, {"unit_id": 7, "month_totals": [2] * 12}, {"unit_id": 7.5, "month_totals": [0] * 12}])
    agg_call(r, [{"unit_id": "A", "month_totals": [1, 2, 3]}, {"unit_id": "B", "month_totals": []}, {"unit_id": "C", "month_totals": None}, {"unit_id": "D"}])
    agg_call(r, [{"unit_id": "A", "month_totals": list(range(20))}, {"unit_id": "B", "month_totals": [0.0] * 12}, {"unit_id": "C", "month_totals": [-1.5, 0.001] * 6}])
    agg_call(r, [{"unit_id": "A", "month_totals": ["1.5", "2", " 3 ", True, False, 4, 5.5, 6, 7, 8, 9, 10]}])
    agg_call(r, [{"unit_id": "A", "month_totals": [0.1] * 12}, {"unit_id": "A", "month_totals": [0.2] * 12}, {"unit_id": "A", "month_totals": [0.7] * 12}])
    agg_call(r, [{"unit_id": "A", "month_totals": [1e308] * 12}, {"unit_id": "A", "month_totals": [1e308] * 12}])
    agg_call(r, [{"unit_id": "A", "month_totals": [NAN] + [1] * 11}, {"unit_id": "B", "month_totals": [INF] + [1] * 11}])
    agg_call(r, [{"unit_id": "A", "month_totals": ["abc"] * 12}])
    agg_call(r, [{"unit_id": "A", "month_totals": [None] * 12}])
    agg_call(r, [{"unit_id": "A", "month_totals": [[1]] * 12}])
    agg_call(r, [{"unit_id": "A", "fein": 5, "month_totals": [1] * 12}, {"unit_id": "A", "fein": None, "month_totals": [1] * 12}, {"unit_id": "A", "fein": "", "month_totals": [1] * 12}])
    agg_call(r, [{"unit_id": "A", "fein": "z", "month_totals": [0.005] * 12}, {"unit_id": "A", "fein": "y", "month_totals": [0.015] * 12}])
    agg_call(r, [{"unit_id": "x", "month_totals": [2.675] * 12}, {"unit_id": "x", "month_totals": [1.005] * 12}])
    for _ in range(120):
        rows = []
        for _ in range(rng.randint(1, 9)):
            rows.append({"unit_id": rng.choice(["GA_1", "GA_2", "GA_3", "TN_1", "\u00e9"]), "fein": rng.choice(["58-1", "58-2", "58-3", ""]),
                         "month_totals": [rng.choice([0, 0.0, round(rng.uniform(0, 40), rng.choice([0, 2, 4])), round(rng.uniform(0, 3), 3)]) for _ in range(rng.choice([12, 12, 12, 11, 13, 0]))]})
        agg_call(r, rows)


def series_scenarios(r: gr.Recorder, rng: random.Random) -> None:
    per = lambda *ys: [[y, [{"unit_id": u, "average_headcount": h} for u, h in us]] for y, us in ys]  # noqa: E731
    cases = [[], per((2021, [])), per((2021, [("A", 1.5), ("B", 2.5)]), (2022, [("B", 3.0)])), per((2022, [("B", 3.0), ("A", 2)]), (2021, [("A", 1.5)])),
             per((2021, [("A", 1)]), (2021, [("A", 2)])), per((2021, [(7, 1)]))]
    for c in cases:
        def run(c=c):
            data = {y: copy.deepcopy(us) for y, us in c}
            return ut.build_unit_series(data)
        r.call("build_unit_series", {"per_year": c}, run)
    r.call("build_unit_series", {"per_year": [[2021, [{"average_headcount": 1}]]]}, lambda: ut.build_unit_series({2021: [{"average_headcount": 1}]}))
    for _ in range(40):
        ys = rng.sample(range(2019, 2027), rng.randint(0, 5))
        c = [[y, [{"unit_id": rng.choice(["A", "B", "C", "\u00e9"]), "average_headcount": round(rng.uniform(0, 60), 2)} for _ in range(rng.randint(0, 4))]] for y in ys]
        r.call("build_unit_series", {"per_year": c}, lambda c=c: ut.build_unit_series({y: copy.deepcopy(us) for y, us in c}))


def infer_call(r: gr.Recorder, unit_years: dict, reachable=None) -> None:
    a = {"unit_years": pairs(unit_years), "reachable": pairs(reachable)}

    def run():
        kw = {} if reachable is None else {"reachable_by_year": reachable}
        return ut.infer_base_year(unit_years, **kw)
    r.call("infer_base_year", a, run)


def infer_scenarios(r: gr.Recorder, rng: random.Random) -> None:
    infer_call(r, {})
    infer_call(r, {}, {2021: 5})
    infer_call(r, {2021: unit(1.0, 12)})
    infer_call(r, {2021: unit(1.0, 11), 2022: unit(1.0, 12)})
    infer_call(r, {2021: unit(1.0, 11), 2022: unit(1.0, 12)}, {2021: 11})
    infer_call(r, {2021: unit(1.0, 3), 2022: unit(1.0, 4)})
    infer_call(r, {2023: unit(1.0, 3), 2021: unit(1.0, 4), 2022: unit(1.0, 2)})
    infer_call(r, {2023: unit(1.0, 12), 2021: unit(1.0, 12)})
    infer_call(r, {2021: unit(1.0, ...), 2022: unit(1.0, None), 2023: unit(1.0, 0)}, {2022: 0, 2023: 0})
    infer_call(r, {2021: unit(1.0, 11.9), 2022: unit(1.0, "12"), 2023: unit(1.0, True)}, {2021: 11})
    infer_call(r, {2021: unit(1.0, 12.0)})
    infer_call(r, {2021: unit(1.0, "x")})
    infer_call(r, {2021: unit(1.0, [1])})
    infer_call(r, {2021: unit(1.0, 7)}, {2021: 7, 2022: 12})
    infer_call(r, {2021: unit(1.0, 7)}, {})
    for _ in range(80):
        ys = rng.sample(range(2018, 2027), rng.randint(1, 6))
        uy = {y: unit(round(rng.uniform(0, 50), 2), rng.choice([0, 3, 6, 10, 11, 12, 12])) for y in ys}
        reach = {y: rng.choice([6, 10, 11, 12]) for y in ys if rng.random() < 0.5} if rng.random() < 0.7 else None
        infer_call(r, uy, reach)


def status_scenarios(r: gr.Recorder) -> None:
    for ty in (2019, 2021, 2022, 2023):
        for base in (None, 2021, 2022):
            for q in (True, False):
                for mwh in (-1, 0, 1, 5, 6, 11, 12, 13):
                    for mr in (None, 6, 11, 12):
                        a = {"tax_year": ty, "base_year": base, "qualified": q, "months_with_headcount": mwh, "months_reachable": mr}

                        def run(a=a):
                            kw = {} if a["months_reachable"] is None else {"months_reachable": a["months_reachable"]}
                            return ut.unit_status(tax_year=a["tax_year"], base_year=a["base_year"], qualified=a["qualified"], months_with_headcount=a["months_with_headcount"], **kw)
                        r.call("unit_status", a, run)


def trend_call(r: gr.Recorder, unit_years: dict, *, base_year, threshold=2.0, per_job=3500.0, tranche_years=None, benefit=None, trail=None, state="GA") -> None:
    a = {"state": state, "unit_years": pairs(unit_years), "base_year": base_year, "threshold": threshold, "per_job_usd": per_job, "tranche_years": tranche_years,
         "benefit": pairs(benefit), "trail": trail}

    def run():
        kw = {}
        if tranche_years is not None:
            kw["tranche_years"] = tranche_years
        if benefit is not None:
            kw["benefit_by_year"] = benefit
        out = traced(trail, lambda: result_tree(ut.unit_trend(unit_years, state=state, base_year=base_year, threshold=threshold, per_job_usd=per_job, **kw)))
        return {**out["result"], **({"trail": out["trail"]} if "trail" in out else {})}
    r.call("unit_trend", a, run)

    def cols():
        res = ut.unit_trend(unit_years, state=state, base_year=base_year, threshold=threshold, per_job_usd=per_job,
                            **({"tranche_years": tranche_years} if tranche_years is not None else {}), **({"benefit_by_year": benefit} if benefit is not None else {}))
        return ut.tranche_columns(res, list(range(base_year - 1, base_year + 9)))
    r.call("unit_trend_columns", a, cols)


def unit_trend_scenarios(r: gr.Recorder, rng: random.Random) -> None:
    trend_call(r, {2021: unit(100), 2022: unit(105), 2023: unit(104)}, base_year=2021, threshold=2, per_job=3500)
    trend_call(r, {2021: unit(100.0), 2022: unit(105.0)}, base_year=2021, trail=TITLE)
    trend_call(r, {2021: unit(...), 2022: unit(None), 2023: unit(0), 2024: unit(""), 2025: unit(False), 2026: unit(5.5)}, base_year=2021)
    trend_call(r, {2021: unit("100"), 2022: unit("105.5"), 2023: unit(True), 2024: unit(" 7 ")}, base_year=2021)
    trend_call(r, {2021: unit("abc"), 2022: unit(5)}, base_year=2021)
    trend_call(r, {2021: unit([1]), 2022: unit(5)}, base_year=2021)
    trend_call(r, {2021: unit(100), 2022: unit(105), 2023: unit(112)}, base_year=2021, threshold=2.0, per_job=3500.0, tranche_years=3,
               benefit={2021: {"threshold": 2.0, "per_job_usd": 3000.0}, 2022: {"threshold": 2.0, "per_job_usd": 3500.0}, 2023: {"threshold": 10.0, "per_job_usd": 4000.0}}, trail=TITLE)
    trend_call(r, {2021: unit(100), 2022: unit(105)}, base_year=2021, benefit={})
    for _ in range(80):
        ys = list(range(2019, 2019 + rng.randint(1, 8)))
        base = rng.choice(ys)
        uy = {y: unit(rng.choice([round(rng.uniform(0, 80), 2), 40.0, 40.005, 41.995, rng.randint(0, 80), None, 0]), 12, total=1.0, feins=["x"]) for y in ys}
        per_year = {y: {"threshold": rng.choice([2.0, 5.0]), "per_job_usd": rng.choice([3500.0, 4000.0])} for y in ys if rng.random() < 0.7} if rng.random() < 0.5 else None
        trend_call(r, uy, base_year=base, threshold=rng.choice([2.0, 5.0, 2]), per_job=rng.choice([3500.0, 3500, 4000.0]), tranche_years=rng.choice([None, 5, 3]),
                   benefit=per_year, trail=TITLE if rng.random() < 0.3 else None)


# ----------------------------------------------------------------------------- realistic series from the production engines

GA_PACKS = {y: sc.load_pack("GA_JTC", y) for y in range(2019, 2027)}


def shifted_rows(base_rows: list[dict], years_ahead: int, rng: random.Random, keep: float) -> list[dict]:
    out = []
    for row in base_rows:
        if keep < 1.0 and rng.random() > keep:
            continue
        shifted = dict(row)
        for k in ("Pay_Period_Start", "Pay_Period_End", "Pay_Date"):
            d = date.fromisoformat(row[k]) + timedelta(days=364 * years_ahead)
            shifted[k] = d.isoformat()
        out.append(shifted)
    return out


def engine_calls(r: gr.Recorder, rng: random.Random) -> None:
    """Per method: aggregate -> pivot -> base year -> trend -> columns over the production engines' real summaries."""
    base_rows = sc.csv_rows()
    for method in ("min_max", "pay_period"):
        for variant in range(3):
            first = 2020 + variant
            years = list(range(first, first + 3 + variant))
            per_year_units, reachable_by_year = {}, {}
            for i, ty in enumerate(years):
                keep = [1.0, 0.8, 0.55][(i + variant) % 3]
                rows = shifted_rows(base_rows, ty - 2025, rng, keep)
                pack = GA_PACKS.get(ty) or GA_PACKS[2025]
                params = {"tax_year": ty, "analysis_start_month": f"{ty}-01-01", "pack": pack, "with_trail": False, "fiscal_window": [f"{ty}-01-01", f"{ty}-12-31"]}
                try:
                    result, _ = engine_io._run_method(method, {"rows": rows, "params": params})
                except Exception:
                    continue
                unreached = oz.unreachable_months(rows, result.months)
                summary = [{"unit_id": row["Worksite_ID"], "fein": row["Entity_FEIN"], **row}
                           for row in rollup_matrix_by_two_fields(result.employee_unit_matrix, "Worksite_ID", "Entity_FEIN")]
                agg_call(r, summary)
                units = ut.aggregate_units(summary)
                per_year_units[ty] = units
                reachable_by_year[ty] = len(result.months) - len(unreached)
            if not per_year_units:
                continue
            r.call("build_unit_series", {"per_year": [[y, u] for y, u in per_year_units.items()]}, lambda p=per_year_units: ut.build_unit_series(p))
            series = ut.build_unit_series(per_year_units)
            ys = sorted(per_year_units)
            benefit = {y: gut._year_benefit("GA_JTC", y) for y in ys}
            for unit_id, unit_years in sorted(series.items()):
                infer_call(r, unit_years, reachable_by_year)
                base_year = ut.infer_base_year(unit_years, reachable_by_year=reachable_by_year)
                per_year = {y: {"threshold": b["threshold"], "per_job_usd": b["per_job_usd"]} for y, b in benefit.items()}
                trend_call(r, unit_years, base_year=base_year, threshold=benefit[ys[-1]]["threshold"], per_job=benefit[ys[-1]]["per_job_usd"],
                           tranche_years=benefit[ys[-1]]["benefit_period_years"], benefit=per_year, trail=TITLE if rng.random() < 0.25 else None)
                other = rng.choice(ys)
                trend_call(r, unit_years, base_year=other, threshold=2.0, per_job=3500.0, benefit=per_year if rng.random() < 0.5 else None)
                for ty, u in unit_years.items():
                    for q in (True, False):
                        mr = reachable_by_year.get(ty, 12)
                        a = {"tax_year": ty, "base_year": base_year, "qualified": q, "months_with_headcount": u["months_with_headcount"], "months_reachable": mr}
                        r.call("unit_status", a, lambda a=a: ut.unit_status(**{**a}))


# ----------------------------------------------------------------------------- designation registry and helpers


def registry_spec(legacy, source, synthetic_default, synthetic) -> dict:
    return {"legacy": [[k, v] for k, v in legacy.items()], "source": [[c, u, v] for (c, u), v in source.items()],
            "synthetic_default": synthetic_default, "synthetic": synthetic}


@contextlib.contextmanager
def registry(spec: dict):
    saved = (dz._DESIGNATION_HISTORY, dz._SOURCE_DESIGNATIONS, dz._SYNTHETIC_GA_DEFAULT, config.synthetic_environment)
    dz._DESIGNATION_HISTORY = {k: v for k, v in spec["legacy"]}
    dz._SOURCE_DESIGNATIONS = {(c, u): v for c, u, v in spec["source"]}
    dz._SYNTHETIC_GA_DEFAULT = spec["synthetic_default"]
    config.synthetic_environment = lambda: spec["synthetic"]
    try:
        yield
    finally:
        dz._DESIGNATION_HISTORY, dz._SOURCE_DESIGNATIONS, dz._SYNTHETIC_GA_DEFAULT, config.synthetic_environment = saved


def production_registry(synthetic: bool) -> dict:
    return registry_spec(copy.deepcopy(dz._DESIGNATION_HISTORY), copy.deepcopy(dz._SOURCE_DESIGNATIONS), copy.deepcopy(dz._SYNTHETIC_GA_DEFAULT), synthetic)


def entry(year, tier=1, designation="T1", mnj=2):
    return {"year": year, "tier": tier, "designation": designation, "min_new_jobs": mnj}


def custom_registry(synthetic: bool = False) -> dict:
    legacy = {
        "GA_B": [entry(2020, 2, "T2", 10), entry(2023, 1, "T1", 2), entry(2025, 3, "T3", 15)],
        "GA_A": [entry(2022, 1, "T1", 2)],
        "GA_EMPTY": [],
        "NC_X": [entry(2021, 1, "Tier 1 \u2014 Standard", 2), entry(2024, 1, "Tier 1 \u2014 Standard", 2)],
        "ga_lower": [entry(2021), entry(2025, 2, "T2", 10)],
        "GA_SAME": [entry(2019), entry(2021), entry(2023)],
        "GA_LATE": [entry(2030, 4, "T4", 25)],
        "GA_\u00e9": [entry(2020, 1, "T1", 2), entry(2024, 1, "T1 B40", 2)],
        "GA_TIER": [entry(2021, 1, "T1", 2), entry(2023, 2, "T1", 2)],
        "GA_UNSORTED": [entry(2025, 2, "T2", 10), entry(2021, 1, "T1", 2), entry(2019, 3, "T3", 15)],
        "GA_F": [{"year": 2021, "tier": 1, "designation": "T1", "min_new_jobs": 2.5}, {"year": 2024, "tier": 1, "designation": "T1", "min_new_jobs": 2}],
    }
    source = {(2001, "GA_GA-013"): [entry(2020), entry(2021, 1, "T1 B40"), entry(2022)], (2002, "GA_GA-013"): [entry(2020, 3, "T3", 15)], (7, "NC_N1"): [entry(2021)]}
    return registry_spec(legacy, source, [entry(2020)], synthetic)


def all_registries() -> dict:
    return {"production": production_registry(False), "production_synthetic": production_registry(True), "custom": custom_registry(False), "custom_synthetic": custom_registry(True),
            "empty": registry_spec({}, {}, [], False), "empty_synthetic": registry_spec({}, {}, [], True)}


def registry_calls(r: gr.Recorder) -> None:
    specs = all_registries()
    for name, spec in specs.items():
        def call(fn, args, fnrun, name=name, spec=spec):
            def run():
                with registry(spec):
                    return fnrun()
            r.call(fn, {"registry": name, **args}, run)
        for state in ("GA", "ga", "NC", "SC", "", "G", "GA_", "TN"):
            for ty, base in ((2023, 2021), (2025, 2021), (2021, 2021), (2019, 2021), (2030, 2021), (2024, None), (2022, 2020), (2026, 2025), (2020, 2024)):
                a = {"state": state, "tax_year": ty, "base_year": base}

                def run(a=a):
                    kw = {} if a["base_year"] is None else {"base_year": a["base_year"]}
                    return dsg.detect_designation_splits(a["state"], a["tax_year"], **kw)
                call("detect_designation_splits", a, run)
                a2 = {**a, "trail": TITLE}
                call("detect_designation_splits_trail", a2, lambda a=a: traced(TITLE, lambda: dsg.detect_designation_splits(a["state"], a["tax_year"], **({} if a["base_year"] is None else {"base_year": a["base_year"]}))))
        for unit_id in ("GA_B", "GA_A", "GA_EMPTY", "NC_X", "ga_lower", "GA_GA-013", "GA_GA-001", "GA_ATL_HQ", "GA_MAC_OPS", "GA_1134481", "", "GA_\u00e9", "GA_F", "NC_N1", "TN_1", "GA_LATE", "GA_SAME", "GA_TIER", "GA_UNSORTED"):
            for cid in (None, 1001, 2001, 2002, 2003, 7, 0, -1, 10**12):
                call("designation_history", {"unit_id": unit_id, "client_id": cid}, lambda u=unit_id, c=cid: dz.designation_history(u, c))
                for ty in (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2030):
                    call("_designation_at", {"unit_id": unit_id, "tax_year": ty, "client_id": cid}, lambda u=unit_id, t=ty, c=cid: gut._designation_at(u, t, c))
        call("all_designations", {}, lambda: dz.all_designations())
        call("disc_meta", {}, lambda: dz.disc_meta())


# ----------------------------------------------------------------------------- negotiated overrides


class Fixed(datetime):
    fixed = None

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


def negotiated_session(r: gr.Recorder, ops: list) -> None:
    """One ordered session over the module's store: ``[op, args]`` steps, each with its own recorded result or exception."""
    def run():
        neg._reset_for_tests()
        saved, neg.datetime = neg.datetime, Fixed
        steps = []
        try:
            for op, a in ops:
                try:
                    if op == "register":
                        Fixed.fixed = datetime(*a["now"], tzinfo=timezone.utc)
                        kw = {k: v for k, v in a.items() if k not in ("state", "now")}
                        out = neg.register_override(a["state"], **kw)
                    elif op == "resolve":
                        out = neg.resolve_override(a["state"], *( [a["worksite"]] if "worksite" in a else []))
                    elif op == "list":
                        out = neg.list_overrides()
                    else:
                        raise AssertionError(op)
                    steps.append({"op": op, "out": gr.enc(copy.deepcopy(out))})
                except Exception as e:
                    steps.append({"op": op, "err": type(e).__name__, "msg": str(e)})
        finally:
            neg.datetime = saved
            neg._reset_for_tests()
        return steps
    r.call("negotiated_session", {"ops": ops}, run)


def negotiated_scenarios(r: gr.Recorder, rng: random.Random) -> None:
    t = [2026, 3, 1, 9, 30, 15, 999999]
    reg = lambda state, now=t, **kw: ("register", {"state": state, "now": now, **kw})  # noqa: E731
    res = lambda state, *w: ("resolve", {"state": state, **({"worksite": w[0]} if w else {})})  # noqa: E731
    lst = ("list", {})
    negotiated_session(r, [lst, res("SC"), res("SC", "W1")])
    negotiated_session(r, [reg("SC", wage_standard_weekly=720.0, min_jobs=100, source="agreement", note="Tractor Supply-style deal"), lst, res("SC"), res("sc"), res("SC", "W1")])
    negotiated_session(r, [reg("SC"), reg("SC", source="x", min_jobs=1), reg("SC", source="agreement"), reg("SC", min_jobs=0), reg("SC", wage_standard_weekly=0.0), lst])
    negotiated_session(r, [reg("GA", wage_standard_weekly=100000.0, source="agreement"), reg("ga", worksite_id="W9", min_jobs=5), reg("GA", worksite_id="", min_jobs=7), lst,
                           res("GA"), res("GA", "W9"), res("ga", "W9"), res("GA", "other"), res("GA", ""), res("GA", None)])
    negotiated_session(r, [reg("GA", min_jobs=1, now=[2024, 2, 29, 23, 59, 59, 500000]), reg("GA", min_jobs=2, now=[2023, 12, 31, 0, 0, 0, 0], effective_years=3), lst,
                           reg("GA", min_jobs=3, now=[1, 1, 1, 0, 0, 0, 1], effective_years=0), reg("GA", min_jobs=4, now=[9999, 12, 31, 23, 59, 59, 999999], note=""), lst])
    negotiated_session(r, [reg("Straße", min_jobs=1), reg("\u01c6", min_jobs=1, worksite_id="\u01c6"), reg("tn", min_jobs=1.5, wage_standard_weekly=3), lst, res("STRASSE"), res("\u01c5")])
    negotiated_session(r, [reg("NY", wage_standard_weekly=-5, min_jobs=-1), reg("NY", wage_standard_weekly=float("nan")), reg("NY", wage_standard_weekly=INF, min_jobs=2**40), lst])
    negotiated_session(r, [reg("A", worksite_id="W", min_jobs=1), reg("A", min_jobs=2), reg("A", worksite_id="W", min_jobs=3), lst, res("A", "W"), res("A")])
    for _ in range(40):
        ops = []
        for _ in range(rng.randint(1, 9)):
            k = rng.choice(["register", "register", "resolve", "list"])
            st = rng.choice(["GA", "ga", "SC", "NY"])
            if k == "register":
                kw = {}
                if rng.random() < 0.8:
                    kw["wage_standard_weekly"] = rng.choice([720.0, 18, 0, 0.0, 100000.0, 17.5])
                if rng.random() < 0.6:
                    kw["min_jobs"] = rng.choice([100, 5, 0, 2.5])
                if rng.random() < 0.7:
                    kw["worksite_id"] = rng.choice(["W1", "W2", "", None])
                if rng.random() < 0.7:
                    kw["source"] = rng.choice(["agreement", "self_service", "x", ""])
                if rng.random() < 0.4:
                    kw["effective_years"] = rng.choice([1, 5, 0])
                if rng.random() < 0.4:
                    kw["note"] = rng.choice(["n", "", "\u00e9"])
                ops.append(reg(st, now=[rng.randint(2020, 2030), rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59), rng.randint(0, 999999)], **kw))
            elif k == "resolve":
                ops.append(res(st, rng.choice(["W1", "W2", "W3", ""])) if rng.random() < 0.7 else res(st))
            else:
                ops.append(lst)
        negotiated_session(r, ops)


# ----------------------------------------------------------------------------- reconcile


def reconcile_call(r: gr.Recorder, bench, comp, **kw) -> None:
    r.call("reconcile", {"benchmark": bench, "computed": comp, **kw}, lambda: rec.reconcile(copy.deepcopy(bench), copy.deepcopy(comp), **kw))


def reconcile_scenarios(r: gr.Recorder, rng: random.Random) -> None:
    bench = [{"key": "GA", "average_headcount": 60.59}, {"key": "SC", "average_headcount": 5.12}, {"key": "NC", "average_headcount": 24.08}, {"key": "VA", "average_headcount": 4.42}]
    comp = [{"key": "GA", "average_headcount": 60.59}, {"key": "SC", "average_headcount": 5.40}, {"key": "NC", "average_headcount": 30.00}, {"key": "TN", "average_headcount": 1.83}]
    reconcile_call(r, bench, comp, tolerance=0.5)
    reconcile_call(r, bench, comp)
    reconcile_call(r, [bench[0]], [comp[0]])
    reconcile_call(r, [], [])
    reconcile_call(r, bench, [])
    reconcile_call(r, [], comp)
    for tol in (0, 0.0, 1, 0.5, 0.25, 1e-9, 1e-4, -1, NAN, INF, 10**15, 0.2999999999999999):
        reconcile_call(r, bench, comp, tolerance=tol)
    for b, c in ((1.0, 1.5), (1.0, 0.5), (1.0, 1.0 + 1e-12), (1.0, 1.0 - 1e-12), (1.0, 1.00004), (1.0, 1.00005), (1.0, 1.00015), (0.1, 0.3), (2.675, 2.676), (1e16, 1e16 + 2),
                 (1e308, -1e308), (INF, INF), (INF, 1.0), (NAN, 1.0), (1.0, NAN), (-0.0, 0.0), (5, 5), (5, 6), (True, False), ("2.5", 3), (" 4 ", "4.4"), ("1e3", 1000), (0.5, 1.0), (2.0, 2.5)):
        for tol in (0.5, 0.25, 0):
            reconcile_call(r, [{"key": "k", "average_headcount": b}], [{"key": "k", "average_headcount": c}], tolerance=tol)
    reconcile_call(r, [{"key": 1, "average_headcount": 1}, {"key": None, "average_headcount": 2}, {"key": 1.5, "average_headcount": 3}, {"key": True, "average_headcount": 4}],
                   [{"key": "1", "average_headcount": 1}, {"key": "None", "average_headcount": 2}, {"key": "1.5", "average_headcount": 3.5}, {"key": "True", "average_headcount": 4.0}])
    reconcile_call(r, [{"key": "\u00e9", "average_headcount": 1}, {"key": "Z", "average_headcount": 1}, {"key": "a", "average_headcount": 1}, {"key": "\U0001f600", "average_headcount": 1}, {"key": "\uff21", "average_headcount": 1}, {"key": "B", "average_headcount": 1}],
                   [{"key": "\u01c6", "average_headcount": 1}, {"key": "b", "average_headcount": 1}, {"key": "\ud7ff", "average_headcount": 1}, {"key": "\ue000", "average_headcount": 1}])
    reconcile_call(r, [{"key": "a", "average_headcount": 1}, {"key": "a", "average_headcount": 2}], [{"key": "a", "average_headcount": 3}, {"key": "a", "average_headcount": 4}])
    reconcile_call(r, [{"key": "a"}, {"average_headcount": 1}, {"key": "b", "average_headcount": 1}, {}], [{"average_headcount": 1}, {"key": "b"}, {"key": "c", "average_headcount": 1, "extra": 1}])
    reconcile_call(r, [{"state": "GA", "v": 1.0}], [{"state": "GA", "v": 1.2}], key="state", value="v")
    reconcile_call(r, [{"state": "GA", "v": 1.0}], [{"state": "GA", "v": 1.2}], key="key", value="v")
    reconcile_call(r, [{"k": "a", "v": 1.0}], [{"k": "a", "v": 1.0, "average_headcount": 99}], key="k", value="v", tolerance=2)
    reconcile_call(r, [{"key": "a", "average_headcount": None}], [])
    reconcile_call(r, [], [{"key": "a", "average_headcount": None}])
    reconcile_call(r, [{"key": "a", "average_headcount": "abc"}], [])
    reconcile_call(r, [], [{"key": "a", "average_headcount": "x"}], tolerance=1)
    reconcile_call(r, [{"key": "a", "average_headcount": [1]}], [])
    reconcile_call(r, [{"key": "a", "average_headcount": {}}], [])
    reconcile_call(r, [{"key": "a", "average_headcount": "abc"}], [{"key": "a", "average_headcount": None}])
    reconcile_call(r, [{"key": "a", "average_headcount": 1}], [{"key": "a", "average_headcount": 10**400}])
    reconcile_call(r, [{"key": "a", "average_headcount": 10**20}], [{"key": "a", "average_headcount": 10**20 + 1}])
    for _ in range(120):
        keys = rng.sample(["GA", "SC", "NC", "VA", "TN", "AL", "FL", "\u00e9", "ga"], rng.randint(0, 7))
        b = [{"key": k, "average_headcount": round(rng.uniform(0, 70), rng.choice([0, 2, 4]))} for k in keys if rng.random() < 0.8]
        c = []
        for row in b:
            if rng.random() < 0.8:
                c.append({"key": row["key"], "average_headcount": round(row["average_headcount"] + rng.choice([0, 0, 0.5, -0.5, 0.2, 1e-12, 3, -0.4999, 0.5001]), rng.choice([2, 4, 6]))})
        for k in rng.sample(keys, min(len(keys), 2)):
            if rng.random() < 0.5:
                c.append({"key": k + "x", "average_headcount": rng.uniform(0, 70)})
        rng.shuffle(c)
        reconcile_call(r, b, c, tolerance=rng.choice([0.5, 0.25, 1, 0.0, 2.5]))


# ----------------------------------------------------------------------------- get_unit_trend helpers


SCRATCH = Path(__file__).resolve().parent / ".scratch-baseyear"
LAB_YEAR_EDITS = {
    2019: lambda p: p["benefit"].pop("benefit_period_years"),
    2020: lambda p: p["benefit"].update(benefit_period_years=0),
    2021: lambda p: p.update(benefit=None, thresholds=None),
    2022: lambda p: (p.update(thresholds={}), p["benefit"].update(amount_per_qualifying_job_usd=0)),
    2023: lambda p: (p["thresholds"].update(minimum_new_jobs="3"), p["benefit"].update(amount_per_qualifying_job_usd="4000.5", benefit_period_years="7")),
    2024: lambda p: (p["thresholds"].update(minimum_new_jobs=2), p["benefit"].update(amount_per_qualifying_job_usd=3500, benefit_period_years=4.9)),
    2025: lambda p: (p["thresholds"].update(minimum_new_jobs=None), p["benefit"].update(amount_per_qualifying_job_usd=None, benefit_period_years=None)),
}


def lab_files() -> dict:
    """The shipped Georgia year packs with the shapes the live packs never have (absent, zero, null, text and float values); 2026 is deleted."""
    import json
    files = {}
    for year, edit in LAB_YEAR_EDITS.items():
        pack = json.loads((BACKEND / "rules" / "ga_jtc" / f"{year}.json").read_text(encoding="utf-8"))
        edit(pack)
        files[f"ga_jtc/{year}.json"] = json.dumps(pack)
    files["ga_jtc/2026.json"] = None
    return files


@contextlib.contextmanager
def world(name: str, files: dict):
    import os
    import shutil
    if name == "shipped":
        yield
        return
    d = SCRATCH / name
    shutil.copytree(BACKEND / "rules", d)
    for rel, text in files.items():
        p = d / rel
        if text is None:
            p.unlink(missing_ok=True)
        else:
            p.write_bytes(text.encode("utf-8"))
    saved = {k: os.environ.pop(k, None) for k in ("RULES_DIR", "PROGRAM_REGISTRY_FILE")}
    os.environ["RULES_DIR"] = str(d.resolve())
    try:
        yield
    finally:
        os.environ.pop("RULES_DIR", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(SCRATCH, ignore_errors=True)


def worlds() -> dict:
    return {"shipped": {"files": {}, "registry_file": None}, "lab": {"files": lab_files(), "registry_file": None}}


def helper_calls(r: gr.Recorder) -> None:
    r.call("_MIN_REACHABLE_MONTHS", {}, lambda: gut._MIN_REACHABLE_MONTHS)
    codes = list(cm.PROGRAM_CODE_TO_PACK)
    names = codes + sorted(set(cm.STATE_TO_PACK)) + ["", "ZZ", "zz", "ga", "ga_jtc", "GA_JTC ", "XX_UNKNOWN", "nope.json", "GA_JTC.json"]
    for name, spec in worlds().items():
        with world(name, spec["files"]):
            for n in names:
                r.call("_candidate_years", {"world": name, "state_or_program": n}, lambda n=n: gut._candidate_years(n))
            for code in codes + ["ZZ_NONE", "", "ga_jtc"]:
                for ty in (None, 1999, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2030, 0, -1):
                    r.call("_year_benefit", {"world": name, "program_code": code, "tax_year": ty}, lambda c=code, t=ty: gut._year_benefit(c, t))

# ----------------------------------------------------------------------------- build


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    r = gr.Recorder()
    test_scenarios(r)
    edge_scenarios(r)
    random_scenarios(r, rng)
    aggregate_scenarios(r, rng)
    series_scenarios(r, rng)
    infer_scenarios(r, rng)
    status_scenarios(r)
    unit_trend_scenarios(r, rng)
    engine_calls(r, rng)
    registry_calls(r)
    negotiated_scenarios(r, rng)
    reconcile_scenarios(r, rng)
    helper_calls(r)
    meta = {"registries": all_registries(), "worlds": worlds()}
    print(f"{len(r.lines)} calls, {r.errors} errors: {r.counts}", file=sys.stderr)
    return gr.serialise(r, meta, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("baseyear", DEFAULT_OUT, SEED, build))
