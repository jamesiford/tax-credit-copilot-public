"""Who qualifies, for a given client, programme and tax year.

The eligible population was only ever available for the certified reference run:
`api/workspace.py` served one sealed singleton, so "who qualifies" could answer
for Candle Bottle and for nobody else. That made the product look like a
one-client demo, when the engine behind it has been per-client all along.

This is the query that closes it. Three facts are resolved separately and
deliberately, because conflating them is what pinned the old path to one client:

- **The statute** comes from the year pack for `(programme, tax_year)`. A year
  with no authored pack is DECLINED by name, never priced from a neighbour
  [ADR-005].
- **The fiscal window** is a fact about the client, read from their own
  `EntityFiscalYearRules`. When the client has no rule on file the window is a
  flagged calendar assumption, and the flag travels with the answer.
- **The methodology** is the assumption set, and is global. The same Min-Max
  span is measured the same way for every client.

Both methods run, and both results are returned per employee. They are not
expected to agree with each other — they are expected to agree with the partner's
implementation of that method — so publishing one with a caveat attached would
be the wrong shape.

A query: it computes and returns, and changes nothing. It calls the same
certified engine that yields 10,236 / 539 / 656, so it must never be able to
move those figures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.queries._client_run import ClientRunNotAvailable

# The router catches this by name, and so do the tests.
EligibilityNotAvailable = ClientRunNotAvailable

_STATUSES = ("all", "both", "min_max_only", "pay_period_only", "neither")
#: Mirrors `gold_reader.ELIGIBILITY_SORTS`. Named here so a bad key is a 422
#: at the door rather than a silent fall-back to employee order.
_SORTS = (
    "employee_id", "status", "near_floor", "total_hours", "total_wages",
    "mm_weeks", "mm_hours", "pp_weeks", "pp_hours",
)


@dataclass(frozen=True)
class GetEligibilityQuery(Query):
    """The per-employee eligibility population for one client-programme-year."""

    tax_year: int
    state: str
    account_id: int | None = None
    status: str = "all"
    near_floor: bool = False
    q: str = ""
    limit: int = 50
    offset: int = 0
    sort: str = "employee_id"
    order: str = "asc"

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}, got {self.status!r}")
        if self.limit < 1 or self.limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if self.offset < 0:
            raise ValueError("offset cannot be negative")
        if self.sort not in _SORTS:
            raise ValueError(f"sort must be one of {_SORTS}, got {self.sort!r}")
        if self.order not in ("asc", "desc"):
            raise ValueError("order must be asc | desc")


def _verdict(
    row: dict[str, Any], prefix: str, floors
) -> dict[str, Any]:
    """One method's reading of one employee, as Gold recorded it.

    `eligible` is READ, never recomputed. It is what the run decided under the
    rule pack the run recorded, and re-deriving it here would be a second
    opinion about a certified number. `passed_hours` / `passed_wages` are not
    stored — they are the two halves of that verdict, shown so a reader can see
    WHICH floor a person missed.
    """
    hours = row.get(f"{prefix}_hours")
    if hours is None:
        return {
            "weeks": None, "avg_hours": None, "avg_wages": None,
            "passed_hours": False, "passed_wages": False, "eligible": False,
        }
    hours = float(hours)
    wages = float(row.get(f"{prefix}_wages") or 0)
    return {
        "weeks": float(row.get(f"{prefix}_weeks") or 0),
        "avg_hours": hours,
        "avg_wages": wages,
        "passed_hours": hours >= float(floors.min_weekly_hours),
        "passed_wages": wages >= float(floors.min_weekly_wages),
        "eligible": bool(row.get(f"{prefix}_eligible")),
    }


#: Within 5% of a floor, on the failing side. Applied in SQL so the count over
#: the whole population costs one statement; repeated here only for the rows on
#: the page, which SQL has already flagged.
NEAR_FLOOR_BAND = 0.05


def handle_get_eligibility(query: GetEligibilityQuery) -> dict[str, Any]:
    """Who qualifies, read from the run that decided it.

    This handler used to replay `run_min_max_method` and `run_pay_period_method`
    over the client's whole payroll on every page load. Both had already run —
    at write time, under a recorded rule pack version — and their per-employee
    verdicts are in `tcc_gold.employee_eligibility`. Reading them means the
    screen shows the certified figures rather than a recomputation that has to
    agree with them.

    Statute and fiscal window are still resolved, because the page states both
    and because the floors draw the near-floor band. Payroll is not loaded.
    """
    from application.wiring import get_gold_reader
    from application.queries._client_run import resolve_statute

    resolved = resolve_statute(
        account_id=query.account_id, state=query.state, tax_year=query.tax_year
    )
    floors = resolved.floors

    if query.account_id is None:
        raise ClientRunNotAvailable(
            "an eligibility population is a fact about one client; select one"
        )

    reader = get_gold_reader()
    with reader.scope():
        read = reader.eligibility_population(
            query.account_id,
            tax_year=query.tax_year,
            min_weekly_hours=float(floors.min_weekly_hours),
            min_weekly_wages=float(floors.min_weekly_wages),
            band=NEAR_FLOOR_BAND,
            status=query.status,
            near_floor=query.near_floor,
            q=query.q,
            limit=query.limit,
            offset=query.offset,
            sort=query.sort,
            order=query.order,
        )

    base = {
        "account_id": query.account_id,
        "state": resolved.state,
        "program_code": resolved.program_code,
        "tax_year": query.tax_year,
        "thresholds": floors.as_dict(),
        # `as_dict` carries the PILOT-07 disclosure — `assumed`, and what each
        # labelling convention would have produced. A hand-rolled subset here
        # dropped exactly that, which is the part a reviewer needs to see.
        "fiscal": resolved.window.as_dict(),
    }

    summary = read["summary"]
    if summary is None:
        # Never a zero. "Nobody qualifies" and "we have not looked" are
        # different answers, and only one is about this client's payroll.
        return {
            **base,
            "calculation_state": "not_calculated",
            "message": (
                f"TY{query.tax_year} has not been calculated for this client. "
                f"It carries no figure — not a zero."
            ),
            "run": read["run"],
            "employees_evaluated": 0, "min_max_eligible": 0,
            "pay_period_eligible": 0, "near_floor": 0, "eligible_either_method": 0,
            "reconciliation": {}, "total": 0, "rows": [],
        }

    rows = [
        {
            "record_token": row["record_token"],
            "employee_id": row["employee_id"],
            "status": row["status"],
            "near_floor": bool(row["near_floor"]),
            "totals": {
                "hours": float(row.get("total_hours") or 0),
                "wages": float(row.get("total_wages") or 0),
            },
            "min_max": _verdict(row, "mm", floors),
            "pay_period": _verdict(row, "pp", floors),
        }
        for row in read["rows"]
    ]

    return {
        **base,
        "calculation_state": "calculated",
        "run": read["run"],
        # `eligible` is READ from the run; the two `passed_*` halves and the
        # near-floor band are drawn from the floors resolved NOW. This states
        # whether they are the same ruler, rather than leaving a reader to
        # discover a contradiction in a row. The manifest's `rule_pack_version`
        # cannot answer it — it is stamped once per run, and a run spans years.
        "statute_matches_run": {
            "matches": int(summary.get("verdict_disagreements") or 0) == 0,
            "verdict_disagreements": int(summary.get("verdict_disagreements") or 0),
            "resolved_rule_pack_source": floors.as_dict().get("source"),
        },
        # These are the certified counts and a filter must never move them:
        # they are a statement about the client, not about what the reader
        # narrowed to. `total` below is the filtered denominator for paging.
        "employees_evaluated": int(summary["employees_evaluated"]),
        "min_max_eligible": int(summary["min_max_eligible"]),
        "pay_period_eligible": int(summary["pay_period_eligible"]),
        "near_floor": int(summary["near_floor"]),
        "eligible_either_method": int(summary["eligible_either"]),
        "reconciliation": {
            "eligible_both": int(summary["eligible_both"]),
            "min_max_only": int(summary["min_max_only"]),
            "pay_period_only": int(summary["pay_period_only"]),
            "neither": int(summary["neither"]),
        },
        "total": read["matching"],
        "rows": rows,
    }
