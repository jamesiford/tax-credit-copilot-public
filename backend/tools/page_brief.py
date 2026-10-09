"""The brief behind each page's Copilot summary, and the check on what it said.

29 Sep: the page-opening banners pointed at single data points ("0.8 jobs from
qualifying: Ironbridge"). James asked for the data to do the talking, with an
optional, collapsed Copilot summary that says the headlines.

ADR-004 still holds. A model never computes a figure: each builder here turns
the page's OWN payload — the one its endpoint already served — into a JSON
brief of pre-formatted facts. `PageSummaryAgent` chooses which of them matter
and says them. The honest limit is that prose streams unvalidated, so
`unsupported_figures` checks every number in the finished summary against the
brief, and the page says so if one does not appear there.

Pure: payload in, brief out. No reads, no model.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_BAND_LABEL = {
    "exposed": "Exposed",
    "on_the_line": "On the line",
    "declining": "Declining",
    "unclaimed_at_scale": "Identified",
    "not_assessed": "Not assessed",
    "settled": "Nothing found",
}


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usd(value: Any) -> str:
    n = _num(value)
    return "—" if n is None else f"${n:,.0f}"


def _one(value: Any) -> str:
    n = _num(value)
    return "—" if n is None else f"{n:.1f}"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


# ------------------------------------------------------------------ portfolio


def portfolio_brief(book: dict[str, Any]) -> dict[str, Any]:
    """The book as the page ranks it: clients in band order, with their reason."""
    items = book.get("items") or []
    total = int(book.get("total_clients") or len(items))
    assessed = int(book.get("assessed_clients") or 0)
    clients = []
    for position, row in enumerate(items, start=1):
        band = row.get("priority_band")
        name = row.get("client_name") or f"Account {row.get('client_id')}"
        margin = _num(row.get("jobs_margin"))
        trend = row.get("trend") or {}
        fact = f"{position}. {name}: {_BAND_LABEL.get(band, band or 'unranked')}"
        if row.get("program_code") and row.get("tax_year"):
            fact += f" ({row['program_code']} TY{row['tax_year']})"
        if band == "on_the_line" and margin is not None:
            fact += (
                f", {abs(margin):.2f} jobs short of the minimum" if margin < 0
                else f", {margin:.2f} jobs over the minimum"
            )
        elif band == "declining" and trend:
            fallen = _num(trend.get("fallen_by"))
            if fallen is not None:
                fact += f", down {fallen:.1f} jobs since TY{trend.get('peak_tax_year')}"
            if trend.get("below_base"):
                fact += ", now below its base year"
            if trend.get("credit_earned_usd") is not None:
                fact += f", {_usd(trend['credit_earned_usd'])} already earned"
        elif _num(row.get("identified_usd")):
            fact += f", {_usd(row['identified_usd'])} identified"
        clients.append({
            "position": position,
            "client": name,
            "industry": row.get("industry"),
            "reason": _BAND_LABEL.get(band, band),
            "fact": fact,
        })

    facts = [f"{_plural(total, 'client')} in the book, {assessed} assessed."]
    facts += [c["fact"] for c in clients]
    caveats = [
        "The ranking is by reason to act, not by dollar value: 'On the line' outranks "
        "'Identified' because a threshold missed at year end is gone, while an "
        "unclaimed credit is recoverable retroactively.",
        "'Declining' is a forecast about a year nobody has filed, not a finding.",
    ]
    if total > assessed:
        caveats.append(
            f"{total - assessed} client(s) have not been assessed: that is not a zero."
        )
    return {
        "page": "portfolio",
        "subject": "the whole book of clients",
        "headline": facts[0],
        "facts": facts,
        "caveats": caveats,
        "data": {"total_clients": total, "assessed_clients": assessed, "clients": clients},
    }


# --------------------------------------------------------------------- client


def client_brief(
    payload: dict[str, Any], *, client_name: str, placeholder_years: Iterable[int] = (),
) -> dict[str, Any]:
    """One client's locations: where each stands in its last finished year and
    in the open one, and what the finished years are worth."""
    items = payload.get("items") or []
    if not items:
        return _not_calculated("client", client_name, payload)

    placeholder = set(placeholder_years)
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for row in items:
        by_unit.setdefault(str(row["worksite_id"]), []).append(row)

    locations = []
    open_year = None
    for unit, rows in sorted(by_unit.items()):
        rows.sort(key=lambda r: int(r["tax_year"]))
        closed = [r for r in rows if r.get("status") != "in_progress"]
        opened = next((r for r in rows if r.get("status") == "in_progress"), None)
        last = closed[-1] if closed else None
        base = next((r for r in rows if r.get("is_base_year")), None)
        entry: dict[str, Any] = {
            "location": unit,
            "base_year": int(base["tax_year"]) if base else None,
            "designation": (last or {}).get("designation"),
        }
        if last is not None:
            entry["latest_finished_year"] = int(last["tax_year"])
            entry["latest_reading"] = str(last.get("status") or "").replace("_", " ")
            entry["latest_net_new_jobs"] = _one(last.get("net_new_vs_base"))
        if opened is not None:
            open_year = int(opened["tax_year"])
            entry["open_year_reading"] = "on track" if opened.get("qualified") else "behind pace"
            entry["open_year_net_new_jobs"] = _one(opened.get("net_new_vs_base"))
            entry["open_year_closed_months"] = opened.get("months_reachable")
        declines = [int(r["tax_year"]) for r in closed if r.get("status") == "below_minimum"]
        if declines:
            entry["years_below_minimum"] = declines
        locations.append(entry)

    totals = payload.get("unit_totals") or []
    claimable = sum(_num(t.get("total_annual_credit_usd")) or 0.0 for t in totals)
    lifetime = sum(_num(t.get("total_tranche_lifetime_usd")) or 0.0 for t in totals)
    finished = sorted({int(r["tax_year"]) for r in items if r.get("status") != "in_progress"})

    qualifying = [l for l in locations if l.get("latest_reading") == "above minimum"]
    below = [l for l in locations if l.get("latest_reading") == "below minimum"]
    facts = [
        f"{_plural(len(locations), 'location')}; in its latest finished year, "
        f"{len(qualifying)} qualify and {len(below)} are below the minimum.",
    ]
    if claimable and finished:
        span = f"TY{finished[0]}–TY{finished[-1]}" if len(finished) > 1 else f"TY{finished[0]}"
        facts.append(f"{_usd(claimable)} claimable across {span}; {_usd(lifetime)} if maintained.")
    for l in below:
        facts.append(
            f"{l['location']} was below the minimum in TY{l['latest_finished_year']} "
            f"({l['latest_net_new_jobs']} net-new jobs against its TY{l['base_year']} base)."
        )
    if open_year:
        on_track = [l for l in locations if l.get("open_year_reading") == "on track"]
        behind = [l for l in locations if l.get("open_year_reading") == "behind pace"]
        facts.append(
            f"TY{open_year} is still open: {len(on_track)} of "
            f"{len(on_track) + len(behind)} locations on track so far."
        )
        for l in behind:
            facts.append(
                f"{l['location']} is behind pace in TY{open_year} "
                f"({l['open_year_net_new_jobs']} net-new jobs so far)."
            )

    caveats = ["Base years are inferred from payroll and designations are prototype data."]
    if open_year:
        caveats.append(
            f"TY{open_year} is open: read on its closed months, never priced; "
            f"'on track' is a forecast, not a qualification."
        )
    if open_year in placeholder:
        caveats.append(
            f"TY{open_year}'s wage floor is a placeholder carried forward from "
            f"TY{open_year - 1} until Georgia publishes it."
        )
    return {
        "page": "client",
        "subject": client_name,
        "headline": facts[0],
        "facts": facts,
        "caveats": caveats,
        "data": {
            "locations": locations,
            "claimable_usd": round(claimable),
            "if_maintained_usd": round(lifetime),
            "finished_years": finished,
            "open_year": open_year,
        },
    }


# ----------------------------------------------------------------------- unit


def unit_brief(
    payload: dict[str, Any], *, client_name: str, month: int | None = None, band: float = 5.0,
    placeholder: bool = False,
) -> dict[str, Any]:
    """One location in one year: who counted, and who is a shift short."""
    unit = payload.get("unit")
    if not unit:
        return _not_calculated("unit", client_name, payload)

    year = int(payload.get("year") or unit.get("tax_year") or 0)
    site = str(unit.get("worksite_id") or payload.get("unit_id") or "")
    floor = _num((payload.get("thresholds") or {}).get("min_weekly_hours"))
    counted = int(payload.get("total_unfiltered") or len(payload.get("employees") or []))
    near = payload.get("near_threshold") or []
    within = [
        r for r in near
        if floor is not None and _num(r.get("avg_weekly_hours")) is not None
        and _num(r["avg_weekly_hours"]) >= floor - band
    ]
    in_progress = unit.get("status") == "in_progress"
    reading = (
        ("on track" if unit.get("qualified") else "behind pace") if in_progress
        else str(unit.get("status") or "").replace("_", " ")
    )
    when = f"in {_MONTHS[month - 1]} TY{year}" if month else f"in TY{year}"

    facts = [
        f"{site}: {counted} employees counted {when}.",
        f"Average headcount {_one(unit.get('average_headcount'))} against a base of "
        f"{unit.get('base_average_headcount')}; reading: {reading}"
        + (f" over {unit.get('months_reachable')} closed months." if in_progress else "."),
    ]
    if unit.get("designation"):
        facts.append(f"Designation {unit['designation']} in TY{year} (prototype data, shown not applied).")
    if unit.get("net_new_vs_base") is not None and not unit.get("is_base_year"):
        facts.append(
            f"{_one(unit.get('net_new_vs_base'))} net-new jobs against a minimum of "
            f"{_one(unit.get('threshold'))}."
        )
    if floor is not None:
        facts.append(
            f"{len(within)} more employees are within {band:g} hrs/week of the "
            f"{floor:g}-hour floor; {len(near)} are ineligible in all."
        )
        closest = sorted(within, key=lambda r: -(_num(r.get("avg_weekly_hours")) or 0))[:3]
        for r in closest:
            extra = _num(r.get("additional_weekly_hours"))
            facts.append(
                f"Employee {r.get('employee_id')} averages {_num(r['avg_weekly_hours']):.2f} hrs/week"
                + (f" and needs {extra:.2f} more to qualify." if extra else ".")
            )

    caveats = []
    if in_progress:
        caveats.append(f"TY{year} is open: read on its closed months; nothing is priced yet.")
    if placeholder:
        caveats.append(f"TY{year}'s wage floor is a placeholder carried forward from TY{year - 1}.")
    return {
        "page": "unit",
        "subject": f"{client_name} · {site}",
        "headline": facts[0],
        "facts": facts,
        "caveats": caveats,
        "data": {
            "location": site, "tax_year": year, "month": month, "counted": counted,
            "reading": reading, "within_band": len(within), "ineligible": len(near),
        },
    }


# ------------------------------------------------------------------- employee


def employee_brief(drill: dict[str, Any], *, placeholder: bool = False) -> dict[str, Any]:
    """One employee's year: did they qualify, by how much, and where they counted."""
    year = drill.get("tax_year")
    employee = drill.get("employee_id")
    thresholds = drill.get("thresholds") or {}
    floor_hours = _num(thresholds.get("minimum_average_weekly_hours"))
    floor_wages = _num(thresholds.get("minimum_average_weekly_wages_usd"))
    rows = drill.get("raw_source_rows") or []
    included = sum(1 for r in rows if r.get("selection_decision") == "included")

    facts = [
        f"Employee {employee}, TY{year}: {_plural(len(rows), 'pay period')} on record, "
        f"{included} included."
    ]
    for key, label in (("min_max", "Min-Max"), ("pay_period", "Pay Period")):
        method = (drill.get("step1") or {}).get(key)
        if not method:
            continue
        verdict = "eligible" if method.get("eligible") else "not eligible"
        hours = _num(method.get("rounded_avg_weekly_hours") or method.get("avg_weekly_hours"))
        wages = _num(method.get("rounded_avg_weekly_wages") or method.get("avg_weekly_wages"))
        if hours is not None and wages is not None and floor_hours is not None:
            facts.append(
                f"{label}: {verdict} — {hours:.2f} hrs/week against {floor_hours:g}, "
                f"{_usd(wages)}/week against {_usd(floor_wages)}."
            )
        else:
            facts.append(f"{label}: {verdict}.")
    onezero = drill.get("onezero") or {}
    months = onezero.get("months") or []
    matrix = onezero.get("min_max") or []
    if months and matrix:
        def counted_in(row: dict[str, Any], index: int) -> bool:
            values = row.get("months") or []
            return index < len(values) and (_num(values[index]) or 0) > 0

        reached = sum(1 for i in range(len(months)) if any(counted_in(r, i) for r in matrix))
        units = sorted({str(r.get("unit_id")) for r in matrix})
        facts.append(
            f"Counted in {reached} of {len(months)} measuring months under Min-Max, at "
            f"{', '.join(units)}."
        )

    caveats = []
    if placeholder:
        caveats.append(f"TY{year}'s wage floor is a placeholder carried forward from TY{int(year) - 1}.")
    return {
        "page": "employee",
        "subject": f"employee {employee}",
        "headline": facts[0],
        "facts": facts,
        "caveats": caveats,
        "data": {"employee_id": employee, "tax_year": year, "periods": len(rows), "included": included},
    }


def _not_calculated(page: str, subject: str, payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message") or "No calculated run holds this yet. That is not a zero."
    return {
        "page": page, "subject": subject, "headline": message,
        "facts": [message], "caveats": [], "data": {"calculated": False},
    }


# ---------------------------------------------------------------------- check

#: A figure in prose: optional $, digits with separators, optional decimals,
#: optional k/m suffix. Years are figures too — a wrong year is a wrong fact.
_FIGURE = re.compile(r"(?<![\d.,])\$?(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\b")
#: Whole numbers this small are counts — months, positions, "two of six" — and
#: are checked by the reader, not by a pattern that would flag every list.
_SMALL_COUNT = 12


def _values(text: str) -> list[tuple[str, float, float]]:
    """(as written, value, the precision it was written to)."""
    out = []
    for match in _FIGURE.finditer(text):
        digits = match.group(1).replace(",", "")
        try:
            value = float(digits)
        except ValueError:
            continue
        decimals = len(digits.split(".", 1)[1]) if "." in digits else 0
        scale = {"k": 1_000, "m": 1_000_000}.get((match.group(2) or "").lower(), 1)
        out.append((match.group(0).strip(), value * scale, scale * 10 ** -decimals))
    return out


def unsupported_figures(text: str, brief: dict[str, Any]) -> list[str]:
    """Figures the summary states that appear nowhere in its brief.

    A figure passes if some brief figure ROUNDS to it at the precision it was
    written to — "$549k" for 548,730, "4.7" for 4.71 — and not otherwise, so a
    year two off ("TY2019" for TY2021) is caught rather than excused as close.
    Anything it cannot find is returned, and the page says so rather than
    letting a misstated number pass as one the system computed.
    """
    known = [value for _raw, value, _p in _values(json.dumps(brief, default=str, ensure_ascii=False))]
    missing: list[str] = []
    for raw, value, precision in _values(text or ""):
        if value <= _SMALL_COUNT and float(value).is_integer():
            continue
        if any(abs(value - k) <= precision / 2 + 1e-9 for k in known):
            continue
        if raw not in missing:
            missing.append(raw)
    return missing