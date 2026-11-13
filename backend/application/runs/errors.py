"""Typed refusals for run batches, each carrying the remedy a caller should show. [ADR-012]

`DependencyUnavailable` (application/errors.py) is reused for outages. These are the request-shaped refusals:
the request was understood and is not acceptable as stated, and nothing was written.
"""
from __future__ import annotations


class RunBatchRefused(ValueError):
    """A request that cannot become a batch as stated. `remedy` says what to change."""

    code = "refused"

    def __init__(self, message: str, remedy: str) -> None:
        super().__init__(f"{message} {remedy}".strip())
        self.message, self.remedy = message, remedy

    def as_detail(self) -> dict[str, str]:
        return {"detail": str(self), "code": self.code, "reason": self.message, "remedy": self.remedy}


class BatchTooLarge(RunBatchRefused):
    """The request selects more items than the configured limit allows."""
    code = "batch_too_large"

    def __init__(self, items: int, limit: int, *, can_override: bool) -> None:
        self.items, self.limit = items, limit
        remedy = (
            "Narrow the selection, or set override_size_limit to run everything."
            if can_override else "Narrow the selection, or raise RUN_BATCH_MAX_ITEMS."
        )
        super().__init__(f"The request selects {items} items, over the limit of {limit}.", remedy)


class ConfirmationRequired(RunBatchRefused):
    """A start above the confirmation threshold was sent without the typed item count."""
    code = "confirmation_required"

    def __init__(self, items: int, confirm_above: int) -> None:
        self.items, self.confirm_above = items, confirm_above
        super().__init__(
            f"This starts {items} items, above {confirm_above}, so it needs confirmation.",
            f"Preview it, then send confirm_items={items} to start it.",
        )


class EmptyScope(RunBatchRefused):
    """The selection matched no clients, so there is nothing to queue."""
    code = "empty_scope"

    def __init__(self, why: str = "The selection matches no clients.") -> None:
        super().__init__(why, "Check the client ids or the filter.")


class UnknownClients(RunBatchRefused):
    """Explicit client ids that are not in the client book."""
    code = "unknown_clients"

    def __init__(self, ids: tuple[int, ...]) -> None:
        self.ids = ids
        shown = ", ".join(str(i) for i in ids[:10]) + (" and more" if len(ids) > 10 else "")
        super().__init__(f"These clients are not in the client book: {shown}.", "Remove them or check the ids.")


class UnknownBatch(LookupError):
    """No batch has this id."""

    def __init__(self, batch_id: str) -> None:
        super().__init__(f"Unknown run batch {batch_id}.")
        self.batch_id = batch_id
