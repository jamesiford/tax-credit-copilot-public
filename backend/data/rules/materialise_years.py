"""Materialise year-scoped rule packs from a flat pack.

[ADR-005] A rule pack is scoped to (program, tax year) and **materialised** —
stored fully resolved rather than merged from a base plus overlays at run time.
The question a tax authority asks is *"what rules did you apply to my 2021
return?"*, and the answer should be a file with a hash, not the output of a
computation that has to be re-executed and trusted.

This is an **authoring tool**. Its output is committed; the engine reads the
committed files and never runs this.

    cd backend
    python -m data.rules.materialise_years ga_jtc --years 2023 2024 2025

Provenance
----------
Every emitted pack records where its statutory values came from, so a later
reader can tell an authored figure from an inherited one.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
_RULES = _BACKEND / "rules"

# ---------------------------------------------------------------------------
# Georgia's published historical wage table.
#
# Transcribed verbatim from `stakeholder-docs/JTCHistoricalWages_Jul 2025.pdf`
# (SHA-256 21A8D16683196F982CBF3040980BEC9C8A3A4F2BD1AC686E57647D03185D8208),
# "Job Tax Credit Program — Historical Wage Detail".
#
# Georgia sets the floor from the average weekly wage of the **lowest-wage county
# in the state** for a DOL report year. Which county that is changes, and the
# figure moves in both directions — TY2025 is $6 BELOW TY2024. Any code that
# assumes the floor rises monotonically is wrong.
#
#   tax_year: (dol_report_year, county, weekly_wage, annualized_wage)
#
# The annualised column is the PDF's own check digit: weekly x 52 == annualised
# for every row. `_validate_wage_table()` asserts it at import, so a transcription
# slip fails loudly here rather than silently changing an eligibility count.
#
# DO NOT edit a figure to make a test pass. This is published statute.
_GA_HISTORICAL_WAGE_TABLE: dict[int, tuple[int, str, float, float]] = {
    2004: (2003, "Echols", 297.0, 15444.0),
    2005: (2004, "Echols", 313.0, 16276.0),
    2006: (2005, "Echols", 340.0, 17680.0),
    2007: (2006, "Echols", 362.0, 18824.0),
    2008: (2007, "Echols", 406.0, 21112.0),
    2009: (2008, "Glascock", 415.0, 21580.0),
    2010: (2009, "Glascock", 423.0, 21996.0),
    2011: (2010, "Glascock", 435.0, 22620.0),
    2012: (2011, "Echols", 446.0, 23192.0),
    2013: (2012, "Echols", 403.0, 20956.0),
    2014: (2013, "Echols", 426.0, 22152.0),
    2015: (2014, "Glascock", 470.0, 24440.0),
    2016: (2015, "Glascock", 471.0, 24492.0),
    2017: (2016, "Glascock", 480.0, 24960.0),
    2018: (2017, "Glascock", 484.0, 25168.0),
    2019: (2018, "Glascock", 511.0, 26572.0),
    2020: (2019, "Glascock", 541.0, 28132.0),
    2021: (2020, "Glascock", 589.0, 30628.0),
    2022: (2021, "Glascock", 602.0, 31304.0),
    2023: (2022, "Glascock", 636.0, 33072.0),
    2024: (2023, "Taliaferro", 686.0, 35672.0),
    2025: (2024, "Taliaferro", 680.0, 35360.0),
}

# The table ends at TY2025. TY2026 would draw on the DOL 2025 Employment & Wages
# publication, which Georgia releases in the summer of 2026 — we do not hold it.
#
# TY2026 is therefore a PLACEHOLDER, authored separately from the table above so
# the two can never be confused, and so the demo can tell an in-year story
# (24 Sep 2026: "build TY2026 now with a clearly-labelled placeholder floor,
# swap in the real one when the partner sends it"). The value is TY2025's $680 CARRIED
# FORWARD and says so; the county and annualised wage are None, not a plausible
# guess. `_prototype_verify` travels into the pack, `StatutoryFloors` reports
# it, and every screen that states a floor for TY2026 flags it as unverified.
#
# To replace it: add TY2026 to `_GA_HISTORICAL_WAGE_TABLE` from the published
# table, delete it here, and re-run `python -m data.rules.materialise_years
# ga_jtc --years 2026`. Nothing else changes.
_GA_PLACEHOLDER_YEARS: dict[int, dict] = {
    2026: {
        "min_weekly_hours": 35.0,
        "min_weekly_wages": 680.0,
        "_source": "placeholder",
        "_prototype_verify": True,
        "_note": (
            "PLACEHOLDER — not published statute. TY2025's $680/week carried forward "
            "until the Georgia DOL 2025 Employment & Wages table (lowest-wage county) "
            "is supplied. Replace before any TY2026 figure is relied on."
        ),
    },
}

_WAGE_TABLE_SOURCE = (
    "JTCHistoricalWages_Jul 2025.pdf (SHA-256 "
    "21A8D16683196F982CBF3040980BEC9C8A3A4F2BD1AC686E57647D03185D8208), "
    "Georgia DOL Employment & Wages Averages, lowest-wage county"
)

# 35 hours is the full-time threshold in O.C.G.A. 48-7-40 and does not vary by
# year — only the wage floor is republished annually.
_GA_MIN_WEEKLY_HOURS = 35.0

_WEEKS_PER_YEAR = 52


def _validate_wage_table() -> None:
    """Check the transcription against the PDF's own annualised column."""
    for year, (_dol, county, weekly, annualized) in _GA_HISTORICAL_WAGE_TABLE.items():
        if round(weekly * _WEEKS_PER_YEAR, 2) != annualized:
            raise AssertionError(
                f"GA wage table TY{year} ({county}): {weekly} x {_WEEKS_PER_YEAR} = "
                f"{weekly * _WEEKS_PER_YEAR}, but the PDF annualises to {annualized}. "
                f"One of the two was mistyped — check against the source PDF."
            )
        if _dol != year - 1:
            raise AssertionError(
                f"GA wage table TY{year} cites DOL report year {_dol}; Georgia uses "
                f"the prior year's publication, so it should be {year - 1}."
            )


_validate_wage_table()


def _ga_known_years() -> dict[int, dict]:
    """The published table, in the shape `_resolve_year` consumes."""
    out: dict[int, dict] = {}
    for year, (dol, county, weekly, annualized) in _GA_HISTORICAL_WAGE_TABLE.items():
        out[year] = {
            "min_weekly_hours": _GA_MIN_WEEKLY_HOURS,
            "min_weekly_wages": weekly,
            "_source": "published_wage_table",
            "_note": (
                f"Georgia published table: DOL report year {dol}, {county} County, "
                f"${annualized:,.0f} / {_WEEKS_PER_YEAR} = ${weekly:,.0f} per week. "
                f"Source: {_WAGE_TABLE_SOURCE}."
            ),
        }
    return out


# Statutory floors, keyed by program then tax year.
#
# Do not edit these to make a test pass. They are the published statute.
_KNOWN_YEARS: dict[str, dict[int, dict]] = {
    "ga_jtc": {**_ga_known_years(), **_GA_PLACEHOLDER_YEARS},
}


# How each year's weekly floor was arrived at. Georgia sets the floor from the
# average weekly wage of its LOWEST-wage county in a DOL report year, so the
# figure is only auditable alongside which county and which report year produced
# it. Those facts belong to the tax year, not to our methodology, which is why
# they live here and not in an assumption set.
#
# Derived from the published table rather than hand-maintained: a second hand-kept
# copy of the same facts is a second thing to get wrong.
def _ga_wage_floor_basis() -> dict[int, dict]:
    published = {
        year: {
            "dol_report_year": dol,
            "lowest_wage_county": county,
            "annualized_wage_usd": annualized,
            "_verified": True,
        }
        for year, (dol, county, _weekly, annualized) in _GA_HISTORICAL_WAGE_TABLE.items()
    }
    # A placeholder year knows which DOL report it WILL come from and nothing
    # else. None, not a guess, and unverified.
    placeholders = {
        year: {"dol_report_year": year - 1, "lowest_wage_county": None,
               "annualized_wage_usd": None, "_verified": False}
        for year in _GA_PLACEHOLDER_YEARS
    }
    return {**published, **placeholders}


_WAGE_FLOOR_BASIS: dict[str, dict[int, dict]] = {
    "ga_jtc": _ga_wage_floor_basis(),
}

# Constant across every Georgia year we hold, so it is stated once rather than
# copied into each entry where the copies could drift apart.
_PROGRAM_WAGE_FLOOR_BASIS: dict[str, dict] = {
    "ga_jtc": {
        "wage_table_year_basis": "source_tax_year",
        "regulation": "110-9-1-.02(1)(a) and 110-9-1-.03(3)(b)1",
    },
}


def _flat_pack(program: str) -> dict:
    path = _RULES / f"{program}.json"
    if not path.exists():
        raise SystemExit(f"no flat pack at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_year(program: str, flat: dict, year: int) -> tuple[dict, dict]:
    """Return (one_zero_overrides, provenance) for one tax year.

    Precedence is **published table first**. `thresholds_by_year` in a flat pack
    is our own earlier, partial transcription of the same source; where both
    cover a year the complete self-checking table is the better authority, and
    letting the partial copy win would make a correction to the table invisible.
    """
    oz = flat.get("one_zero", {})

    known = _KNOWN_YEARS.get(program, {}).get(year)
    if known:
        overrides = {k: v for k, v in known.items() if not k.startswith("_")}
        prov = {"source": known["_source"], "note": known["_note"]}
        # Carry the unverified marker into the emitted pack so a placeholder is
        # visible downstream and cannot pass for authored statute.
        if known.get("_prototype_verify"):
            prov["_prototype_verify"] = True
            overrides["_prototype_verify"] = True
        _warn_if_flat_pack_disagrees(program, oz, year, overrides)
        return overrides, prov

    by_year = (oz.get("thresholds_by_year") or {}).get(str(year))
    if by_year:
        overrides = {k: v for k, v in by_year.items() if not k.startswith("_")}
        return overrides, {
            "source": "thresholds_by_year",
            "note": by_year.get("_note", ""),
            "doc_source": by_year.get("_doc_source", ""),
        }
        return overrides, prov

    # No authored statute for this year. Emitting the flat default would be a
    # confident wrong answer, so refuse and name the year that is missing.
    raise SystemExit(
        f"no statutory values for {program} tax year {year}. "
        f"Author them in _KNOWN_YEARS or add thresholds_by_year to the flat pack. "
        f"ADR-005: a missing year is a real gap in statutory coverage and must "
        f"not silently inherit another year's rules."
    )


def _wage_floor_basis(program: str, year: int) -> dict | None:
    """The county / DOL-report-year facts behind this year's weekly floor."""
    per_year = _WAGE_FLOOR_BASIS.get(program, {}).get(year)
    if per_year is None:
        return None
    basis = {**_PROGRAM_WAGE_FLOOR_BASIS.get(program, {}), "source_tax_year": year}
    basis.update({k: v for k, v in per_year.items() if not k.startswith("_")})
    if not per_year.get("_verified"):
        basis["_prototype_verify"] = True
    return basis


def _warn_if_flat_pack_disagrees(program: str, oz: dict, year: int, chosen: dict) -> None:
    """Say so out loud when the flat pack's older copy contradicts the table.

    Silence here would let two disagreeing transcriptions of the same PDF sit in
    the repo indefinitely, with the losing one still being read by the flat
    (non-year-scoped) code path.
    """
    by_year = (oz.get("thresholds_by_year") or {}).get(str(year))
    if not by_year:
        return
    for key in ("min_weekly_hours", "min_weekly_wages"):
        old, new = by_year.get(key), chosen.get(key)
        if old is not None and new is not None and old != new:
            print(
                f"  ! {program} TY{year}: flat pack thresholds_by_year says {key}={old}, "
                f"published table says {new}. Using the table; fix or remove the flat "
                f"pack entry."
            )


def materialise(program: str, year: int, *, dry_run: bool = False) -> Path:
    flat = _flat_pack(program)
    overrides, provenance = _resolve_year(program, flat, year)

    pack = json.loads(json.dumps(flat))          # deep copy
    oz = pack.setdefault("one_zero", {})
    oz.update(overrides)
    basis = _wage_floor_basis(program, year)
    if basis is not None:
        oz["wage_floor_basis"] = basis
    # Resolved: the year's values are now literal, so the overlay must go or a
    # reader could not tell which won.
    oz.pop("thresholds_by_year", None)

    pack["tax_year"] = year
    pack["rule_pack_version"] = f"{flat.get('rule_pack_version', '0.1.0')}+ty{year}"
    pack["_year_provenance"] = {
        **provenance,
        "materialised_from": f"rules/{program}.json",
        "materialised_on": date.today().isoformat(),
        "adr": "ADR-005",
    }

    out_dir = _RULES / program
    out = out_dir / f"{year}.json"
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("program", help="e.g. ga_jtc")
    ap.add_argument("--years", nargs="+", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for year in sorted(args.years):
        out = materialise(args.program, year, dry_run=args.dry_run)
        if out.exists():
            pack = json.loads(out.read_text(encoding="utf-8"))
            oz = pack.get("one_zero", {})
            src = pack.get("_year_provenance", {}).get("source", "?")
            print(f"{'would write' if args.dry_run else 'wrote'} "
                  f"{out.relative_to(_BACKEND)}  hrs={oz.get('min_weekly_hours')} "
                  f"wages=${oz.get('min_weekly_wages')}  [{src}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
