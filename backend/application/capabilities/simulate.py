"""`simulate` — what-if against the statutory engine.

Two functions, because the portal chat and the channel ask two different
questions and the repository holds a tool for each:

* `simulate` — one lever at one location of one client-year, priced exactly as
  the location grid prices it (`SimulateUnitQuery`). This is the channel's tool.
* `simulate_headcount` — "what if we hired N in <city>", the straight-line
  prototype the portal chat has always answered. It is not client-scoped and it
  says so in `warnings`.
"""
from __future__ import annotations

from application.capabilities import _support as s
from application.capabilities.errors import InvalidArguments, NotCalculated
from application.capabilities.envelope import Provenance, ToolResult

_STRAIGHT_LINE = (
    "A straight-line prototype model over the platform's configured payroll feed. "
    "It is not scoped to a client; use the location what-if for a client figure."
)


def simulate(
    client_id: int,
    tax_year: int,
    worksite_id: str,
    action: str = "add_headcount",
    magnitude: float = 1.0,
    state: str = "GA",
    method: str = "min_max",
    hire_weekly_hours: float | None = None,
    hire_hourly_rate: float | None = None,
) -> ToolResult:
    """One lever at one location, with the engine re-deciding everyone's eligibility.

    An open year's credit is a labelled run-rate and travels as `run_rate`; a
    closed year is priced outright. The base year refuses a lever, because moving
    it restates every later year rather than projecting one.
    """
    from application.queries.simulate_unit import SimulateUnitQuery, UnitSimulationNotAvailable
    from application.wiring import get_mediator

    try:
        query = SimulateUnitQuery(
            client_id=client_id, worksite_id=worksite_id, tax_year=tax_year,
            state=state, method=method, action=action, magnitude=magnitude,
            hire_weekly_hours=hire_weekly_hours, hire_hourly_rate=hire_hourly_rate,
        )
    except ValueError as exc:
        raise InvalidArguments(str(exc)) from exc
    try:
        facts = get_mediator().send(query)
    except UnitSimulationNotAvailable as exc:
        raise NotCalculated(str(exc)) from exc

    baseline, projected, delta = facts["baseline"], facts["projected"], facts["delta"]
    rows = [
        (label, s.cell(baseline[key], fmt), s.cell(projected[key], fmt), s.cell(delta[key], fmt))
        for label, key, fmt in (
            ("Average headcount", "average_headcount", "headcount"),
            ("Net new vs base", "net_new_vs_base", "headcount"),
            ("Annual credit", "annual_credit_usd", "money"),
            ("Credit over the series", "series_credit_usd", "money"),
        )
    ]
    blocks = [
        s.heading(f"{facts['scope']['worksite_id']} · TY{s.cell(tax_year, 'year')}"),
        s.paragraph(str(facts["detail"])),
        s.table(("Measure", "Baseline", "Projected", "Change"), rows),
    ]
    if facts.get("run_rate"):
        blocks.append(s.callout(str(facts["run_rate"]["note"])))
    return s.result(
        "simulate", facts, blocks,
        provenance=Provenance(run_id=facts.get("run_id"), source="tcc_gold"),
    )


def simulate_headcount(location: str, new_hires: int) -> ToolResult:
    """The portal chat's what-if: add or remove headcount in a city or state.

    Records its steps into the active trail recorder, which is how the chat
    shows the calculation. `new_hires=0` is refused by the tool and surfaces as
    `InvalidArguments`.
    """
    from tools.simulation import simulate_hiring

    with s.trail_scope() as recorder:
        try:
            facts = simulate_hiring(location=location, new_hires=new_hires)
        except ValueError as exc:
            raise InvalidArguments(str(exc)) from exc
        provenance = s.run_provenance(None, recorder=recorder, source="straight-line prototype model")

    baseline, projected, delta = facts["baseline"], facts["projected"], facts["delta"]
    rows = [
        ("Average headcount", s.cell(baseline["average_headcount"], "headcount"),
         s.cell(projected["average_headcount"], "headcount"), s.cell(new_hires, "count")),
        ("Net new headcount", s.cell(baseline["net_new_headcount"], "headcount"),
         s.cell(projected["net_new_headcount"], "headcount"), ""),
        ("Annual credit", s.cell(baseline["annual_credit_usd"], "money"),
         s.cell(projected["annual_credit_usd"], "money"), s.cell(delta["annual_credit_usd"], "money")),
        ("Lifetime credit", s.cell(baseline["lifetime_credit_usd"], "money"),
         s.cell(projected["lifetime_credit_usd"], "money"), s.cell(delta["lifetime_credit_usd"], "money")),
    ]
    blocks = [
        s.table(("Measure", "Baseline", "Projected", "Change"), rows),
        s.paragraph(f"Citation: {facts['citation']}"),
    ]
    return s.result("simulate", facts, blocks, provenance=provenance, warnings=[_STRAIGHT_LINE])
