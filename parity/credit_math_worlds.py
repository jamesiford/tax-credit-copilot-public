"""The rules folders the credit-math golden is recorded against (stage DS7).

A *world* is the shipped ``backend/rules`` plus an overlay of files (``None`` deletes one), built here from the same
helpers the Python tests use (``tests/two_program_world.py``; read, never edited) and a set of invented programs of
my own that exercise every shape the shipped packs do not: a flat pack with ``thresholds_by_year``, integer floors,
a part-time band, a percentage-of-wages benefit, a benefit with no recognised shape, year packs with missing floors,
a retired and a draft program, a pack whose ``credit.code`` differs from its registry code, and strays in a year folder.

Every value is invented and flagged ``_prototype_verify``; nothing here is law. The overlay is what the .NET replay
needs: it is recorded verbatim in the golden's meta line, so the C# side rebuilds the identical folder in memory and
no rule file is copied.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "backend" / "rules"
FLAG = {"_prototype_verify": True}

MANIFEST = "registry/programs.json"


def shipped_manifest() -> dict:
    return json.loads((RULES / MANIFEST).read_text(encoding="utf-8"))


def entry(code: str, state: str | None, pack_file: str, *, lifecycle: str = "described", level: str = "state",
          jurisdiction: str | None = None, profile: dict | None = None, notes: str | None = None) -> dict:
    jur = jurisdiction or (state or "US")
    out = {"code": code, "name": f"{code} (fictional)", "jurisdiction": {"level": level, "code": jur}}
    if state:
        out["state"] = state
    out["pack_file"] = pack_file
    out["lifecycle"] = lifecycle
    out["engine_profile"] = profile or {"credit_model": "per_net_new_job", "headcount_model": "one_zero"}
    if notes is not None:
        out["notes"] = notes
    return out


def pack(code: str, state: str, *, year: int | None = None, per_job=1000, minimum=1, years=3, one_zero: dict | None = None,
         benefit: dict | None = None, thresholds: dict | None = None, convention: object = "begins",
         extra: dict | None = None) -> dict:
    """An invented pack, shaped like ``two_program_world.fictional_pack`` with every block overridable."""
    doc = {
        "_prototype_verification": "FICTIONAL lab program for parity tests. Every value is invented and flagged; it is not law.",
        "rule_pack_version": "0.0.1" if year is None else f"0.0.1+ty{year}",
        "jurisdiction": {"level": "state", "code": state, "name": "Lab (fictional)"},
        "credit": {"code": code, "name": f"{code} (fictional)", "statutory_citation": "Fictional Code \u00a7 0-0-0"},
        "tax_year_convention": ({"label": convention, **FLAG} if convention is not None else None),
        "thresholds": thresholds if thresholds is not None else {"minimum_new_jobs": minimum, "minimum_hours_per_week_full_time": 30, **FLAG},
        "benefit": benefit if benefit is not None else {"amount_per_qualifying_job_usd": per_job, "benefit_period_years": years,
                                                      "carryforward_years": 5, "currency": "USD", **FLAG},
        "one_zero": one_zero if one_zero is not None else {
            "min_weekly_hours": 30.0, "min_weekly_wages": 400.0, "wage_basis": "regular", "geographic_granularity": "statewide",
            "pt_aggregation": False, "headcount_unit_field": "Worksite_ID", "entity_combination": "permitted", **FLAG,
            "wage_floor_basis": {"note": "invented for tests", **FLAG}},
    }
    if doc["tax_year_convention"] is None:
        del doc["tax_year_convention"]
    if year is not None:
        doc["tax_year"] = year
        doc["_year_provenance"] = {"source": "invented for tests", "adr": "ADR-005"}
    doc.update(extra or {})
    return doc


def dump(data: dict) -> str:
    return json.dumps(data, indent=2)


def _oz(**over) -> dict:
    base = {"min_weekly_hours": 30.0, "min_weekly_wages": 400.0, "wage_basis": "regular", "geographic_granularity": "statewide",
            "pt_aggregation": False, "headcount_unit_field": "Worksite_ID", "entity_combination": "permitted", **FLAG}
    base.update(over)
    return base


def zz_world(*, second_authored: bool = True, beta_first: bool = False) -> dict:
    """The two-program world of ``tests/two_program_world.install``, as an overlay."""
    from tests import two_program_world as w

    files: dict = {}
    for code in (w.ALPHA, w.BETA):
        slug = code.lower()
        files[f"{slug}.json"] = dump(w.fictional_pack(code, None))
        if code == w.ALPHA or second_authored:
            for year in w.YEARS:
                files[f"{slug}/{year}.json"] = dump(w.fictional_pack(code, year))
    data = shipped_manifest()
    codes = (w.BETA, w.ALPHA) if beta_first else (w.ALPHA, w.BETA)
    for code in codes:
        data["programs"].append({
            "code": code, "name": f"{code} (fictional)", "jurisdiction": {"level": "state", "code": w.STATE}, "state": w.STATE,
            "pack_file": f"{code.lower()}.json", "lifecycle": "described",
            "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"}})
    files[MANIFEST] = json.dumps(data)
    return {"files": files, "registry_file": None}


def retired_world() -> dict:
    data = shipped_manifest()
    for e in data["programs"]:
        if e["code"] == "VA_MBJF":
            e["lifecycle"] = "retired"
    return {"files": {MANIFEST: json.dumps(data)}, "registry_file": None}


def lab_world() -> dict:
    """Every shape the shipped packs lack, one invented program each (see the module text)."""
    files: dict = {}
    progs: list = []

    def add(code, state, pack_file, doc=None, years: dict | None = None, **kw):
        progs.append(entry(code, state, pack_file, **kw))
        if doc is not None:
            files[pack_file] = dump(doc)
        for y, d in (years or {}).items():
            files[f"{pack_file[:-5]}/{y}"] = d if isinstance(d, str) else dump(d)

    flat_oz = _oz(min_weekly_hours=35, min_weekly_wages=500, pt_band_hours=[20, 32], pt_weight=0.5, measuring_date="15",
                  wage_basis="all_remuneration", geographic_granularity="county", pt_aggregation=True, entity_combination="prohibited",
                  headcount_unit_field="Site", pay_code_policy={"included_pay_codes": ["Regular", "Bonus"], "excluded_pay_codes": ["Mileage"]},
                  thresholds_by_year={"2024": {"min_weekly_hours": 36.5, "min_weekly_wages": 510.25, "pt_weight": 0.75},
                                      "2025": {"min_weekly_hours": 37}, "2026": {}, "2027": {"measuring_date": "last_day"}},
                  methodology={"minimum_pay_period_days": 5, "average_decimals": 3, "count_zero_hour_periods": False,
                               "maximum_weeks_without_review": 52, "pay_period_denominator_mode": "frequency_code"})
    add("ZL_RETIRED", "ZL", "zl_retired.json", pack("ZL_RETIRED", "ZL"), lifecycle="retired")
    add("ZL_FLAT", "ZL", "zl_flat.json", pack("ZL_FLAT", "ZL", per_job=1250.5, minimum=3, one_zero=flat_oz))
    add("ZL_PCT", "ZL", "zl_pct.json", pack("ZL_PCT", "ZL", benefit={"amount_per_qualifying_job_pct_of_wages": 0.065,
                                                                    "benefit_period_years": 10, **FLAG}, minimum=2))
    add("ZM_NOSHAPE", "ZM", "zm_noshape.json", pack("ZM_NOSHAPE", "ZM", benefit={"benefit_period_years": 3}))
    add("ZM_DRAFT", "ZM", "zm_draft.json", None, lifecycle="draft")
    add("ZM_PREF", "ZM", "zm_pref.json", pack("ZM_PREF", "ZM", benefit={"amount_per_qualifying_job_usd": 99, "amount_per_qualifying_job_pct_of_wages": 0.5,
                                                                          "benefit_period_years": 2}))
    ys = {
        "2024": pack("ZN_YS", "ZN", year=2024), "2025": pack("ZN_YS", "ZN", year=2025, one_zero=_oz(min_weekly_hours=35, min_weekly_wages=700)),
        "2026": pack("ZN_YS", "ZN", year=2026, one_zero=_oz(min_weekly_wages=None)),
        "2027": {**pack("ZN_YS", "ZN", year=2027), "one_zero": None},
        "2028": pack("ZN_YS", "ZN", year=2028, convention="ends"),
        "2029": pack("ZN_YS", "ZN", year=2029, convention="weird"),
        "2030": pack("ZN_YS", "ZN", year=2030, convention=None, one_zero=_oz(wage_floor_basis={"source": "invented", "_private": 1, "n": 2.5, "_prototype_verify": False},
                                                                          _prototype_verify=False),
                     extra={"_year_provenance": {"source": "invented", "_prototype_verify": True}}),
        "2031": pack("ZN_YS", "ZN", year=2031, one_zero=_oz(min_weekly_hours=None)),
        "2032": {**pack("ZN_YS", "ZN", year=2032), "tax_year_convention": {"label": "begins", "regulation": "Fictional reg 1", "_note": "n", "_prototype_verify": False}},
        "2033": {**pack("ZN_YS", "ZN", year=2033), "tax_year_convention": {"regulation": "none"}},
        "2034": {**pack("ZN_YS", "ZN", year=2034, one_zero=_oz(wage_floor_basis=None)), "_year_provenance": None},
        "2035": pack("ZN_YS", "ZN", year=2035, one_zero=_oz(min_weekly_hours=0, min_weekly_wages=0.0)),
        "0042": pack("ZN_YS", "ZN", year=42),
        "notes": {"note": "not a year"}, "abc": {"note": "not a year"},
    }
    add("ZN_YS", "ZN", "zn_ys.json", pack("ZN_YS", "ZN", one_zero=_oz(thresholds_by_year={"2024": {"min_weekly_wages": 1}})),
        years={f"{k}.json": v for k, v in ys.items()})
    files["zn_ys/2031.txt"] = "{}"
    add("ZN_EY", "ZN", "zn_ey.json", pack("ZN_EY", "ZN"), years={"notes.json": {"n": 1}})
    add("ZO_NOONEZERO", "ZO", "zo_noonezero.json", {**pack("ZO_NOONEZERO", "ZO"), "one_zero": None})
    add("ZO_ALIAS", "ZO", "zo_alias.json", pack("ZO_ALIAS_PACK", "ZO"))
    add("ZO_EMPTYOZ", "ZO", "zo_emptyoz.json", pack("ZO_EMPTYOZ", "ZO", one_zero={}))
    add("ZO_NOCONV", "ZO", "zo_noconv.json", pack("ZO_NOCONV", "ZO", convention=None))
    add("FED_LAB", None, "fed_lab.json", pack("FED_LAB", "US", one_zero=_oz(min_weekly_hours=32.0, min_weekly_wages=0.0,
                                                                                entity_combination="prohibited")),
        level="federal", jurisdiction="US")
    add("FED_LAB_EMPTY", None, "fed_lab_empty.json", pack("FED_LAB_EMPTY", "US", one_zero={}), level="federal", jurisdiction="US")
    add("ZP_BIGFLOAT", "ZP", "zp_bigfloat.json", pack("ZP_BIGFLOAT", "ZP", per_job=1e300, minimum=0))
    add("ZP_BIGINT", "ZP", "zp_bigint.json", pack("ZP_BIGINT", "ZP", per_job=10 ** 30, years=10 ** 20))
    add("ZP_FRAC", "ZP", "zp_frac.json", pack("ZP_FRAC", "ZP", per_job=0.5, minimum=0.5, years=4))
    add("ZP_TIE", "ZP", "zp_tie.json", pack("ZP_TIE", "ZP", per_job=2.5, minimum=0, years=2))
    add("ZP_YEARS55", "ZQ", "zp_years55.json", pack("ZP_YEARS55", "ZQ", years=5.5))
    add("ZP_YEARSSTR", "ZQ", "zp_yearsstr.json", pack("ZP_YEARSSTR", "ZQ", years="7", minimum="4"))
    add("ZP_YEARSNEG", "ZQ", "zp_yearsneg.json", pack("ZP_YEARSNEG", "ZQ", years=-2, minimum=-1.5))
    add("ZP_YEARSBAD", "ZQ", "zp_yearsbad.json", pack("ZP_YEARSBAD", "ZQ", years="five"))
    add("ZP_YEARSNONE", "ZQ", "zp_yearsnone.json", pack("ZP_YEARSNONE", "ZQ", years=None))
    add("ZP_NOTHR", "ZR", "zp_nothr.json", {k: v for k, v in pack("ZP_NOTHR", "ZR").items() if k != "thresholds"})
    add("ZP_NOMIN", "ZR", "zp_nomin.json", pack("ZP_NOMIN", "ZR", thresholds={"minimum_hours_per_week_full_time": 30}))
    add("ZP_NOBEN", "ZR", "zp_noben.json", {k: v for k, v in pack("ZP_NOBEN", "ZR").items() if k != "benefit"})
    add("ZP_NOCITE", "ZR", "zp_nocite.json", {**pack("ZP_NOCITE", "ZR"), "credit": {"code": "ZP_NOCITE", "name": "ZP_NOCITE (fictional)"}})
    add("ZP_NONAME", "ZR", "zp_noname.json", {**pack("ZP_NONAME", "ZR"), "credit": {"code": "ZP_NONAME", "statutory_citation": "x"}})
    add("ZP_NOJUR", "ZR", "zp_nojur.json", {k: v for k, v in pack("ZP_NOJUR", "ZR").items() if k != "jurisdiction"})
    add("ZP_NONAMEVAL", "ZR", "zp_nonameval.json", {**pack("ZP_NONAMEVAL", "ZR"), "credit": {"code": "ZP_NONAMEVAL", "name": None, "statutory_citation": "x"}})
    add("ZP_THRSTR", "ZS", "zp_thrstr.json", pack("ZP_THRSTR", "ZS", thresholds={"minimum_new_jobs": "x"}))
    add("ZP_THRNONE", "ZS", "zp_thrnone.json", pack("ZP_THRNONE", "ZS", thresholds={"minimum_new_jobs": None}))
    add("ZP_BENEFITSTR", "ZS", "zp_benefitstr.json", pack("ZP_BENEFITSTR", "ZS", benefit={"amount_per_qualifying_job_usd": "x", "benefit_period_years": 1}))
    add("ZP_PERJOBNONE", "ZS", "zp_perjobnone.json", pack("ZP_PERJOBNONE", "ZS", benefit={"amount_per_qualifying_job_usd": None, "benefit_period_years": 1}))
    add("ZP_PERJOBZERO", "ZS", "zp_perjobzero.json", pack("ZP_PERJOBZERO", "ZS", benefit={"amount_per_qualifying_job_usd": 0, "benefit_period_years": 1}))
    add("ZP_PCTSTR", "ZS", "zp_pctstr.json", pack("ZP_PCTSTR", "ZS", benefit={"amount_per_qualifying_job_pct_of_wages": "0.1", "benefit_period_years": 1}))
    add("ZP_BADOZ", "ZT", "zp_badoz.json", pack("ZP_BADOZ", "ZT", one_zero=_oz(methodology={"minimum_pay_period_day": 3})))
    add("ZP_BADOZ2", "ZT", "zp_badoz2.json", pack("ZP_BADOZ2", "ZT", one_zero=_oz(methodology={"min_max_span_mode": "weird", "minimum_pay_period_days": -1})))
    add("ZP_NOWAGES", "ZT", "zp_nowages.json", pack("ZP_NOWAGES", "ZT", one_zero={"min_weekly_hours": 30.0}))
    add("ZP_NOHOURS", "ZT", "zp_nohours.json", pack("ZP_NOHOURS", "ZT", one_zero={"min_weekly_wages": 30.0}))
    add("ZP_BANDMIN", "ZT", "zp_bandmin.json", pack("ZP_BANDMIN", "ZT", one_zero=_oz(pt_band_hours=[0, 0], pt_weight=0, measuring_date=None,
                                                                                  pay_code_policy={"included_pay_codes": [], "excluded_pay_codes": None})))
    add("ZP_NULLPOLICY", "ZT", "zp_nullpolicy.json", pack("ZP_NULLPOLICY", "ZT", one_zero=_oz(pay_code_policy=None, wage_basis=None, geographic_granularity=None)))
    data = shipped_manifest()
    data["programs"].extend(progs)
    files[MANIFEST] = json.dumps(data)
    return {"files": files, "registry_file": None}


def custom_registry_world() -> dict:
    """The manifest moved out of ``registry/`` and named by ``PROGRAM_REGISTRY_FILE``."""
    data = shipped_manifest()
    return {"files": {MANIFEST: None, "custom-programs.json": json.dumps(data)}, "registry_file": "custom-programs.json"}


def text_world(text: str | None, name: str = MANIFEST) -> dict:
    return {"files": {MANIFEST: text}, "registry_file": None}


def all_worlds() -> dict[str, dict]:
    worlds: dict[str, dict] = {
        "shipped": {"files": {}, "registry_file": None},
        "zz": zz_world(),
        "zz_one": zz_world(second_authored=False),
        "zz_rev": zz_world(beta_first=True),
        "retired": retired_world(),
        "lab": lab_world(),
        "custom": custom_registry_world(),
        "nomanifest": text_world(None),
        "badjson": text_world("{"),
        "badschema": text_world("{}"),
        "badprograms": text_world('{"schema_version": 1, "programs": {}}'),
        "emptyprograms": text_world('{"schema_version": 1, "programs": []}'),
        "bom": text_world("\ufeff" + json.dumps(shipped_manifest())),
    }
    return copy.deepcopy(worlds)
