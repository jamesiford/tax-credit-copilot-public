"""The event a writer check raises when it could not answer, and so denied. [RM-03]

"Is this person a writer?" has more than one source (the allow-list table, an
Entra group asked of Graph) and any of them can fail. A source that cannot answer
never grants: the answer is "no". But a denial that looks exactly like a person
who is not a writer would hide a broken source behind ordinary refusals, so each
one is logged at ERROR on `tcc.writer_check`, and counted, as `writer_check_failed`
with the source's name and the type of the error. No oid, no message.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter

LOGGER_NAME = "tcc.writer_check"
EVENT = "writer_check_failed"

_alert = logging.getLogger(LOGGER_NAME)
_counts: Counter[str] = Counter()
_lock = threading.Lock()


def writer_check_failed(source: str, error: BaseException | str) -> None:
    """Record that `source` could not answer and the caller was denied."""
    error_type = error if isinstance(error, str) else type(error).__name__
    with _lock:
        _counts[source] += 1
    _alert.error(
        "%s source=%s error_type=%s decision=deny", EVENT, source, error_type,
        extra={"event": EVENT, "writer_source": source, "error_type": error_type, "decision": "deny"},
    )


def denial_counts() -> dict[str, int]:
    """Denials caused by a failing source since the process started, per source."""
    with _lock:
        return dict(_counts)


def reset_denial_counts() -> None:
    """For tests."""
    with _lock:
        _counts.clear()
