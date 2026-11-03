"""Offline API stand-in for the measurement tools. Dev tooling, not shipped.

The app cannot boot on a clone of the public repo without private inputs: the
shell needs the sealed reference workspace (`One.csv`..`Four.csv`) and every
per-client read needs the Fabric Warehouse. The design gates (visible rows,
type floor, brand, sweep) need a rendered page, so this serves a small,
deterministic, SYNTHETIC dataset for exactly those endpoints and forwards
everything else to a real backend on port 8001 when one is running.

    python frontend/tools/mock_api.py            # listens on :8000

Vite already proxies `/api` to :8000, so no tool changes are needed. The data
is invented (no payroll, no real names) and carries no certified figure; it is
only large enough to make the grids render at a realistic density.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8000
UPSTREAM = "http://127.0.0.1:8001"

RUN = {"run_id": "1ef66984739b4e22986ec57603fe8a7c", "produced_at": "2026-09-01T10:00:00Z"}
YEARS = [2021, 2022, 2023]
UNITS = [f"GA_GA-{n:03d}" for n in range(1, 11)]
NAMES = ["Peachtree", "Midtown", "Buckhead", "Decatur", "Marietta", "Savannah Riverfront",
         "Augusta Road", "Macon Central", "Athens Campus", "Columbus Plaza"]
COUNTIES = ["Fulton", "Fulton", "Fulton", "DeKalb", "Cobb", "Chatham", "Richmond", "Bibb", "Clarke", "Muscogee"]

WORKSPACE = {
    "run": {
        "step1_calculation_id": "sha256:abc", "onezero_calculation_id": "sha256:def",
        "source_manifest_sha256": "sha256:ghi", "step1_assumption_set_id": "GDS-STEP1-2026-08-25-v8",
        "onezero_assumption_set_id": "GDS-ONEZERO-2026-08-24-v7", "code_commit": "abc1234",
        "created_at": "2026-08-26T12:00:00Z",
    },
    "workspace": {"account_id": 1001, "tax_year": 2023, "client_name": "Synthetic Client"},
    "eligibility": {
        "employees_with_totals": 10236,
        "min_max": {"employees_evaluated": 10236, "eligible_employees": 539},
        "pay_period": {"employees_evaluated": 10236, "eligible_employees": 656},
        "reconciliation": {"eligible_both": 500, "min_max_only": 39, "pay_period_only": 156},
        "thresholds": {"source_tax_year": 2023},
        "denominator_invariant": {
            "invariant_holds": True, "pay_period_gt_min_max": 0,
            "pay_period_gt_min_max_over_review_tolerance": 0,
            "pay_period_over_52_weeks": 0, "maximum_weeks_without_review": 53,
        },
        "pay_period_controls": {
            "source_period_keys": 384418, "employee_pps_ppe_periods": 382180,
            "same_pps_ppe_records_collapsed": 2238, "conflicting_frequency_periods": 0,
        },
    },
    "onezero": {"min_max": {"overlap_flags": 30}, "pay_period": {}},
    "source": {
        "source_kind": "lakehouse",
        "controls": {
            "usable_rows": 384433, "distinct_employees": 10236, "zero_hour_rows": 1204,
            "negative_hour_rows": 88, "negative_wage_rows": 91, "pay_date_before_period_end_rows": 3,
        },
        "files": [{"file_name": "One.csv", "usable_rows": 100000, "padded_rows": 10, "sha256": "sha256:aaa"}],
    },
    "equivalence": {
        "matches": True, "source_kind": "lakehouse",
        "expected": {"employees_evaluated": 10236, "min_max_eligible": 539, "pay_period_eligible": 656},
        "observed": {"employees_evaluated": 10236, "min_max_eligible": 539, "pay_period_eligible": 656},
    },
    "exceptions": {"step1": [], "onezero": []},
    "boundary": {
        "boundary_complete": True, "status": "complete", "prior_ppe_paid_in_fy_rows": 0,
        "crossing_start_rows": 0, "current_ppe_paid_after_fy_rows": 0,
        "earliest_valid_pay_period_start": "2023-07-28",
    },
    "comparison": {"status": "awaiting_outputs", "first_divergent_stage": None},
    "stages": [],
}


def unit_rows(method: str, tax_year: int | None):
    items, months, installments, totals = [], [], [], []
    for u, worksite in enumerate(UNITS):
        base_year = 2021 if u % 3 else 2022
        for year in YEARS:
            if tax_year and year != tax_year and False:
                continue
            avg = 18 + u * 3.1 + (year - 2021) * (1.5 if u % 4 else -2.0)
            net_new = round(avg - (18 + u * 3.1), 2)
            qualified = year > base_year and net_new >= 2
            items.append({
                "worksite_id": worksite, "tax_year": year, "method": method, "program_code": "GA_JTC",
                "average_headcount": round(avg, 2), "base_average_headcount": round(avg - net_new, 2),
                "net_new_vs_base": net_new, "threshold": 2, "tier": 1 + u % 3, "designation": f"Tier {1 + u % 3}",
                "tier_source": "designation", "per_job_usd": "3500.0000",
                "annual_credit_usd": f"{int(max(net_new, 0) * 3500)}.0000",
                "qualified": qualified, "is_base_year": year == base_year,
                "status": "base_year" if year == base_year else ("qualified" if qualified else "below_minimum"),
                "high_water_mark": round(avg + 0.5, 2), "months_with_headcount": 12, "unreachable_months": "",
            })
            row = {"worksite_id": worksite, "tax_year": year, "method": method,
                   "total": round(avg * 12, 2), "average_headcount": round(avg, 2), "unreachable_months": ""}
            for m in range(1, 13):
                row[f"month_{m:02d}"] = round(avg + ((m * 7 + u) % 5) - 2, 2)
            months.append(row)
            for created in range(2021, year + 1):
                installments.append({
                    "worksite_id": worksite, "tax_year": year, "creation_year": created,
                    "claimable_usd": f"{int(max(avg - 18 - u * 3.1, 0) * 3500) + 7000}.0000",
                    "projected": False,
                })
        totals.append({
            "worksite_id": worksite, "total_annual_credit_usd": f"{40000 + u * 9000}.0000",
            "final_high_water_mark": round(20 + u * 3.1, 2),
            "total_tranche_lifetime_usd": f"{52000 + u * 9500}.0000",
        })
    units = [{"worksite_id": w, "name": NAMES[i], "county": COUNTIES[i], "city": NAMES[i]}
             for i, w in enumerate(UNITS)]
    return items, months, installments, totals, units


def units_payload(method: str, tax_year: int | None):
    items, months, installments, totals, units = unit_rows(method, tax_year)
    return {
        "calculation_state": "calculated", "run": RUN, "newer_run_in_flight": False,
        "client_id": 2001, "state": "GA", "year": tax_year, "method": method,
        "items": items, "total": len(items), "months": months, "installments": installments,
        "unit_totals": totals, "units": units, "years": YEARS,
    }


def employee(n: int, month: int | None):
    hours = 29 + (n * 7) % 14 + (n % 3) * 0.37
    wages = 520 + (n * 53) % 340
    row = {
        "record_token": f"tok-{n:04d}", "employee_id": f"E{n:05d}", "weight": 1,
        "weeks_worked": 40 + n % 13, "total_hours": round(hours * (40 + n % 13), 1),
        "avg_weekly_hours": round(hours, 2), "avg_weekly_wages": round(wages, 2),
        "eligible": hours >= 35 and wages >= 636, "failure_mode": None,
    }
    for m in range(1, 13):
        row[f"month_{m:02d}"] = 1 if (n + m) % 7 else 0
    if month:
        row[f"month_{month:02d}"] = 1
    return row


def unit_payload(unit_id: str, month: int | None):
    people = [employee(n, month) for n in range(1, 29)]
    near = [employee(n, month) | {"additional_weekly_hours": round((35 - e["avg_weekly_hours"]), 2),
                                   "hours_bound": True}
            for n, e in ((n, employee(n, month)) for n in range(100, 125))]
    return {
        "calculation_state": "calculated", "run": RUN,
        "unit": {"worksite_id": unit_id, "average_headcount": 25.92, "base_year": 2021, "status": "qualified"},
        "employees": people, "total": len(people), "total_unfiltered": len(people),
        "near_threshold": near, "near_total_unfiltered": len(near),
        "month_filter": {"month_index": month},
        "thresholds": {"min_weekly_hours": 35, "min_weekly_wages": 636},
    }


def upstream_json(path: str):
    with urllib.request.urlopen(UPSTREAM + path, timeout=60) as response:
        return json.loads(response.read())


CLIENTS = [
    (2001, "Cascade Retail Partners", 784, "Retail", "unclaimed_at_scale", 11.4, "148750"),
    (2002, "Ironbridge Logistics", 512, "Logistics", "on_the_line", -0.4, "52500"),
    (2003, "Halloway Foods", 301, "Food service", "declining", 6.2, "208845"),
    (2004, "Northwind Care", 266, "Healthcare", "exposed", 3.1, "31200"),
    (2005, "Lakeshore Fabrication", 143, "Manufacturing", "settled", 0.0, "0"),
]


def scope_payload():
    body = upstream_json("/api/scope")
    body["clients"] = [c for c in body["clients"] if c["account_id"] == 1001] + [
        {"account_id": cid, "name": name, "billing_state": "GA", "employees": emp, "synthetic": True, "industry": ind}
        for cid, name, emp, ind, *_ in CLIENTS
    ]
    return body


def client_scope(client_id: int):
    return {
        "account_id": client_id, "states": ["GA", "NC"], "payroll_years": YEARS,
        "calculable_years": YEARS, "payroll_without_statute": [], "rows": 76086,
    }


def portfolio_payload(query):
    body = upstream_json("/api/v2/portfolio?limit=200")
    template = body["items"][0]
    items = []
    for rank, (cid, name, _emp, industry, band, margin, usd) in enumerate(CLIENTS, start=1):
        items.append(template | {
            "client_id": cid, "client_name": name, "industry": industry, "status": "assessed",
            "tax_year": 2023, "priority_band": band, "priority_rank": rank, "jobs_margin": margin,
            "gap_jobs": max(0.0, -margin), "identified_usd": usd, "claimed_usd": "0", "opportunity_usd": usd,
            "states": ["GA", "NC"], "priceable_states": ["GA"], "outcome": "unclaimed",
            "near_threshold": band == "on_the_line", "one_more_job_qualifies": band == "on_the_line",
        })
    body.update(items=items, total=len(items), total_clients=len(items),
                assessed_clients=len(items), unassessed_clients=0)
    return body


def route(method: str, path: str, query: dict[str, list[str]], body: bytes):
    """Return a JSON-able body for the endpoints this stand-in owns, else None."""
    if path == "/api/scope":
        return scope_payload()
    m = re.fullmatch(r"/api/scope/client/(\d+)", path)
    if m and int(m.group(1)) >= 2000:
        return client_scope(int(m.group(1)))
    if path == "/api/v2/portfolio":
        return portfolio_payload(query)
    if path in ("/api/workspace", "/api/workspace/refresh"):
        return WORKSPACE
    if path.startswith("/api/workspace/"):
        return 503, {"detail": "mock: sealed workspace endpoint not served"}
    m = re.fullmatch(r"/api/v2/clients/(\d+)/runs/latest", path)
    if m:
        return {"run": RUN, "calculation_state": "calculated"}
    m = re.fullmatch(r"/api/v2/clients/(\d+)/units", path)
    if m:
        year = int(query["year"][0]) if query.get("year") else None
        return units_payload(query.get("method", ["min_max"])[0], year)
    m = re.fullmatch(r"/api/v2/clients/(\d+)/units/([^/]+)", path)
    if m:
        month = int(query["month"][0]) if query.get("month") else None
        return unit_payload(m.group(2), month)
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, status: int, payload, headers=None):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        result = route(self.command, parsed.path, parse_qs(parsed.query), body)
        if result is not None:
            status, payload = result if isinstance(result, tuple) else (200, result)
            return self._send(status, payload)
        request = urllib.request.Request(
            UPSTREAM + self.path, data=body or None, method=self.command,
            headers={"Content-Type": self.headers.get("Content-Type", "application/json")},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return self._send(response.status, response.read())
        except urllib.error.HTTPError as error:
            return self._send(error.code, error.read())
        except Exception as error:  # noqa: BLE001
            return self._send(503, {"detail": f"mock: no upstream for {parsed.path} ({error})"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"mock api on :{port}, upstream {UPSTREAM}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
