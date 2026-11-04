"""`calc_walkthrough` and `employee_drill` — showing the working.

Both exist so a reader can ask "where did that number come from" and get the
engine's own answer: the calculation trail (`{step, inputs, formula, output,
citation}` plus a SHA-256 over it) and one employee's derivation by opaque
record token. Neither re-derives a certified figure.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.capabilities import _support as s
from application.capabilities import format as fmt
from application.capabilities.errors import InvalidArguments, NotCalculated, YearNotAuthored
from application.capabilities.envelope import Provenance, ToolResult


def _inline(values: Mapping[str, Any]) -> str:
    """`key=value` pairs, numbers printed exactly as the engine produced them."""
    parts = []
    for key in sorted(values):
        value = values[key]
        if value is None:
            rendered = s.ABSENT
        elif isinstance(value, (dict, list, tuple)):
            rendered = str(value)
        elif fmt.is_number(value) and not isinstance(value, str):
            rendered = fmt.number(value)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return ", ".join(parts)


def _trail_blocks(trail: Mapping[str, Any]) -> list:
    steps = trail.get("steps") or []
    blocks = [s.heading(str(trail.get("title") or "Calculation"))]
    if trail.get("citation"):
        blocks.append(s.paragraph(f"Citation: {trail['citation']}"))
    if steps:
        blocks.append(s.table(
            ("Step", "Inputs", "Formula", "Output", "Citation"),
            [
                (
                    str(step["step"]), _inline(step["inputs"]), str(step["formula"]),
                    _inline(step["output"]), str(step["citation"]),
                )
                for step in steps
            ],
        ))
    if trail.get("evidence_hash"):
        blocks.append(s.paragraph(f"Evidence hash: {trail['evidence_hash']}"))
    return blocks


def calc_walkthrough(
    client_id: int | None = None,
    tax_year: int | None = None,
    state: str = "GA",
    method: str = "min_max",
    *,
    trail: Mapping[str, Any] | None = None,
) -> ToolResult:
    """The calculation trail for a client-year.

    With `trail`, wraps one a caller already holds: the portal chat caches the
    trail its last answer recorded and re-narrates it, and rebuilding it would
    be a second computation of a figure already shown. Without it, the credit is
    re-read from the run that decided it and its steps are recorded afresh, and
    `client_id` and `tax_year` are required.
    """
    from tools.portfolio import chat_client_context, chat_state_credit

    if trail is not None:
        facts = dict(trail)
        provenance = Provenance(
            trail_sha256=str(facts.get("evidence_hash", "")).removeprefix("sha256:") or None,
            source="cached calculation trail",
        )
        return s.result("calc_walkthrough", facts, _trail_blocks(facts), provenance=provenance)

    if client_id is None or tax_year is None:
        raise InvalidArguments("client_id and tax_year are required to build a walkthrough")
    state = state.upper()
    s.statute(state, client_id, tax_year)
    capture = s.RunCapture()
    with s.trail_scope() as recorder:
        context = chat_client_context(
            account_id=client_id, tax_year=tax_year, method=s.read_method(method), on_run=capture,
        )
        if not context.get("calculated"):
            raise NotCalculated(
                f"No calculated run holds TY{tax_year} for this client. That is not a zero."
            )
        credit = chat_state_credit(
            state, tax_year=tax_year, account_id=client_id,
            current_average=context.get("current_average"),
            prior_average=context.get("prior_average"),
        )
        if credit.get("no_state_pack"):
            raise YearNotAuthored(str(credit["message"]))
        recorder.title = f"{credit['credit_name']} · TY{tax_year}"
        recorder.citation = str(credit["citation"])
        facts = recorder.to_dict()
        provenance = s.run_provenance(capture.run, recorder=recorder, source="tcc_gold")
    return s.result("calc_walkthrough", facts, _trail_blocks(facts), provenance=provenance)


def employee_drill(
    client_id: int,
    record_token: str,
    tax_year: int,
    state: str = "GA",
) -> ToolResult:
    """One employee's derivation for a client-year, keyed by opaque handle.

    Sensitive: the result names an employee. The handle is the record token the
    run minted — an employee id never travels in a request — and the drill
    states what it cannot show rather than rendering it empty.
    """
    from application.queries._client_run import ClientRunNotAvailable
    from application.queries.get_employee_drill import GetEmployeeDrillQuery
    from application.services import get_mediator

    try:
        query = GetEmployeeDrillQuery(
            record_token=record_token, tax_year=tax_year, state=state, account_id=client_id,
        )
        facts = get_mediator().send(query)
    except ClientRunNotAvailable as exc:
        raise s.refusal(exc) from exc
    except ValueError as exc:
        raise NotCalculated(str(exc)) from exc

    run = facts.get("run") or {}
    provenance = Provenance(run_id=run.get("run_id"), source="tcc_gold")
    blocks = [
        s.heading(f"Employee derivation · TY{s.cell(tax_year, 'year')}"),
        s.paragraph(
            "This employee is identified by an opaque record token. The derivation "
            "below is read from the run that decided eligibility; it is not recomputed."
        ),
    ]
    return s.result(
        "employee_drill", facts, blocks, provenance=provenance,
        warnings=["Sensitive: this result describes an individual employee."],
    )
