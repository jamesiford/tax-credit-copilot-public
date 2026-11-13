"""Run batches: the pure model of "recalculate these clients" as tracked work. [ADR-012]

A batch is a request (what to run, for whom); an item is one client, optionally one tax year.
Everything here is data and rules with no I/O, so the state machines, the retry policy and the
"unchanged" decision are unit tests rather than integration tests.

Two decisions shape the model and are worth reading before changing it:

* **An item with no `tax_year` means "the client's latest runnable year", resolved when the item
  starts.** A run replays and writes every authored year of the client's payroll whatever year it is
  asked for, so an all-years request is one item per client (`refresh_once`), not one per year.
  Resolving the year at start keeps the enqueue and the preview free of payroll reads.
* **"Unchanged" is a conclusion that needs evidence, and absence of evidence means run.** See
  `unchanged_decision`: any missing value on either side is "cannot tell", never "unchanged".
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class BatchKind(str, Enum):
    """What a batch does for each client."""
    ASSESS = "assess"
    CALCULATE = "calculate"
    ASSESS_AND_CALCULATE = "assess_and_calculate"


class ScopeKind(str, Enum):
    """How the clients of a batch were chosen."""
    ONE = "one"
    LIST = "list"
    FILTER = "filter"
    ALL = "all"


class BatchStatus(str, Enum):
    """Where a batch is, derived from its items."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ItemStatus(str, Enum):
    """Where one item is in its life."""
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    SKIPPED_NO_PAYROLL = "skipped_no_payroll"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Items that will not change again unless somebody retries them.
TERMINAL_ITEMS = frozenset({
    ItemStatus.SUCCEEDED, ItemStatus.SKIPPED_UNCHANGED, ItemStatus.SKIPPED_NO_PAYROLL,
    ItemStatus.FAILED, ItemStatus.CANCELLED,
})
SKIPPED_ITEMS = frozenset({ItemStatus.SKIPPED_UNCHANGED, ItemStatus.SKIPPED_NO_PAYROLL})
ACTIVE_ITEMS = frozenset({ItemStatus.LEASED, ItemStatus.RUNNING})

#: Legal item moves. `leased -> queued` is a worker giving a claim back (lost the per-client lock, or
#: the lease expired); `failed -> queued` is an operator's retry. Nothing leaves `succeeded`.
_ITEM_MOVES: dict[ItemStatus, frozenset[ItemStatus]] = {
    ItemStatus.QUEUED: frozenset({ItemStatus.LEASED, ItemStatus.CANCELLED}),
    ItemStatus.LEASED: frozenset({ItemStatus.RUNNING, ItemStatus.QUEUED, ItemStatus.CANCELLED,
                                  ItemStatus.SKIPPED_UNCHANGED, ItemStatus.SKIPPED_NO_PAYROLL}),
    ItemStatus.RUNNING: frozenset({ItemStatus.SUCCEEDED, ItemStatus.FAILED, ItemStatus.QUEUED,
                                   ItemStatus.SKIPPED_UNCHANGED, ItemStatus.SKIPPED_NO_PAYROLL}),
    ItemStatus.FAILED: frozenset({ItemStatus.QUEUED}),
}


class IllegalTransition(ValueError):
    """An item or batch was asked to move somewhere the state machine does not allow."""


def check_item_move(current: ItemStatus, target: ItemStatus) -> None:
    if target not in _ITEM_MOVES.get(current, frozenset()):
        raise IllegalTransition(f"an item cannot move from {current.value} to {target.value}")


@dataclass(frozen=True)
class RunBatch:
    """One request to run a set of clients. Counts are derived from the items by `batch_status`."""

    batch_id: str
    kind: BatchKind
    scope_kind: ScopeKind
    scope_spec: dict[str, Any]
    requested_by: str
    requested_at: datetime
    program_code: str | None = None
    tax_years: tuple[int, ...] = ()
    force: bool = False
    include_code_commit: bool = False
    refresh_once: bool = True
    status: BatchStatus = BatchStatus.QUEUED
    idempotency_key: str | None = None
    dry_run_summary: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RunBatchItem:
    """One client (and maybe one year) in a batch."""

    item_id: str
    batch_id: str
    client_id: int
    seq: int = 0
    program_code: str | None = None
    tax_year: int | None = None
    status: ItemStatus = ItemStatus.QUEUED
    attempts: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    not_before: datetime | None = None
    run_id: str | None = None
    skip_reason: str | None = None
    error_dependency: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def moved(self, status: ItemStatus, **changes: Any) -> "RunBatchItem":
        check_item_move(self.status, status)
        return replace(self, status=status, **changes)


@dataclass(frozen=True)
class ItemResult:
    """How an item ended, as the queue records it."""

    status: ItemStatus
    run_id: str | None = None
    skip_reason: str | None = None
    error_dependency: str | None = None
    error_message: str | None = None
    tax_year: int | None = None


def _finished_status(counts: dict[str, int], total: int) -> BatchStatus:
    """The status of a batch with no open items left."""
    failed, cancelled = counts.get(ItemStatus.FAILED.value, 0), counts.get(ItemStatus.CANCELLED.value, 0)
    if failed == 0 and cancelled == 0:
        return BatchStatus.SUCCEEDED
    if total - failed - cancelled == 0:
        return BatchStatus.CANCELLED if failed == 0 else BatchStatus.FAILED
    return BatchStatus.PARTIAL


def batch_status(counts: dict[str, int], *, cancel_requested: bool = False) -> BatchStatus:
    """The batch's status from its item counts (keyed by `ItemStatus` value).

    `partial` means some items succeeded or were skipped and some failed or were cancelled: the batch
    is over but did not do everything it was asked to. All-skipped is `succeeded`, because a skip is a
    deliberate answer ("nothing to do"), not a failure.
    """
    total = sum(counts.values())
    if total == 0:
        return BatchStatus.CANCELLED if cancel_requested else BatchStatus.SUCCEEDED
    open_items = sum(counts.get(s.value, 0) for s in ItemStatus if s not in TERMINAL_ITEMS)
    if open_items:
        started = total - counts.get(ItemStatus.QUEUED.value, 0)
        return BatchStatus.RUNNING if started else BatchStatus.QUEUED
    return _finished_status(counts, total)


# ---------------------------------------------------------------- the unchanged rule


@dataclass(frozen=True)
class Fingerprint:
    """Everything that decides a client-year's answer, as the manifest records it. None = unknown."""

    calculation_id: str | None = None
    step1_assumption_sha256: str | None = None
    onezero_assumption_sha256: str | None = None
    rule_pack_version: str | None = None
    code_commit: str | None = None
    tax_year: int | None = None


def unchanged_decision(
    last: Fingerprint | None, current: Fingerprint, *, include_code_commit: bool = False,
) -> tuple[bool, str]:
    """`(unchanged, reason)`. True only when every compared value is known on both sides and equal.

    `source_snapshot_id` is deliberately not compared: it is never populated, so it cannot say anything.
    `calculation_id` already digests the year's payroll rows, the floors and the assumption ids.
    """
    if last is None:
        return False, "no earlier successful run for this client and programme"
    if last.tax_year != current.tax_year:
        return False, (
            f"the latest run was for TY{last.tax_year}, not TY{current.tax_year}: cannot tell, so run"
        )
    pairs = [
        ("calculation fingerprint", last.calculation_id, current.calculation_id),
        ("step 1 assumption hash", last.step1_assumption_sha256, current.step1_assumption_sha256),
        ("one/zero assumption hash", last.onezero_assumption_sha256, current.onezero_assumption_sha256),
        ("rule pack version", last.rule_pack_version, current.rule_pack_version),
    ]
    if include_code_commit:
        pairs.append(("code commit", last.code_commit, current.code_commit))
    for name, before, now in pairs:
        if not before or not now:
            return False, f"{name} is not recorded on one side: cannot tell, so run"
        if before != now:
            return False, f"{name} changed"
    return True, "calculation fingerprint, assumption hashes and rule pack are identical to the last run"


# ---------------------------------------------------------------- retry policy
#
# Which failures are transient is decided where the exception is understood (`application/runs/executor.py`),
# because it depends on typed application errors; the domain owns only how long to wait.

def backoff_seconds(
    attempt: int, *, base: float = 5.0, cap: float = 120.0, jitter: Callable[[], float] = random.random,
) -> float:
    """Capped exponential backoff with up to 25% jitter, so a batch of failures does not retry in step."""
    raw = min(cap, base * (2 ** max(0, attempt - 1)))
    return raw * (1 + 0.25 * jitter())
