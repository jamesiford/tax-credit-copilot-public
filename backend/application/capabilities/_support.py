"""Small helpers every capability module shares.

Kept private (`_support`) because nothing outside the package should depend on
how a block is laid out or how a trail hash is lifted off a recorder.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from application.capabilities import format as fmt
from application.capabilities.envelope import Block, Provenance, ToolResult
from application.capabilities.errors import CapabilityError, NotCalculated, YearNotAuthored
from domain.calculation.trail import (
    TrailRecorder,
    current_recorder,
    reset_recorder,
    set_recorder,
)

#: Shown where a figure is absent. Never a zero: "we have not looked" and "we
#: looked and found nothing" are different statements.
ABSENT = "—"


def result(
    tool: str,
    facts: dict[str, Any],
    blocks: Iterable[Block] = (),
    *,
    provenance: Provenance | None = None,
    warnings: Iterable[str] = (),
) -> ToolResult:
    return ToolResult(
        tool=tool,
        facts=facts,
        blocks=tuple(blocks),
        provenance=provenance or Provenance(),
        warnings=tuple(warnings),
    )


# ------------------------------------------------------------------ provenance


def trail_sha256(recorder: TrailRecorder | None) -> str | None:
    """The SHA-256 over the recorder's canonical trail, or None with no steps.

    The recorder's own `evidence_hash` carries a `sha256:` prefix; the envelope
    field is the bare digest.
    """
    if recorder is None or not recorder.steps:
        return None
    return recorder.to_dict()["evidence_hash"].removeprefix("sha256:")


def run_provenance(
    run: Mapping[str, Any] | None,
    *,
    recorder: TrailRecorder | None = None,
    source: str | None = None,
) -> Provenance:
    """Provenance from a Gold run row. A field the run does not carry stays None."""
    run = run or {}
    assumption_sets = [
        str(run[key]) for key in ("step1_assumption_set_id", "onezero_assumption_set_id")
        if run.get(key)
    ]
    return Provenance(
        run_id=str(run["run_id"]) if run.get("run_id") else None,
        rule_pack_version=str(run["rule_pack_version"]) if run.get("rule_pack_version") else None,
        assumption_set_id=" + ".join(assumption_sets) or None,
        trail_sha256=trail_sha256(recorder),
        source=source,
    )


class RunCapture:
    """Collects the run a tool read from, via the tools' `on_run` hook."""

    def __init__(self) -> None:
        self.run: Mapping[str, Any] | None = None

    def __call__(self, run: Mapping[str, Any]) -> None:
        self.run = run


@contextmanager
def trail_scope(title: str = "Pending") -> Iterator[TrailRecorder]:
    """The recorder tools write their calculation steps into.

    Reuses the one already active. The portal chat sets its own around a whole
    pipeline and later emits it as the `calculation_trail` event; a capability
    that swapped in a private recorder would make those steps vanish from the
    chat. With none active — the channel — it opens one and closes it again.
    """
    active = current_recorder()
    if active is not None:
        yield active
        return
    recorder = TrailRecorder(title=title, citation="")
    token = set_recorder(recorder)
    try:
        yield recorder
    finally:
        reset_recorder(token)


def refusal(exc: Exception) -> CapabilityError:
    """A query's `ClientRunNotAvailable`, as the typed error a caller can act on.

    The query raises one exception for two different facts — the statute is not
    authored, or no run holds the figure — and only the message tells them
    apart. The statute messages are the ones that say "rule pack" or cite
    ADR-005, so those are the declines [ADR-005]; everything else is a client-year
    nobody has calculated.
    """
    text = str(exc)
    lowered = text.lower()
    if "rule pack" in lowered or "no programme maps" in lowered or "adr-005" in lowered:
        return YearNotAuthored(text)
    return NotCalculated(text)


def read_method(method: str) -> str:
    """The method a Gold headcount read takes. `both` has no single answer, so
    it reads the pay-period average the portal has always used."""
    return method if method in ("min_max", "pay_period") else "pay_period"


def statute(state: str, client_id: int, tax_year: int):
    """The statute and fiscal window for a client-year, or the named refusal.

    Resolves no payroll. An unmapped state and an unauthored year are real gaps
    in coverage, and pricing either from a neighbour is a wrong answer wearing a
    right one's costume [ADR-005].
    """
    from application.queries._client_run import ClientRunNotAvailable, resolve_statute

    try:
        return resolve_statute(account_id=client_id, state=state.upper(), tax_year=tax_year)
    except ClientRunNotAvailable as exc:
        raise YearNotAuthored(str(exc)) from exc


# ---------------------------------------------------------------------- blocks


def heading(text: str) -> Block:
    return Block("heading", text=text)


def paragraph(text: str) -> Block:
    return Block("paragraph", text=text)


def callout(text: str) -> Block:
    return Block("callout", text=text)


def bullets(items: Sequence[str]) -> Block:
    return Block("bullets", rows=tuple((item,) for item in items))


def table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> Block:
    return Block("table", rows=(tuple(header), *(tuple(r) for r in rows)))


def cell(value: Any, formatter: str) -> str:
    """One table cell. None is `ABSENT`; a value the formatter refuses prints
    as the text it is, never as a guess."""
    if value is None:
        return ABSENT
    try:
        return fmt.format_value(value, formatter)
    except ValueError:
        return str(value)
