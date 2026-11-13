"""Run one batch item by calling the existing commands. There is one implementation of a run, and this is not it. [ADR-012]

The executor decides *what* to ask (which programme, which year, whether the last run already answers it) and maps
every way the asking can end onto an item outcome. The calculation, the Gold write and the claim assessment are
`RunClientCalculationCommand` and `AssessClientCommand`, untouched.

Failure mapping is the part worth reading. A failure is retried only if a later attempt can plausibly cure it:
a store or lakehouse that could not be reached, a timeout, a write conflict. A request the data cannot satisfy
(no payroll, an unauthored year) is a *skip* with the reason, never a failure and never a zero. Everything else
(an unmapped pay code, a schema mismatch, a section 9 violation, a bug) fails once and says why.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from application.errors import DependencyUnavailable, PROGRAMMING_ERRORS, as_dependency_failure
from application.gold_ports import GoldWriteFailed
from application.runs.fingerprint import (
    current_assumptions, current_code_commit, current_fingerprint, manifest_fingerprint,
)
from domain.runs import BatchKind, ItemResult, ItemStatus, RunBatch, RunBatchItem, unchanged_decision

log = logging.getLogger("tcc.runs")

#: Named dependencies whose outage is worth retrying (see `application/errors.py` for the convention).
#: The named cause of a Gold write that did not hold (a section 9 violation such as more than one current run for a
#: client and program, or the writer failing). Shown in the batch's failures by cause.
GOLD_WRITE = "gold_write"
GOLD_WRITE_MESSAGE = (
    "The Gold write did not validate ({detail}). Gold may briefly hold rows of more than one run for this client. "
    "It is retried once with no other worker on the client; if it fails again, run the client alone and check section 9 "
    "(`python backend/tools/verify_gold_reads.py`) before trusting its figures."
)
_TRANSIENT_DEPENDENCIES = frozenset({"source_lakehouse", "source_sql", "operational_store", "claims_store", "warehouse"})


@dataclass(frozen=True)
class ItemOutcome:
    """How one item ended: the status, what to record, and whether a retry could help."""
    status: ItemStatus
    run_id: str | None = None
    skip_reason: str | None = None
    error_dependency: str | None = None
    error_message: str | None = None
    tax_year: int | None = None
    program_code: str | None = None
    transient: bool = False
    #: A Gold write that did not validate: retried once under the client lock, then it stays failed. [F04b.3]
    retry_once: bool = False

    def result(self) -> ItemResult:
        """The part the queue stores."""
        return ItemResult(self.status, self.run_id, self.skip_reason, self.error_dependency, self.error_message, self.tax_year)


class Skip(Exception):
    """The item cannot run because the data or statute does not support it. Not a failure."""


class Refuse(Exception):
    """The item is ambiguous or invalid as asked. A failure that retrying will not cure."""


class Collaborators:
    """The reads and the dispatcher an item needs, as functions so a test can supply fakes."""

    def __init__(
        self, *, send: Callable[[Any], Any] | None = None, client_scope: Callable[[int], dict[str, Any]] | None = None,
        resolve_run: Callable[..., Any] | None = None, latest_manifest: Callable[[int, str], Any] | None = None,
        assumptions: Callable[[], list[dict[str, str]]] = current_assumptions,
        code_commit: Callable[[], str] = current_code_commit,
    ) -> None:
        self.send = send or _real_send
        self.client_scope = client_scope or _real_scope
        self.resolve_run = resolve_run or _real_resolve
        self.latest_manifest = latest_manifest or _real_latest
        self.assumptions, self.code_commit = assumptions, code_commit


def _real_send(command: Any) -> Any:
    from application.services import get_mediator

    return get_mediator().send(command)


def _real_scope(client_id: int) -> dict[str, Any]:
    from application.queries.get_scope import GetClientScopeQuery, handle_get_client_scope

    return handle_get_client_scope(GetClientScopeQuery(account_id=client_id))


def _real_resolve(*, account_id: int, state: str, tax_year: int) -> Any:
    from application.queries._client_run import resolve_client_run

    return resolve_client_run(account_id=account_id, state=state, tax_year=tax_year)


def _real_latest(client_id: int, program_code: str) -> Any:
    from application.services import get_run_manifest_repository

    return get_run_manifest_repository().latest(client_id, program_code=program_code)


def _covers(program: dict[str, Any], calculable: set[int], wanted: str | None) -> bool:
    """A state programme that is the one asked for (if any was) and has statute over a payroll year."""
    named = not wanted or program["program_code"] == wanted
    return program["jurisdiction"]["level"] == "state" and named and bool(calculable & set(program["authored_years"]))


def _program_for(scope: dict[str, Any], batch: RunBatch, item: RunBatchItem) -> dict[str, Any]:
    """The one state programme with authored statute over this client's payroll years, or `Skip` / `Refuse`."""
    calculable = set(scope.get("calculable_years") or [])
    wanted = item.program_code or batch.program_code
    candidates = [p for p in scope.get("programs") or [] if _covers(p, calculable, wanted)]
    if not candidates:
        raise Skip("no programme with authored statute covers this client's payroll years")
    if len(candidates) > 1:
        raise Refuse("the client is covered by several programmes (" + ", ".join(p["program_code"] for p in candidates)
                     + "); name one with program_code")
    return candidates[0]


def choose_target(scope: dict[str, Any], batch: RunBatch, item: RunBatchItem) -> tuple[str, str, int]:
    """`(state, program_code, tax_year)` for an item from the client's scope, or raise `Skip` / `Refuse`."""
    program = _program_for(scope, batch, item)
    usable = sorted(set(scope.get("calculable_years") or []) & set(program["authored_years"]))
    year = item.tax_year or batch_default_year(scope, usable)
    if year not in usable:
        raise Skip(f"TY{year} is not calculable for this client: no payroll in its fiscal window or no authored statute")
    return program["jurisdiction"]["code"], program["program_code"], int(year)


def batch_default_year(scope: dict[str, Any], usable: list[int]) -> int:
    default = scope.get("default_year")
    return int(default) if default in usable else int(usable[-1])


class ItemExecutor:
    """Runs one item through the existing commands and turns every ending into an outcome."""
    def __init__(self, collaborators: Collaborators | None = None) -> None:
        self._c = collaborators or Collaborators()

    def execute(self, batch: RunBatch, item: RunBatchItem, on_target: Callable[[int, str], None] | None = None) -> ItemOutcome:
        """Run one item. Never raises: every ending is an outcome."""
        year, program = item.tax_year, item.program_code
        try:
            state, program, year = choose_target(self._c.client_scope(item.client_id), batch, item)
            if on_target:
                on_target(year, program)
            return self._act(batch, item, state, program, year)
        except Skip as skip:
            return ItemOutcome(ItemStatus.SKIPPED_NO_PAYROLL, skip_reason=str(skip), tax_year=year, program_code=program)
        except Refuse as refusal:
            return ItemOutcome(ItemStatus.FAILED, error_dependency="validation", error_message=str(refusal),
                               tax_year=year, program_code=program)
        except Exception as exc:  # noqa: BLE001 - classified: every failure becomes an item outcome
            return classify(exc, year, program)

    def _act(self, batch: RunBatch, item: RunBatchItem, state: str, program: str, year: int) -> ItemOutcome:
        explicit = (year,) if item.tax_year else ()
        if batch.kind is BatchKind.ASSESS:
            from application.commands.assess_client import AssessClientCommand

            self._c.send(AssessClientCommand(client_id=item.client_id, program_code=program, tax_years=explicit,
                                             actor=batch.requested_by))
            return ItemOutcome(ItemStatus.SUCCEEDED, tax_year=year, program_code=program)
        run = self._c.resolve_run(account_id=item.client_id, state=state, tax_year=year)
        if batch.skip_unchanged and not batch.force:
            same, why = unchanged_decision(
                manifest_fingerprint(self._c.latest_manifest(item.client_id, run.program_code)),
                current_fingerprint(run, self._c.assumptions(), self._c.code_commit()),
                include_code_commit=batch.include_code_commit,
            )
            if same:
                return ItemOutcome(ItemStatus.SKIPPED_UNCHANGED, skip_reason=why, tax_year=year, program_code=program)
        from application.commands.run_client_calculation import RunClientCalculationCommand

        narrow = (year,) if batch.kind is BatchKind.CALCULATE else ()
        result = self._c.send(RunClientCalculationCommand(
            client_id=item.client_id, tax_year=year, state=state, actor=batch.requested_by, assess_tax_years=narrow))
        return ItemOutcome(ItemStatus.SUCCEEDED, run_id=result.get("run_id"), tax_year=year, program_code=program)


def _declined(exc: BaseException, common: dict[str, Any]) -> ItemOutcome | None:
    """The outcomes that are not a plain failure: a request the data cannot satisfy, or a Gold write that did not hold."""
    from application.commands.assess_client import ClientHasNoPayroll
    from application.queries._client_run import ClientRunNotAvailable
    from application.queries.get_scope import NoPayrollForScope, NoResolvableWorkState, UnknownClient

    if isinstance(exc, GoldWriteFailed):
        return ItemOutcome(ItemStatus.FAILED, error_dependency=GOLD_WRITE, error_message=GOLD_WRITE_MESSAGE.format(detail=str(exc)[:300]),
                           retry_once=True, **common)
    if isinstance(exc, (ClientHasNoPayroll, ClientRunNotAvailable, NoPayrollForScope, NoResolvableWorkState, UnknownClient)):
        return ItemOutcome(ItemStatus.SKIPPED_NO_PAYROLL, skip_reason=str(exc)[:500], **common)
    return None


def classify(exc: BaseException, year: int | None, program: str | None) -> ItemOutcome:
    """Map an exception onto an outcome. See the module docstring for the rule."""
    common = {"tax_year": year, "program_code": program}
    declined = _declined(exc, common)
    if declined is not None:
        return declined
    if _is_conflict(exc):
        return ItemOutcome(ItemStatus.FAILED, error_dependency="conflict", error_message="a write conflict on the warehouse",
                           transient=True, **common)
    if isinstance(exc, DependencyUnavailable):
        transient = type(exc) is DependencyUnavailable and exc.dependency in _TRANSIENT_DEPENDENCIES
        return ItemOutcome(ItemStatus.FAILED, error_dependency=exc.dependency, error_message=f"{exc.reason} {exc.remedy}",
                           transient=transient, **common)
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ItemOutcome(ItemStatus.FAILED, error_dependency="timeout", error_message=f"{type(exc).__name__}",
                           transient=True, **common)
    if isinstance(exc, ValueError):
        return ItemOutcome(ItemStatus.FAILED, error_dependency="validation", error_message=str(exc)[:500], **common)
    if isinstance(exc, PROGRAMMING_ERRORS):
        log.exception("run item failed on a programming error")
        return ItemOutcome(ItemStatus.FAILED, error_dependency="internal", error_message=f"{type(exc).__name__}: see the log",
                           **common)
    typed = as_dependency_failure("operational_store", exc)
    name = typed.dependency if typed else "internal"
    message = f"{typed.reason} {typed.remedy}" if typed else type(exc).__name__
    return ItemOutcome(ItemStatus.FAILED, error_dependency=name, error_message=message,
                       transient=name in _TRANSIENT_DEPENDENCIES, **common)


_CONFLICT_NUMBERS = ("24556", "3960", "1205")


def _is_conflict(exc: BaseException) -> bool:
    """A snapshot-isolation write conflict or deadlock, by the same numbers `tenant_sql` retries on.

    The writer already retries these in its own transaction; one that still escapes is worth a later attempt.
    """
    text = " ".join(str(a) for a in getattr(exc, "args", ()) or ()) or str(exc)
    low = text.lower()
    return any(f"({n})" in text for n in _CONFLICT_NUMBERS) or "snapshot isolation transaction aborted" in low or "deadlock" in low
