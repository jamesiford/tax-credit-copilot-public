"""The alert an audit-write failure raises. [RM-03]

An audit trail that fails quietly is the worst failure it can have: the platform
goes on acting and nothing records that it did. Where a failed write must not
stop the answer (a closing event, a narration's agent row), it is still never
silent. Every such failure lands here, once, and does two things:

- logs `audit_write_failed` at ERROR on the dedicated logger `tcc.audit_alert`,
  which a log alert keys on (the message starts with the event name and carries
  `source=`, `operation=`, `error_type=` and `fatal=`), and
- counts it per source in a process-wide counter (`failure_counts`).

It never carries payload: no argument, no figure, no exception message (a
database error can echo the row that failed). The type of the error says enough
to route it; the stack trace, where a caller wants one, goes to that caller's own
logger.

`fatal` says whether the caller refused the work because of it (a read whose
opening event cannot be written is not made) or carried on (a closing event).
"""
from __future__ import annotations

import logging
import threading
from collections import Counter

LOGGER_NAME = "tcc.audit_alert"
EVENT = "audit_write_failed"
#: The three trails a write can fail on: the channel audit table, the narrator's
#: agent-action table, and the narration report that feeds both.
SOURCES = ("channel_audit", "agent_audit", "narration")

_alert = logging.getLogger(LOGGER_NAME)
_counts: Counter[str] = Counter()
_lock = threading.Lock()


def audit_write_failed(source: str, operation: str, error: BaseException | str, *, fatal: bool) -> None:
    """Raise the alert for one failed audit write. Raises only for an unknown source (a programming error)."""
    if source not in SOURCES:
        raise ValueError(f"unknown audit source {source!r}; expected one of {', '.join(SOURCES)}")
    error_type = error if isinstance(error, str) else type(error).__name__
    with _lock:
        _counts[source] += 1
    _alert.error(
        "%s source=%s operation=%s error_type=%s fatal=%s", EVENT, source, operation, error_type, fatal,
        extra={"event": EVENT, "audit_source": source, "audit_operation": operation,
               "error_type": error_type, "fatal": fatal},
    )


def failure_counts() -> dict[str, int]:
    """Failures since the process started, per source (zero for a source with none)."""
    with _lock:
        return {source: _counts[source] for source in SOURCES}


def reset_failure_counts() -> None:
    """For tests: a counter shared by the process would make one test's failure another's."""
    with _lock:
        _counts.clear()
