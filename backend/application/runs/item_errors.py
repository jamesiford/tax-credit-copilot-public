"""What a stored run item says about why it failed: a typed cause and a fixed remedy, never the raw error text. [F07.3]

The raw message of an exception can echo a request value, a host name or a row. It goes to the log (logger `tcc.runs`); the item
and the API carry the cause (`error_dependency`) and the sentence below. Split from `executor.py` by size.
"""
from __future__ import annotations

import logging

from application.errors import DependencyUnavailable

log = logging.getLogger("tcc.runs")

#: The named cause of a Gold write that did not hold (a section 9 violation such as more than one current run for a client and
#: program, or the writer failing). Shown in the batch's failures by cause.
GOLD_WRITE = "gold_write"
GOLD_WRITE_MESSAGE = (
    "The Gold write did not validate. Gold may briefly hold rows of more than one run for this client. "
    "It is retried once with no other worker on the client; if it fails again, run the client alone and check section 9 "
    "(`python backend/tools/verify_gold_reads.py`) before trusting its figures."
)
FIXED_REMEDY = {
    "validation": "The request was refused as stated (a value is out of range or unsupported). Fix the selection and start a new batch; the log holds the exact message.",
    "internal": "An unexpected error. The item was not retried; see the log, and run the client alone to reproduce it.",
    "timeout": "A call timed out or the connection dropped. Retry the failed items when the store or source is reachable.",
    "conflict": "A write conflict on the warehouse. Retry the failed items; lower RUN_WORKER_CONCURRENCY if it repeats.",
    "unavailable": "A dependency did not answer. Check it, then retry the failed items.",
}


def remedy_of(failure: DependencyUnavailable) -> str:
    """The failure's fixed remedy. Its `reason` can carry the underlying error text, so it goes to the log, not the item."""
    log.warning("run item: %s unavailable: %s", failure.dependency, failure.reason)
    return failure.remedy.strip() or FIXED_REMEDY["unavailable"]


def log_raw(cause: str, exc: BaseException) -> None:
    """Keep the raw message where an operator can read it. A programming error also keeps its trace."""
    if cause == "internal":
        log.error("run item failed on an unexpected error: %r", exc, exc_info=exc)
    else:
        log.warning("run item failed (%s): %s", cause, exc)
