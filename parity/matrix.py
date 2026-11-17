"""The scenario matrix: datasets plus every request the golden exporter runs through the oracle."""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import scenarios as sc
from scenarios import BASE_PACK, iso, row, with_pack

PROGRAM_YEARS_DEFAULT = [2023, 2024]
GA_YEARS = list(range(2019, 2027))
RANDOM_COUNT = 700


def _derived_datasets(base: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    out["csv"] = base
    out["csv_typed"] = sc.typed(base)
    dup = []
    for i, r in enumerate(base):
        dup.append(r)
        if i % 47 == 0:
            d = dict(r)
            d["Hours_Worked"] = "0.25"
            d["Gross_Wages"] = "3.1"
            dup.append(d)
    out["csv_dup"] = dup
    codes = ["Regular", "Overtime", "Bonus", "Commission", "Mileage", "Expense_Reimbursement", "Relocation", "Weird"]
    out["csv_codes"] = [{**r, "Pay_Code": codes[(i * 7 + len(r["Employee_ID"])) % len(codes)]} for i, r in enumerate(base)]
    blank = []
    for i, r in enumerate(base):
        r = dict(r)
        if i % 211 == 0:
            r["Hours_Worked"] = ""
        if i % 307 == 0:
            r["Gross_Wages"] = None
        blank.append(r)
    out["csv_blanks"] = blank
    out["csv_state_cells"] = [{**r, "Work_State": r["Worksite_ID"][:2].lower() if i % 3 else " " + r["Worksite_ID"][:2] + " "} for i, r in enumerate(base)]
    shifted = []
    for r in base:  # whole file shifted to a mid-month, non-calendar fiscal year (53-week style window)
        shifted.append({**r,
                        "Pay_Period_Start": iso(date.fromisoformat(r["Pay_Period_Start"]) - timedelta(days=161)),
                        "Pay_Period_End": iso(date.fromisoformat(r["Pay_Period_End"]) - timedelta(days=161)),
                        "Pay_Date": iso(date.fromisoformat(r["Pay_Date"]) - timedelta(days=161))})
    out["csv_shifted"] = shifted
    return out


def build() -> tuple[dict[str, list[dict]], list[dict]]:
    rng = random.Random(sc.SEED)
    base = sc.csv_rows()
    datasets = _derived_datasets(base)
    edge = sc.edge_datasets()
    for k, v in edge.items():
        datasets["edge_" + k] = v
    scen: list[dict] = []

    def add(sid: str, op: str, dataset: str | None, params: dict | None = None, rows: list[dict] | None = None) -> None:
        s: dict[str, Any] = {"id": sid, "op": op, "params": params or {}}
        if dataset is not None:
            s["dataset"] = dataset
        if rows is not None:
            s["rows"] = rows
        scen.append(s)

    from tools import credit_math as cm
    # --- every programme pack x years x both methods x calendar windows on the committed synthetic CSV
    for code in cm.PROGRAM_CODE_TO_PACK:
        years = GA_YEARS if code == "GA_JTC" else PROGRAM_YEARS_DEFAULT
        for y in years:
            pack = sc.load_pack(code, y)
            if pack is None:
                continue
            for method in ("pay_period", "min_max"):
                tyear = y if y >= 2024 else 2024
                add(f"pack/{code}/{y}/{method}", method, "csv",
                    {"tax_year": tyear, "analysis_start_month": f"{tyear}-01-01", "pack": pack, "with_trail": True,
                     "fiscal_window": [f"{tyear}-01-01", f"{tyear}-12-31"]})
    # legacy flat resolution (tax_year None) for each programme
    for code in cm.PROGRAM_CODE_TO_PACK:
        pack = sc.load_pack(code, None)
        if pack:
            for method in ("pay_period", "min_max"):
                add(f"pack/{code}/flat/{method}", method, "csv", {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": pack, "with_trail": True})

    ga24 = sc.load_pack("GA_JTC", 2024)
    ga25 = sc.load_pack("GA_JTC", 2025)
    # --- windows: calendar, March year end, 53-week and stub-opening windows
    for method in ("pay_period", "min_max"):
        for ds in ("csv", "csv_typed", "csv_dup", "csv_blanks", "csv_codes", "csv_state_cells"):
            add(f"calendar/{ds}/{method}", method, ds, {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": ga25, "with_trail": True})
        add(f"march/{method}", method, "csv", {"tax_year": 2025, "fiscal_year_end_month": 3, "analysis_start_month": "2024-04-01", "pack": ga25, "with_trail": True})
        add(f"march_window/{method}", method, "csv", {"tax_year": 2025, "analysis_start_month": "2024-04-01", "pack": ga25, "with_trail": True,
                                                      "fiscal_window": ["2024-04-01", "2025-03-31"]})
        add(f"week53/{method}", method, "csv_shifted", {"tax_year": 2024, "analysis_start_month": "2024-07-01", "pack": ga24, "with_trail": True,
                                                        "fiscal_window": ["2024-07-28", "2025-08-02"]})
        add(f"week53_nostart_fix/{method}", method, "csv", {"tax_year": 2025, "analysis_start_month": "2025-07-01", "pack": ga25, "with_trail": True,
                                                            "fiscal_window": ["2025-07-28", "2026-08-02"]})
        add(f"no_trail/{method}", method, "csv", {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": ga25, "with_trail": False})
        add(f"year_without_rows/{method}", method, "csv", {"tax_year": 2019, "analysis_start_month": "2019-01-01", "pack": ga25, "with_trail": True})
        for y in (2024, 2026):
            add(f"calendar_y{y}/{method}", method, "csv", {"tax_year": y, "analysis_start_month": f"{y}-01-01", "pack": ga24, "with_trail": True})
    # --- methodology overrides
    meth = [{"minimum_pay_period_days": 0}, {"minimum_pay_period_days": 1}, {"minimum_pay_period_days": 14}, {"short_periods_excluded_from_numerator": True},
            {"pay_period_denominator_mode": "frequency_code"}, {"min_max_span_mode": "inclusive_days"}, {"count_zero_hour_periods": False},
            {"average_decimals": 0}, {"average_decimals": 1}, {"average_decimals": 3}, {"average_decimals": 4}, {"maximum_weeks_without_review": 20.0},
            {"maximum_weeks_without_review": 52}, {"exclude_off_cycle_periods": True}, {"minimum_pay_period_days": 14, "exclude_off_cycle_periods": True,
                                                                                         "short_periods_excluded_from_numerator": True}]
    for i, mset in enumerate(meth):
        for method in ("pay_period", "min_max"):
            add(f"methodology/{i}/{method}", method, "csv_dup", {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": {**ga25, "methodology": mset}, "with_trail": True})
    # --- measuring dates
    for md in ["last_day", "15", "1", "31", "28", "29", "30", "0", "-3", "abc", "", " 20 ", "1_5", "١٥", "99", "15.5", "+7", "٠٣"]:
        for method in ("pay_period", "min_max"):
            add(f"measuring_date/{md!r}/{method}", method, "csv", {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": {**ga25, "measuring_date": md}, "with_trail": False})
    # --- part-time bands and numeric type variants
    for i, pt in enumerate([{"pt_band_hours": [20.0, 32.0], "pt_weight": 0.5}, {"pt_band_hours": [20, 32], "pt_weight": 0.5}, {"pt_band_hours": [20.0, 32.0], "pt_weight": 0.0},
                            {"pt_band_hours": [20.0, 32.0], "pt_weight": 1}, {"pt_band_hours": [30.0, 34.0], "pt_weight": 0.25}, {"pt_weight": 0.5}, {"pt_band_hours": [10.0, 33.0]}]):
        for method in ("pay_period", "min_max"):
            add(f"parttime/{i}/{method}", method, "csv",
                {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": with_pack(min_weekly_hours=32.0, min_weekly_wages=0.0, **pt), "with_trail": True})
            add(f"parttime_int_floors/{i}/{method}", method, "csv",
                {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": with_pack(min_weekly_hours=32, min_weekly_wages=0, **pt), "with_trail": True})
    # --- pay-code policies on the multi-code dataset
    for i, pol in enumerate([{}, {"included_pay_codes": ["Regular"]}, {"excluded_pay_codes": ["Mileage", "Relocation"]},
                             {"included_pay_codes": ["Regular", "Overtime"], "excluded_pay_codes": ["Overtime"]}, {"included_pay_codes": []}, {"excluded_pay_codes": []},
                             {"included_pay_codes": ["Nonexistent"]}]):
        for method in ("pay_period", "min_max"):
            add(f"paycode_policy/{i}/{method}", method, "csv_codes",
                {"tax_year": 2025, "analysis_start_month": "2025-01-01", "pack": {**BASE_PACK, **pol}, "with_trail": True})
        add(f"paycode_policy_op/{i}", "apply_pay_code_policy", "csv_codes", {"pack": {**BASE_PACK, **pol}})
    # --- entity / granularity variants (carried by the pack, ignored by the engine: proves invariance)
    for em in ("permitted", "required", "prohibited"):
        for g in ("unit", "county", "statewide"):
            add(f"entity_granularity/{em}/{g}", "min_max", "csv", {"tax_year": 2025, "analysis_start_month": "2025-01-01",
                                                                     "pack": {**ga25, "entity_combination": em, "geographic_granularity": g}, "with_trail": True})

    # --- edge datasets through every op
    edge_packs = {"ga": with_pack(), "ga_codes": with_pack(included_pay_codes=["Regular", "Overtime", "Bonus", "Commission"], excluded_pay_codes=["Mileage"]),
                  "pt": with_pack(min_weekly_hours=32.0, min_weekly_wages=0.0, pt_band_hours=[20.0, 32.0], pt_weight=0.5),
                  "low": with_pack(min_weekly_hours=1.0, min_weekly_wages=1.0)}
    for name in edge:
        ds = "edge_" + name
        for pk, pack in edge_packs.items():
            for method in ("pay_period", "min_max"):
                for md, start in (("cal", "2024-01-01"), ("mar", "2024-03-01")):
                    add(f"edge/{name}/{pk}/{method}/{md}", method, ds, {"tax_year": 2024, "analysis_start_month": start, "pack": pack, "with_trail": True,
                                                                       "fiscal_window": ["2024-01-01", "2024-12-31"] if md == "cal" else None})
        add(f"edge/{name}/preprocess", "preprocess", ds, {"tax_year": 2024, "with_trail": True})
        add(f"edge/{name}/preprocess_march", "preprocess", ds, {"tax_year": 2024, "fiscal_year_end_month": 3, "with_trail": True, "methodology": {"count_zero_hour_periods": False}})
        add(f"edge/{name}/preprocess_window", "preprocess", ds, {"tax_year": 2024, "fiscal_window": ["2024-01-10", "2024-03-01"], "with_trail": False})
        add(f"edge/{name}/first_measurable", "first_measurable_month", ds, {"window": ["2024-01-01", "2024-12-31"]})
        add(f"edge/{name}/first_measurable_mid", "first_measurable_month", ds, {"window": ["2023-12-28", "2024-12-02"]})
        add(f"edge/{name}/unreachable", "unreachable_months", ds, {"months": [iso(date(2024, m, 28)) for m in range(1, 13)] + ["2024-01-31", "2024-02-29"]})
        add(f"edge/{name}/policy", "apply_pay_code_policy", ds, {"pack": edge_packs["ga_codes"]})
        add(f"edge/{name}/row_states", "row_states", ds)
        add(f"edge/{name}/states_present", "states_present", ds)
        for st in ("GA", "TN", "XX", ""):
            add(f"edge/{name}/rfsy/{st}", "rows_for_state_year", ds, {"state": st, "tax_year": 2024})
            add(f"edge/{name}/rfsy_w/{st}", "rows_for_state_year", ds, {"state": st, "tax_year": 2024, "window": ["2024-01-01", "2024-12-31"]})
            add(f"edge/{name}/ahc/{st}", "average_headcount", ds, {"state": st, "tax_year": 2024, "pack": edge_packs["ga"]})
            add(f"edge/{name}/ahc_w/{st}", "average_headcount", ds, {"state": st, "tax_year": 2024, "pack": edge_packs["ga"], "window": ["2023-12-28", "2024-12-02"]})
    for st in ("GA", "SC", "TN", "NC", "NY", "OH", "FL", "CO", "VA", "TX", "ga", ""):
        for ty in (2024, 2025):
            add(f"csv/rows_for_state_year/{st}/{ty}", "rows_for_state_year", "csv", {"state": st, "tax_year": ty})
            add(f"csv/ahc/{st}/{ty}", "average_headcount", "csv", {"state": st, "tax_year": ty, "pack": ga24 if ty == 2024 else ga25})
            add(f"csv/ahc_fiscal/{st}/{ty}", "average_headcount", "csv", {"state": st, "tax_year": ty, "pack": ga25, "window": [f"{ty - 1}-04-01", f"{ty}-03-31"]})
            add(f"csv/ahc_calwindow/{st}/{ty}", "average_headcount", "csv_state_cells", {"state": st, "tax_year": ty, "pack": ga25, "window": [f"{ty}-01-01", f"{ty}-12-31"]})
    add("csv/row_states", "row_states", "csv")
    add("csv/row_states_cells", "row_states", "csv_state_cells")
    add("csv/states_present", "states_present", "csv")
    add("csv/states_present_cells", "states_present", "csv_state_cells")
    add("csv/first_measurable/cal", "first_measurable_month", "csv", {"window": ["2025-01-01", "2025-12-31"]})
    add("csv/first_measurable/stub", "first_measurable_month", "csv", {"window": ["2025-07-28", "2026-08-02"]})
    add("csv/first_measurable/none", "first_measurable_month", "csv", {"window": ["2010-01-01", "2010-12-31"]})
    add("csv/unreachable", "unreachable_months", "csv", {"months": [iso(date(2025, m, 28)) for m in range(1, 13)]})
    add("csv/preprocess", "preprocess", "csv_dup", {"tax_year": 2025, "with_trail": True})

    # --- seeded random runs
    for i in range(RANDOM_COUNT):
        s = sc.random_run(rng, i)
        scen.append(s)

    # --- helpers
    _helpers(add)
    # --- fiscal and floors
    _fiscal_and_floors(add)
    return datasets, scen


def _helpers(add) -> None:
    n = 0

    def h(name: str, args: list, pack: dict | None = None, **extra) -> None:
        nonlocal n
        n += 1
        add(f"helper/{n:05d}/{name}", "helper", None, {"name": name, "args": args, **({"pack": pack} if pack else {}), **extra})

    for y in (2023, 2024, 2025):
        for m in range(1, 13):
            for dd in (1, 15, 16, 28, 29, 30, 31):
                try:
                    d = date(y, m, dd)
                except ValueError:
                    continue
                for fm in (12, 3, 6, 1, 7):
                    h("fiscal_year_of", [iso(d), fm])
    for ty in (2019, 2023, 2024, 2025, 2026):
        for fm in range(1, 13):
            h("fiscal_window_start", [ty, fm])
    for y in range(2019, 2028):
        for m in range(1, 13):
            h("twelve_month_ends", [iso(date(y, m, 1))])
    for md in ["last_day", None, "", "15", "1", "31", "0", "-1", "99", "abc", " 7 ", "1_0", "٣", "1.0", "+5", "-0", "00015"]:
        for me in ("2024-02-29", "2023-02-28", "2024-01-31", "2024-04-30", "2024-12-31"):
            h("measuring_date_for_month", [me, md])
    for me, lp in (("2024-12-31", "2024-12-20"), ("2024-12-31", "2024-12-15"), ("2024-12-31", "2024-12-16"), ("2024-12-31", "2024-11-30"),
                   ("2024-12-31", "2023-12-30"), ("2024-07-31", "2024-07-26"), ("2024-07-15", "2024-07-26"), ("2024-07-15", "2024-07-16")):
        for m12 in (True, False):
            h("adjusted_target", [me, lp, m12])
    for dys in range(-5, 75):
        h("infer_frequency", [dys])
    for v in (0.125, 0.375, 2.675, 1.005, 34.995, -0.125, 1e22, 1e300, 5e-324, 0.0, -0.0, 1.5, 2.5, 123456.785, 99.995):
        for places in range(0, 7):
            h("round_half_up", [v, places])
    for hrs in (34.99, 35.0 - 1e-10, 35.0 - 1e-9, 35.0 - 2e-9, 35.0, 36.0, 19.99, 20.0, 31.99, 32.0, 0.0):
        for wg in (685.99, 686.0, 686.0 - 1e-10, 0.0, 635.999999999, 700.0):
            for pack in (with_pack(), with_pack(min_weekly_hours=32.0, min_weekly_wages=0.0, pt_band_hours=[20.0, 32.0], pt_weight=0.5),
                         with_pack(min_weekly_hours=35, min_weekly_wages=686), with_pack(pt_band_hours=[20.0, 34.0], pt_weight=0.0)):
                h("classify_eligibility", [{"avg_weekly_hours": hrs, "avg_weekly_wages": wg}], pack)
    for start, end in (("2024-01-01", "2024-01-07"), ("2024-01-01", "2024-01-01"), ("2024-01-02", "2024-01-01"), ("2024-02-29", "2024-03-01")):
        for md in (0, 1, 2, 6, 7, 8):
            h("qualifies", [{"Pay_Period_Start": start, "Pay_Period_End": end}], methodology={"minimum_pay_period_days": md})


def _fiscal_and_floors(add) -> None:
    n = 0
    for b, e in (("2024-01-01", "2024-12-31"), ("2023-07-28", "2024-08-02"), ("2024-04-01", "2025-03-31"), ("2024-12-31", "2024-12-31"), ("2025-01-01", "2024-12-31"),
                 ("2023-12-31", "2024-01-01")):
        for conv in ("begins", "ends", "other"):
            n += 1
            add(f"fiscal/{n}/resolve", "fiscal", None, {"name": "resolve_tax_year", "args": [b, e, conv]})
            add(f"fiscal/{n}/client", "fiscal", None, {"name": "window_from_client_rules", "args": [b, e, conv]})
            add(f"fiscal/{n}/client_note", "fiscal", None, {"name": "window_from_client_rules", "args": [b, e, conv, "custom note"]})
    for ty in (2019, 2023, 2024, 2026):
        for conv in ("begins", "ends"):
            add(f"fiscal/assumed/{ty}/{conv}", "fiscal", None, {"name": "assumed_calendar_window", "args": [ty, conv]})
    n = 0
    bases = [({"_prototype_verify": True}, {}), ({}, {"_prototype_verify": True}), ({}, {}), ({"_prototype_verify": False}, {"_prototype_verify": 0}),
             ({"_prototype_verify": "no"}, {}), ({"_prototype_verify": []}, {"_prototype_verify": ""}), ({"a": 1, "_hidden": 2, "b": "x"}, {"_prototype_verify": 1.5}),
             ({"_prototype_verify": {}}, {"_prototype_verify": None}), ({"_prototype_verify": 0.0}, {}), ({"x": {"y": 1}}, {"_prototype_verify": [0]})]
    for basis, prov in bases:
        for pf in ("ga_jtc.json", "ga_jtc", "x.json.json", ".json", ""):
            n += 1
            add(f"floors/{n}", "floors", None, {"program_code": "GA_JTC", "tax_year": 2024, "min_weekly_hours": 35.0, "min_weekly_wages": 686.0,
                                               "basis": basis, "provenance": prov, "pack_file": pf})
