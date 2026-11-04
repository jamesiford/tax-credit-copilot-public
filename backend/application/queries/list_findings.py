"""What agents found for one client-year, at the grain a human decides it.

This was the body of `api/findings.findings`. It moved so the channel's
`findings_list` capability can call it without importing a router; the router
now maps `FindingsNotAvailable` onto a 404 and nothing else changed.

The grain is the whole design. `detect_scraggly_pay_periods` returns one anomaly
per row, and on the real reference client that is **36,016 rows**. Thirty-six
thousand buttons is not a work queue — but it is not 36,016 decisions either. It
is one: "do periods below $50 and 4 hours count toward the denominator, or not?"
Answer once, applies to the population. Test-of-twos is genuinely per-instance:
each employee-month needs its own answer to "which worksite owns this head?".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from domain.calculation.headcount import row_state
from application.source_ports import load_pay_periods

# What each kind of finding means, what an agent proposes, and — crucially —
# the GRAIN a human actually decides at.
KINDS = {
    "test_of_twos": {
        "title": "Employee counted at two worksites in one month",
        "grain": "policy_with_exceptions",
        "why": (
            "The engine counts headcount per unit, so a person appearing at two "
            "worksites in the same month is counted twice. That inflates Average "
            "Headcount, which inflates the credit."
        ),
        "proposes": "assign",
        "effect": "Counts the employee at their dominant worksite for that month.",
    },
    "meaningful_pay_period": {
        "title": "Pay periods too small to be real periods",
        "grain": "policy",
        "why": (
            "A period with almost no hours or wages still adds weeks to the "
            "denominator, which lowers the weekly average and can push someone "
            "below a statutory floor they actually clear. Whether such periods "
            "count is one policy question, not one question per period."
        ),
        "proposes": "drop",
        "effect": "Excludes every period below the threshold from the denominator.",
    },
}

# How many examples to carry on a policy finding. Enough to judge the pattern,
# far short of a dump.
SAMPLE_SIZE = 5

# When one worksite holds at least this share of an employee's hours for the
# month, which unit owns the head is not a judgement call — it is arithmetic.
# Below it the split is genuinely ambiguous and a person should look.
#
# On the reference client this is the difference between 3,797 decisions and a
# couple of dozen. A queue nobody can finish is a queue nobody starts.
DOMINANCE = 0.75

# Above this many exceptions, individual review stops being realistic and the
# exceptions are themselves a pattern. A hospitality client with three thousand
# employees splitting hours evenly across two sites does not have three thousand
# anomalies — it has one payroll characteristic, and what it needs is a tie-break
# rule plus a sample to sanity-check.
#
# The general principle: **grain follows volume.** A handful of exceptions is a
# work queue; thousands is a policy question wearing a work queue's clothes.
INSTANCE_CAP = 25


@dataclass(frozen=True)
class ListFindingsQuery(Query):
    """Every finding for one client-year, with its resolution if it has one."""

    client_id: int
    tax_year: int
    state: str | None = None


class FindingsNotAvailable(LookupError):
    """No payroll for this client in the active data source."""


def dominant_unit(anomaly: dict[str, Any]) -> tuple[dict[str, Any] | None, float]:
    """The worksite holding most of the month's hours, and its share."""
    units = anomaly.get("units") or []
    total = sum(float(u.get("hours") or 0) for u in units)
    if not units or total <= 0:
        return None, 0.0
    top = max(units, key=lambda u: float(u.get("hours") or 0))
    return top, float(top.get("hours") or 0) / total


def is_ambiguous(anomaly: dict[str, Any]) -> bool:
    """True when no worksite clearly dominates, so a human must choose."""
    _top, share = dominant_unit(anomaly)
    return share < DOMINANCE


def finding_id(anomaly: dict[str, Any]) -> str:
    """Stable across runs, so a decision sticks to the finding it answered."""
    if anomaly.get("type") == "test_of_twos":
        return f"t2:{anomaly.get('employee_id')}:{anomaly.get('month')}"
    return f"pp:{anomaly.get('employee_id')}:{anomaly.get('worksite_id')}:{anomaly.get('pay_date')}"


def policy_finding_id(kind: str, tax_year: int, state: str | None) -> str:
    """One id per policy question per client-year, not one per instance."""
    return f"policy:{kind}:{state or 'ALL'}:{tax_year}"


def roll_up_policy(
    kind: str, anomalies: list[dict[str, Any]], tax_year: int, state: str | None,
) -> dict[str, Any]:
    """Collapse a population of instances into the one decision behind them.

    Carries the size, who is affected, the total at stake, and a handful of
    examples — enough to judge the pattern. Deliberately NOT the full list: a
    reviewer answering a policy question does not read 36,016 rows, and offering
    them is how a work queue becomes a database browser.
    """
    employees = {a.get("employee_id") for a in anomalies if a.get("employee_id")}

    # Money and hours live at different depths by kind: a scraggly period
    # carries them on the row, a test-of-twos on its per-unit breakdown. Summing
    # only the top level renders "$0 / 0 hours" beside three thousand affected
    # employees, which reads as "nothing at stake" — the opposite of true.
    wages = hours = 0.0
    for anomaly in anomalies:
        units = anomaly.get("units")
        if units:
            wages += sum(float(u.get("wages") or 0) for u in units)
            hours += sum(float(u.get("hours") or 0) for u in units)
        else:
            wages += float(anomaly.get("wages") or 0)
            hours += float(anomaly.get("hours") or 0)

    return {
        "instances": len(anomalies),
        "employees_affected": len(employees),
        "total_wages": round(wages, 2),
        "total_hours": round(hours, 2),
        "sample": anomalies[:SAMPLE_SIZE],
        "sample_of": len(anomalies),
    }


def detect(client_id: int, tax_year: int, state: str | None) -> list[dict[str, Any]]:
    from tools.qc import run_exception_report

    rows = load_pay_periods(client_id)
    if not rows:
        # A named tenant with no rows is a different fact from an absent
        # dataset, and must never fall through to another client's payroll.
        raise FindingsNotAvailable(f"No payroll for client {client_id} in the active data source.")
    if state:
        rows = [r for r in rows if row_state(r) == state.upper()]
    report = run_exception_report(rows, tax_year=tax_year, state=state)
    return list(report["test_of_twos"]) + list(report["meaningful_pay_period"])


def handle_list_findings(query: ListFindingsQuery) -> dict[str, Any]:
    """Everything an agent found for one client-year, at the grain it is decided at.

    Instance-grain kinds (test-of-twos) list individually, because each needs its
    own answer. Policy-grain kinds (trivial pay periods) roll up into a single
    finding covering the population — on the reference client that turns 36,016
    rows into one question, which is the number of decisions it actually is.

    An unresolved finding is counted separately rather than blending into the
    list: a judgement nobody has made is not the same as one that was made and
    happened to be "accept".
    """
    from application.services import get_finding_repository

    client_id, tax_year, state = query.client_id, query.tax_year, query.state
    repo = get_finding_repository()
    decided = {r.finding_id: r for r in repo.live(client_id, tax_year)}

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for anomaly in detect(client_id, tax_year, state):
        by_kind.setdefault(anomaly.get("type") or "unknown", []).append(anomaly)

    items: list[dict[str, Any]] = []
    for kind, anomalies in by_kind.items():
        meta = KINDS.get(kind, {})
        grain = meta.get("grain", "instance")

        if grain == "policy":
            fid = policy_finding_id(kind, tax_year, state)
            resolution = decided.get(fid)
            items.append({
                "finding_id": fid,
                "kind": kind,
                "grain": "policy",
                "title": meta.get("title", kind),
                "why_it_matters": meta.get("why", ""),
                "proposes": meta.get("proposes"),
                "proposed_effect": meta.get("effect", ""),
                "employee_id": None,
                "population": roll_up_policy(kind, anomalies, tax_year, state),
                "evidence": {"type": kind, "units": []},
                "resolution": resolution.to_dict() if resolution else None,
                "requires_decision": resolution is None,
            })
            continue

        if grain == "policy_with_exceptions":
            # One rule for the clear-cut majority, plus the genuinely ambiguous
            # ones listed individually. Asking a reviewer to confirm 120h-vs-4h
            # three thousand times is not review, it is attrition.
            clear = [a for a in anomalies if not is_ambiguous(a)]
            ambiguous = [a for a in anomalies if is_ambiguous(a)]

            if clear:
                fid = policy_finding_id(kind, tax_year, state)
                resolution = decided.get(fid)
                rolled = roll_up_policy(kind, clear, tax_year, state)
                rolled["dominance_threshold"] = DOMINANCE
                items.append({
                    "finding_id": fid,
                    "kind": kind,
                    "grain": "policy",
                    "title": f"{meta.get('title', kind)} — clear-cut",
                    "why_it_matters": (
                        f"{meta.get('why', '')} In these one worksite holds at least "
                        f"{int(DOMINANCE * 100)}% of the month's hours, so which unit "
                        f"owns the head is arithmetic rather than a judgement."
                    ),
                    "proposes": "assign",
                    "proposed_effect": (
                        "Counts each employee at their dominant worksite for that month."
                    ),
                    "employee_id": None,
                    "population": rolled,
                    "evidence": {"type": kind, "units": []},
                    "resolution": resolution.to_dict() if resolution else None,
                    "requires_decision": resolution is None,
                })

            if ambiguous and len(ambiguous) > INSTANCE_CAP:
                # Too many to review one at a time, so they are a pattern rather
                # than a queue. Offer the tie-break rule and a sample.
                fid = policy_finding_id(f"{kind}_split", tax_year, state)
                resolution = decided.get(fid)
                rolled = roll_up_policy(kind, ambiguous, tax_year, state)
                rolled["instance_cap"] = INSTANCE_CAP
                items.append({
                    "finding_id": fid,
                    "kind": kind,
                    "grain": "policy",
                    "title": f"{meta.get('title', kind)} — split evenly",
                    "why_it_matters": (
                        f"{meta.get('why', '')} In these the hours are split closely "
                        f"enough that no worksite obviously owns the head. There are too "
                        f"many to judge one at a time, which usually means it is a "
                        f"characteristic of this client's payroll rather than an anomaly "
                        f"— staff genuinely working across sites. Choose a tie-break rule."
                    ),
                    "proposes": "assign",
                    "proposed_effect": (
                        "Counts each employee at whichever of their worksites holds the "
                        "most hours that month, breaking ties on wages."
                    ),
                    "employee_id": None,
                    "population": rolled,
                    "evidence": {"type": kind, "units": []},
                    "resolution": resolution.to_dict() if resolution else None,
                    "requires_decision": resolution is None,
                })
                continue

            for anomaly in ambiguous:
                fid = finding_id(anomaly)
                resolution = decided.get(fid)
                items.append({
                    "finding_id": fid,
                    "kind": kind,
                    "grain": "instance",
                    "title": f"{meta.get('title', kind)} — split evenly",
                    "why_it_matters": (
                        f"{meta.get('why', '')} Here the hours are split closely enough "
                        f"that no worksite obviously owns the head, so this one needs a "
                        f"person."
                    ),
                    "proposes": meta.get("proposes"),
                    "proposed_effect": meta.get("effect", ""),
                    "employee_id": anomaly.get("employee_id"),
                    "population": None,
                    "evidence": anomaly,
                    "resolution": resolution.to_dict() if resolution else None,
                    "requires_decision": resolution is None,
                })

    open_count = sum(1 for i in items if i["requires_decision"])
    return {
        "client_id": client_id,
        "tax_year": tax_year,
        "state": state.upper() if state else None,
        "findings": sorted(items, key=lambda i: (not i["requires_decision"], i["finding_id"])),
        "summary": {
            # DECISIONS, not instances. The number that matters to whoever has
            # to work through this.
            "total": len(items),
            "requires_decision": open_count,
            # The underlying population, so "one decision" never reads as "one
            # row" and understates what is at stake.
            "instances": sum(len(v) for v in by_kind.values()),
            # Not "clean" — clean would imply nothing was found. This says the
            # findings that exist have all been answered.
            "all_decided": len(items) > 0 and open_count == 0,
            "none_found": len(items) == 0,
            "by_kind": {kind: len(v) for kind, v in by_kind.items()},
        },
    }
