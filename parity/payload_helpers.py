"""The helper-call half of ``export_gold_payload.py``: the pure functions the run command depends on, recorded one call at a time.

Each call runs the PRODUCTION function and records its arguments and either the output tree or the exception's type and message (``golden_rec`` line
format). Payroll arguments are SYMBOLIC (``"csv"``, ``"csv:300"``, ``"synth:2003:500"``: the committed CSV, or the first N rows of a synthetic client) so a
golden stays small and the replay rebuilds the same rows from its own inputs. Covered: ``application/program_defaults.py``, ``application/payroll_rows.py``,
``application/qc_resolutions.py``, ``application/queries/_client_run.py``, ``application/runs/fingerprint.py`` and ``infrastructure/payroll/fiscal_source.py``
(the pure window arithmetic, and ``client_fiscal_window`` with the source mode and the stored rules supplied from here, since the SQL and lakehouse reads are I/O).
"""
from __future__ import annotations

import hashlib
import json
import warnings
from datetime import date
from types import SimpleNamespace

import golden_rec as gr

YEARS = (None, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027)
STATES = ("GA", "ga", "NY", "SC", "NC", "TN", "FL", "OH", "CO", "VA", "ZZ", "", "G")
CODES = ("GA_JTC", "ga_jtc", "NY_EXCELSIOR", "SC_JTC", "NC_JTEC", "TN_JTC", "FL_QTI", "OH_JCTC", "CO_EZ", "VA_MBJF", "FEDERAL_WOTC_LITE", "XX_NONE", "", "GA")
CLIENTS = (None, 1001, 2001, 9999)
STORE: dict = {}


def row_digest(rows) -> str:
    fields = ("Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State")
    text = json.dumps([[r.get(f) for f in fields] for r in rows], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def rows_of(spec):
    parts = spec.split(":")
    rows = STORE["csv"] if parts[0] == "csv" else STORE["synth"][int(parts[1])]
    count = int(parts[-1]) if len(parts) > (1 if parts[0] == "csv" else 2) else None
    return rows if count is None else rows[:count]


def window(w) -> dict:
    return None if w is None else w.as_dict()


def pack_tree(p) -> dict:
    return {"min_weekly_hours": p.min_weekly_hours, "min_weekly_wages": p.min_weekly_wages, "wage_basis": p.wage_basis, "tax_year": p.tax_year, "citation": p.citation,
            "measuring_date": p.measuring_date, "entity_combination": p.entity_combination, "pt_weight": p.pt_weight, "geographic_granularity": p.geographic_granularity}


def statute_tree(s) -> dict:
    return {"account_id": s.account_id, "state": s.state, "program_code": s.program_code, "tax_year": s.tax_year, "floors": s.floors.as_dict(), "pack": pack_tree(s.pack),
            "window": window(s.window)}


def run_tree(r) -> dict:
    kwargs = r.engine_kwargs()
    return {**statute_tree(r), "n_rows": len(r.rows), "n_state_rows": len(r.state_rows), "rows_digest": row_digest(r.rows), "state_rows_digest": row_digest(r.state_rows),
            "engine": {"tax_year": kwargs["tax_year"], "analysis_start_month": kwargs["analysis_start_month"], "fiscal_window": kwargs["fiscal_window"]}}


def call(r, fn, args, run):
    r.call(fn, args, run)


def program_defaults(r) -> None:
    from application import program_defaults as pd

    for ty in YEARS:
        call(r, "calculable_states", {"tax_year": ty}, lambda ty=ty: pd.calculable_states(ty))
        for st in STATES:
            call(r, "calculable_programs_for_state", {"state": st, "tax_year": ty}, lambda st=st, ty=ty: pd.calculable_programs_for_state(st, ty))
    for held in ([], ["GA"], ["ga", "TN"], ["SC", "GA"], ["NC", "TN"], ["XX"], ["GA", "GA"], ["tn"]):
        for ty in (None, 2019, 2025, 2026):
            call(r, "pick_state", {"client_states": held, "tax_year": ty}, lambda h=held, ty=ty: pd.pick_state(h, ty))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for client in (1001, 2001, 9999):
            for ty in (None, 2025):
                for req in (None, "", "ga", "tn", "ZZ"):
                    call(r, "derive_run_state", {"client_id": client, "tax_year": ty, "requested": req}, lambda c=client, ty=ty, q=req: pd.derive_run_state(c, ty, q))
                call(r, "derive_run_programs", {"client_id": client, "tax_year": ty}, lambda c=client, ty=ty: pd.derive_run_programs(c, ty))
                for ws in ("GA_GA-001", "tn_x", "ZZ_1", "NOPREFIX", ""):
                    for req in (None, "sc"):
                        call(r, "state_for_location", {"client_id": client, "worksite_id": ws, "tax_year": ty, "requested": req},
                             lambda c=client, w=ws, ty=ty, q=req: pd.state_for_location(c, w, ty, q))
        for st in STATES + (None,):
            for code in CODES + (None,):
                call(r, "check_program_state", {"state": st, "program_code": code}, lambda s=st, c=code: pd.check_program_state(s, c))
        for code in CODES:
            call(r, "program_state", {"program_code": code}, lambda c=code: pd.program_state(c))
            call(r, "location_state", {"client_id": 1001, "worksite_id": "GA_GA-001", "state": None, "program_code": code}, lambda c=code: pd.location_state(1001, "GA_GA-001", None, c))
        for client in (1001, 9999):
            for st in STATES[:6] + (None,):
                for code in CODES[:3] + ("TN_JTC", "XX_NONE", None):
                    for ty in (None, 2025):
                        for req in (False, True):
                            args = {"client_id": client, "state": st, "program_code": code, "tax_year": ty, "require_program": req}
                            call(r, "resolve_program", args, lambda a=args: pd.resolve_program(a["client_id"], a["state"], a["program_code"], a["tax_year"], require_program=a["require_program"]))
                        call(r, "priced_program", {"client_id": client, "state": st, "program_code": code, "tax_year": ty},
                             lambda c=client, s=st, p=code, ty=ty: pd.priced_program(c, s, p, ty))
                        call(r, "run_state", {"client_id": client, "tax_year": ty, "state": st, "program_code": code}, lambda c=client, s=st, p=code, ty=ty: pd.run_state(c, ty, s, p))
    for st in STATES:
        call(r, "programs_to_price", {"state": st}, lambda s=st: pd.programs_to_price(s))
        call(r, "program_code_for_state", {"state": st}, lambda s=st: pd.program_code_for_state(s))
    call(r, "state_programs", {}, lambda: pd.state_programs())
    rows = [{"program_code": "GA_JTC", "v": 1}, {"program_code": None, "v": 2}, {"v": 3}, {"program_code": "TN_JTC", "v": 4}]
    for code in (None, "", "GA_JTC", "TN_JTC", "XX"):
        call(r, "rows_of_program", {"rows": rows, "program_code": code}, lambda c=code: pd.rows_of_program(rows, c))
    call(r, "ProgramChoiceRequired", {"state": "GA", "candidates": ["GA_JTC", "GA_X"]},
         lambda: (lambda e: {"message": str(e), "candidates": list(e.candidates), "is_not_runnable": isinstance(e, pd.ProgramNotRunnable)})(pd.ProgramChoiceRequired("GA", ("GA_JTC", "GA_X"))))


def payroll_rows(r) -> None:
    from application import payroll_rows as pr
    from application import qc_resolutions as qc
    from tools.qc import pay_line_keys

    for spec in ("csv", "csv:300", "synth:2001:4000", "synth:2003:2500"):
        rows = rows_of(spec)
        for st in ("GA", "ga", "TN", "SC", "XX", ""):
            call(r, "program_rows", {"rows": spec, "program_state": st}, lambda rows=rows, st=st: {"n": len(pr.program_rows(rows, st)), "digest": row_digest(pr.program_rows(rows, st))})
        call(r, "states_present", {"rows": spec}, lambda rows=rows: pr.states_present(rows))
        call(r, "row_state_digest", {"rows": spec}, lambda rows=rows: [pr.row_state(x) for x in rows[:50]])
    for acct in (1001, 9999, None):
        call(r, "require_pay_periods", {"account_id": acct, "drop_qc": False}, lambda a=acct: {"n": len(pr.require_pay_periods(account_id=a)), "digest": row_digest(pr.require_pay_periods(account_id=a))})
    for ty in ((2023, 2025), (2018,), (2019, 2026, 2030), ()):
        for st in (None, "GA", "tn", "SC"):
            call(r, "unauthored_state_years", {"tax_years": list(ty), "state": st}, lambda ty=ty, st=st: pr.unauthored_state_years(ty, state=st))
    for spec in ("csv:2000", "synth:2001:3000"):
        rows = rows_of(spec)
        for ty in (2018, 2023, 2025):
            for st in (None, "GA", "SC"):
                for on in ("raise", "skip", "bad"):
                    args = {"rows": spec, "tax_year": ty, "state": st, "on_unauthored": on}
                    call(r, "iter_state_packs", args, lambda rows=rows, a=args: [
                        {"state": sp[0], "program_code": sp.program_code, "n": len(sp[2]), "pack": pack_tree(sp[1])}
                        for sp in pr.iter_state_packs(rows, tax_year=a["tax_year"], state=a["state"], on_unauthored=a["on_unauthored"])])
    # QC resolutions: a seeded store, then every spec's rows filtered through it.
    rows = rows_of("csv:3000")
    keys = pay_line_keys(rows)
    months: dict = {}
    for row in rows:
        months.setdefault((str(row.get("Employee_ID", "")), str(row.get("Pay_Date", ""))[:7]), set()).add(str(row.get("Worksite_ID", "")))
    multi = [(e, m, sorted(w)) for (e, m), w in sorted(months.items()) if len(w) > 1][:3]
    scenarios = {
        "empty": {},
        "drop-lines": {f"pp:{keys[i]}": {"resolution": "drop"} for i in (3, 40, 41, 700)},
        "assign": {f"t2:{e}:{m}": {"resolution": "assign", "keep_worksite": w[0]} for e, m, w in multi} or {"t2:x:2024-01": {"resolution": "assign", "keep_worksite": "GA_GA-001"}},
        "annotations-only": {f"pp:{keys[5]}": {"resolution": "accept"}, "t2:1:2024-01": {"resolution": "flag"}, "t2:2:2024-01": {"resolution": "assign"}},
        "mixed": {f"pp:{keys[9]}": {"resolution": "drop"}, "t2:abc:2024-02": {"resolution": "assign", "keep_worksite": "GA_X"}, "t2:short": {"resolution": "assign", "keep_worksite": "W"}},
    }
    for name, store in scenarios.items():
        def run(store=store):
            qc.QC_RESOLUTIONS.clear()
            qc.QC_RESOLUTIONS.update(store)
            try:
                out = qc.apply_calc_drops(rows)
                return {"n": len(out), "digest": row_digest(out), "same_list": out is rows}
            finally:
                qc.reset_qc_resolutions()

        call(r, "apply_calc_drops", {"rows": "csv:3000", "resolutions": store}, run)
    for anomaly in ({"type": "test_of_twos", "employee_id": "E1", "month": "2024-03"}, {"type": "scraggly", "line_key": "k1"}, {"type": "x"}, {"employee_id": 5, "type": "test_of_twos"}):
        call(r, "exception_id", {"anomaly": anomaly}, lambda a=anomaly: qc.exception_id(a))


def fiscal(r) -> None:
    from infrastructure.payroll import fiscal_source as fs
    import tools.fabric_source as fab

    for acct in (None, 1001, 2001):
        for ty in YEARS[1:]:
            for conv in ("begins", "ends"):
                call(r, "client_fiscal_window", {"account_id": acct, "tax_year": ty, "convention": conv}, lambda a=acct, ty=ty, c=conv: window(fs.client_fiscal_window(a, ty, c)))
    for acct in (None, 1001):
        for st in ("GA", "GA_JTC", "TN", "XX", "", "ga"):
            for ty in (2018, 2023, 2026):
                call(r, "fiscal_window_for_state_year", {"account_id": acct, "state": st, "tax_year": ty}, lambda a=acct, s=st, ty=ty: window(fs.fiscal_window_for_state_year(a, s, ty)))
                call(r, "window_for_state_year", {"account_id": acct, "state": st, "tax_year": ty}, lambda a=acct, s=st, ty=ty: fs.window_for_state_year(a, s, ty))
    rules = [
        ("a calendar year", "EntityFiscalYearRules", "CAL", date(2023, 1, 1), date(2023, 12, 31)),
        ("a july year", "EntityFiscalYearRules", None, date(2023, 7, 1), date(2024, 6, 30)),
        ("a 53 week year", "override:ops", "52/53", date(2023, 7, 28), date(2024, 8, 2)),
        ("leap start", "EntityFiscalYearRules", "", date(2024, 2, 29), date(2025, 2, 27)),
        ("leap end", "EntityFiscalYearRules", "", date(2023, 3, 1), date(2024, 2, 29)),
        ("backwards", "EntityFiscalYearRules", "", date(2024, 1, 1), date(2023, 1, 1)),
        ("text dates", "EntityFiscalYearRules", "txt", "2023-04-01T00:00:00", "2024-03-31"),
        ("bad text", "EntityFiscalYearRules", "bad", "nonsense", "2024-03-31"),
        ("missing", "EntityFiscalYearRules", "m", None, None),
    ]
    for label, name, expression, begin, end in rules:
        rule = SimpleNamespace(name=name, rule_expression=expression, fiscal_year_begin=begin, fiscal_year_end=end)
        for ty in (2019, 2022, 2023, 2024, 2025, 2028):
            for conv in ("begins", "ends"):
                args = {"label": label, "name": name, "rule_expression": expression, "begin": begin, "end": end, "tax_year": ty, "convention": conv}
                call(r, "_window_from_rule", args, lambda rule=rule, ty=ty, c=conv: window(fs._window_from_rule(rule, 7, ty, c)))
    original = (fs._rules_with_overrides, fab.active_data_source)
    try:
        fab.active_data_source = lambda: "lakehouse"
        for label, rule_set in {"none": None, "empty": [], "first-unusable": [SimpleNamespace(name="x", rule_expression=None, fiscal_year_begin=None, fiscal_year_end=None),
                                                                            SimpleNamespace(name="override:y", rule_expression="E", fiscal_year_begin=date(2023, 7, 1), fiscal_year_end=date(2024, 6, 30))],
                                "july": [SimpleNamespace(name="EntityFiscalYearRules", rule_expression="J", fiscal_year_begin=date(2023, 7, 1), fiscal_year_end=date(2024, 6, 30))]}.items():
            fs._rules_with_overrides = lambda account_id, rule_set=rule_set: rule_set
            for ty in (2022, 2023, 2024, 2026):
                for conv in ("begins", "ends"):
                    for acct in (None, 1001):
                        call(r, "client_fiscal_window_rules", {"rules": label, "account_id": acct, "tax_year": ty, "convention": conv},
                             lambda a=acct, ty=ty, c=conv: window(fs.client_fiscal_window(a, ty, c)))
    finally:
        fs._rules_with_overrides, fab.active_data_source = original


def resolution(r) -> None:
    from application.queries import _client_run as cr
    from application.runs import fingerprint as fp
    from application.commands.run_client_calculation import _assumption_identity
    from domain.warehouse import RunManifest

    for acct in (1001, 9999, None):
        for st, code in (("GA", None), (None, None), (None, "GA_JTC"), ("TN", None), ("SC", None), ("ZZ", None), (None, "FEDERAL_WOTC_LITE"), ("GA", "TN_JTC")):
            for ty in (2018, 2023, 2024, 2025, 2026, 2030):
                args = {"account_id": acct, "state": st, "tax_year": ty, "program_code": code, "require_program": False}
                call(r, "resolve_statute", args, lambda a=args: statute_tree(cr.resolve_statute(**a)))
                call(r, "resolve_client_run", {**args, "rows": None}, lambda a=args: run_tree(cr.resolve_client_run(**a)))
    rows = rows_of("csv")
    for ty in (2024, 2025):
        args = {"account_id": 1001, "state": "GA", "tax_year": ty, "program_code": None, "require_program": True, "rows": "csv:4000"}
        call(r, "resolve_client_run_rows", args, lambda ty=ty: run_tree(cr.resolve_client_run(account_id=1001, state="GA", tax_year=ty, rows=rows[:4000], require_program=True)))
        call(r, "resolve_client_run_rows", {**args, "rows": "csv:0"}, lambda ty=ty: run_tree(cr.resolve_client_run(account_id=1001, state="GA", tax_year=ty, rows=[])))
    assumptions = _assumption_identity()
    for spec in ("csv", "csv:5000", "csv:50"):
        for ty in (2024, 2025, 2026):
            def identity(spec=spec, ty=ty):
                run = cr.resolve_client_run(account_id=1001, state="GA", tax_year=ty, rows=rows_of(spec))
                ident = fp.run_identity(run, assumptions)
                current = fp.current_fingerprint(run, assumptions, "c0ffee")
                return {"identity": ident.manifest_fields(), "fingerprint": current}

            call(r, "run_identity", {"rows": spec, "tax_year": ty}, identity)
    for rule in ([], [("2023-07-01", "2024-06-30")], [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")]):
        for spec in ("csv", "csv:100"):
            call(r, "client_data_fingerprint", {"rows": spec, "windows": rule}, lambda rule=rule, spec=spec: fp.client_data_fingerprint(rows_of(spec), rule))
    for acct in (None, 1001):
        for st, code in (("GA", "GA_JTC"), ("TN", "TN_JTC"), ("GA", "XX"), ("GA", "")):
            call(r, "authored_windows", {"account_id": acct, "state": st, "program_code": code}, lambda a=acct, s=st, c=code: fp.authored_windows(a, s, c))
    manifest = RunManifest(run_id="r", client_id=1, program_code="GA_JTC", tax_year=2024, fiscal_year_begin=date(2024, 1, 1), fiscal_year_end=date(2024, 12, 31),
                           run_started_at=__import__("datetime").datetime(2026, 1, 1), run_status="success", calculation_id="calc", step1_assumption_sha256="s1", onezero_assumption_sha256="",
                           rule_pack_version="v", code_commit="abc", source_snapshot_id="snap")
    call(r, "manifest_fingerprint", {"manifest": "full"}, lambda: fp.manifest_fingerprint(manifest))
    call(r, "manifest_fingerprint", {"manifest": None}, lambda: fp.manifest_fingerprint(None))
    call(r, "manifest_fingerprint", {"manifest": "bare"}, lambda: fp.manifest_fingerprint(SimpleNamespace(
        calculation_id="", step1_assumption_sha256=None, onezero_assumption_sha256="x", rule_pack_version="", code_commit=None, tax_year=2020)))


def helper_lines(csv_data: list, synthetic: dict) -> list:
    STORE["csv"], STORE["synth"] = csv_data, synthetic
    r = gr.Recorder()
    program_defaults(r)
    payroll_rows(r)
    fiscal(r)
    resolution(r)
    lines = []
    for text_in, rec in r.lines:
        body = gr.dumps(rec)
        lines.append(body[:-1] + ',"args":' + text_in + "}")
    print(f"{len(r.lines)} helper calls, {r.errors} errors", file=__import__("sys").stderr)
    return lines
