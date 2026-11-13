"""A fictional state with TWO fictional programs, for the program-first tests. [F04c.9]

Everything lives under a temporary rules folder (`RULES_DIR`): `ZZ_ALPHA_JTC` and `ZZ_BETA_JTC` both register state `ZZ`, each
with its own pack and its own authored year packs, and they differ ON PURPOSE in the per-job amount and the threshold so
that pricing one under the other's statute shows up as a different number. Georgia ships unchanged beside them. Every
value is invented and flagged `_prototype_verify`; nothing here is law, and no tracked rules file is touched.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
RULES = BACKEND / "rules"
STATE = "ZZ"
ALPHA, BETA = "ZZ_ALPHA_JTC", "ZZ_BETA_JTC"
#: (per-job USD, minimum new jobs): different on purpose.
STATUTE = {ALPHA: (1000, 1), BETA: (2500, 3)}
YEARS = (2024, 2025)
CLIENT = 7777


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def fictional_pack(code: str, year: int | None) -> dict:
    per_job, threshold = STATUTE[code]
    flag = {"_prototype_verify": True}
    pack = {
        "_prototype_verification": "FICTIONAL demo program for tests. Every value is invented and flagged; it is not law.",
        "rule_pack_version": "0.0.1" if year is None else f"0.0.1+ty{year}",
        "jurisdiction": {"level": "state", "code": STATE, "name": "Zedland (fictional)"},
        "credit": {"code": code, "name": f"{code} (fictional)", "statutory_citation": "Fictional Code § 0-0-0"},
        "tax_year_convention": {"label": "begins", **flag},
        "filing": {"window": "Fictional filing window", "cycle": "annual", **flag},
        "thresholds": {"minimum_new_jobs": threshold, "minimum_hours_per_week_full_time": 30, **flag},
        "benefit": {"amount_per_qualifying_job_usd": per_job, "benefit_period_years": 3, "carryforward_years": 5,
                    "currency": "USD", **flag},
        "one_zero": {
            "min_weekly_hours": 30.0, "min_weekly_wages": 400.0, "wage_basis": "regular", "geographic_granularity": "statewide",
            "pt_aggregation": False, "headcount_unit_field": "Worksite_ID", "entity_combination": "permitted", **flag,
            "wage_floor_basis": {"note": "invented for tests", **flag},
        },
    }
    if year is not None:
        pack["tax_year"] = year
        pack["_year_provenance"] = {"source": "invented for tests", "adr": "ADR-005"}
    return pack


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def zz_payroll() -> list[dict]:
    """The committed synthetic payroll, re-labelled to the made-up state."""
    rows = []
    with (BACKEND / "data" / "payroll_pay_periods.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["Worksite_ID"].startswith("GA_") and int(row["Tax_Year"]) in YEARS:
                rows.append({**row, "Worksite_ID": f"{STATE}_" + row["Worksite_ID"][3:], "Tax_Year": int(row["Tax_Year"]),
                             "Hours_Worked": float(row["Hours_Worked"]), "Gross_Wages": float(row["Gross_Wages"])})
    return rows


def install(tmp_path: Path, monkeypatch, *, second_authored: bool = True) -> dict:
    """Build the temporary rules folder, point `RULES_DIR` at it and serve the relabelled payroll for `CLIENT`."""
    import application.source_ports as source_ports

    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    codes = (ALPHA, BETA)
    for code in codes:
        slug = code.lower()
        write_json(rules / f"{slug}.json", fictional_pack(code, None))
        if code == ALPHA or second_authored:
            for year in YEARS:
                write_json(rules / slug / f"{year}.json", fictional_pack(code, year))
    manifest = rules / "registry" / "programs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for code in codes:
        data["programs"].append({
            "code": code, "name": f"{code} (fictional)", "jurisdiction": {"level": "state", "code": STATE}, "state": STATE,
            "pack_file": f"{code.lower()}.json", "lifecycle": "described",
            "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"},
        })
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("RULES_DIR", str(rules))
    rows = zz_payroll()
    assert rows, "the synthetic fixture should hold Georgia rows to relabel"
    monkeypatch.setattr(source_ports, "load_pay_periods", lambda account_id=None: rows)
    scope = type("S", (), {"states": [STATE], "tax_years": list(YEARS), "total_rows": len(rows),
                           "pay_dates": sorted({str(r["Pay_Date"])[:10] for r in rows})})()
    monkeypatch.setattr(source_ports, "payroll_scope", lambda account_id: scope)
    return {"rules": rules, "rows": rows}
