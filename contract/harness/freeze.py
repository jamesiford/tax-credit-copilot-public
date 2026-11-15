"""Freeze the sources of non-determinism from the harness, never from the product.

Prefer freezing the source over normalising its output (contract/docs/normalisation.md): the clock, every UUID,
the secrets module, `random`, and the monotonic-ish timers whose readings leak into response bodies as durations.

`install()` must run before any product module is imported, because modules bind `from datetime import datetime`
and `from uuid import uuid4` at import time.
"""
from __future__ import annotations

import datetime as _dt
import itertools
import random
import secrets
import time
import uuid

#: One instant for every `now()` the product takes. A constant rather than a ticking clock: a tick makes a response
#: depend on how many times the product happened to ask, and a background task would perturb it.
FROZEN_UTC = _dt.datetime(2026, 1, 15, 12, 0, 0, tzinfo=_dt.timezone.utc)
FROZEN_EPOCH = FROZEN_UTC.timestamp()
_REAL_DATE, _REAL_DATETIME = _dt.date, _dt.datetime

_uuid_counter = itertools.count(1)
_bytes_counter = itertools.count(1)
_installed = False
_TRACE = __import__("os").environ.get("CONTRACT_UUID_TRACE")


class FrozenDate(_dt.date):
    @classmethod
    def today(cls):  # noqa: D102
        return cls(FROZEN_UTC.year, FROZEN_UTC.month, FROZEN_UTC.day)


class FrozenDatetime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: D102
        base = FROZEN_UTC if tz is not None else FROZEN_UTC.replace(tzinfo=None)
        if tz is not None:
            base = FROZEN_UTC.astimezone(tz)
        return cls(base.year, base.month, base.day, base.hour, base.minute, base.second, base.microsecond, base.tzinfo)

    @classmethod
    def utcnow(cls):  # noqa: D102
        return cls.now()

    @classmethod
    def today(cls):  # noqa: D102
        return cls.now()


def reset_counters() -> None:
    """Start every id source from the same place; the recorder calls this before each scenario."""
    global _uuid_counter, _bytes_counter, _perf
    _uuid_counter = itertools.count(1)
    _bytes_counter = itertools.count(1)
    _perf = itertools.count(1)
    random.seed(20260115)


def _uuid4() -> uuid.UUID:
    n = next(_uuid_counter)
    if _TRACE:
        import threading
        import traceback

        frames = traceback.extract_stack(limit=6)[:-1]
        with open(_TRACE, "a", encoding="utf-8") as fh:
            fh.write(f"{n} {threading.current_thread().name} " + " < ".join(f"{f.filename.split('backend')[-1]}:{f.lineno}" for f in reversed(frames)) + "\n")
    return uuid.UUID(int=(0x4000_0000_0000_4000_8000_0000_0000_0000 | n))


def _uuid1(*_args, **_kwargs) -> uuid.UUID:
    return _uuid4()


def _token_bytes(nbytes: int | None = None) -> bytes:
    n = 32 if nbytes is None else nbytes
    value = next(_bytes_counter)
    return (value.to_bytes(8, "big") * (n // 8 + 1))[:n]


def _token_hex(nbytes: int | None = None) -> str:
    return _token_bytes(nbytes).hex()


def _token_urlsafe(nbytes: int | None = None) -> str:
    import base64

    return base64.urlsafe_b64encode(_token_bytes(nbytes)).rstrip(b"=").decode("ascii")


_perf = itertools.count(1)


def _perf_counter() -> float:
    """A deterministic timer: each reading is 1 ms after the last, so a measured duration is a function of call count."""
    return next(_perf) / 1000.0


def install() -> None:
    global _installed
    if _installed:
        return
    _dt.datetime = FrozenDatetime  # type: ignore[misc]
    _dt.date = FrozenDate  # type: ignore[misc]
    import sqlite3

    # Python 3.12 deprecated sqlite3's default date/datetime adapters and 3.14 removed them, so the product (which targets 3.12) binds
    # plain dates only where the interpreter still supplies them. Register the 3.12 behaviour for the stdlib types and the frozen
    # subclasses; this is what the product was written against. (FINDING F-2.)
    sqlite3.register_adapter(_REAL_DATE, lambda d: d.isoformat())
    sqlite3.register_adapter(_REAL_DATETIME, lambda d: d.isoformat(" "))
    sqlite3.register_adapter(FrozenDate, lambda d: d.isoformat())
    sqlite3.register_adapter(FrozenDatetime, lambda d: d.isoformat(" "))
    uuid.uuid4 = _uuid4  # type: ignore[assignment]
    uuid.uuid1 = _uuid1  # type: ignore[assignment]
    secrets.token_bytes = _token_bytes  # type: ignore[assignment]
    secrets.token_hex = _token_hex  # type: ignore[assignment]
    secrets.token_urlsafe = _token_urlsafe  # type: ignore[assignment]
    time.time = lambda: FROZEN_EPOCH  # type: ignore[assignment]
    time.time_ns = lambda: int(FROZEN_EPOCH * 1_000_000_000)  # type: ignore[assignment]
    time.perf_counter = _perf_counter  # type: ignore[assignment]
    reset_counters()
    _freeze_git()
    _freeze_zip()
    _freeze_mtimes()
    _freeze_threads()
    _installed = True


def _freeze_mtimes() -> None:
    """The rule-pack files' modification times reach `/api/rules` (`last_update_iso`, each rule's `updated`).

    They are the checkout time of whoever cloned the repository, so a recording would only hold on one machine. Each rule file is given a
    fixed time derived from its path (so the 'most recently updated' ordering is stable and not all equal). (FINDING F-10.)
    """
    import os
    import zlib

    real = os.stat
    base = int(FROZEN_EPOCH) - 30 * 86400

    def stat(path, *args, **kwargs):
        result = real(path, *args, **kwargs)
        text = os.fspath(path) if not isinstance(path, int) else ""
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        normalised = text.replace("\\", "/")
        if normalised.endswith(".json") and "/backend/rules/" in normalised:
            when = base + zlib.crc32(normalised.split("/backend/rules/", 1)[1].encode()) % (20 * 86400)
            fields = list(result)[:7] + [when, when, when]
            return os.stat_result(fields + [float(when), float(when), float(when), when * 10**9, when * 10**9, when * 10**9])
        return result

    os.stat = stat  # type: ignore[assignment]


def _freeze_threads() -> None:
    """Background recalculation after a base-year save runs on a daemon thread the response does not wait for.

    Its id and clock draws interleave with the next request's, and what the next read says (`newer_run_in_flight`) depends on how fast
    it ran. The harness runs it deterministically: deferred until the response has been sent, finished before the next request is
    accepted (`ContractControl`). The product's own semantics (a response that does not wait for the recalculation) are unchanged.
    """
    import threading

    real_start = threading.Thread.start

    def start(self):
        if self.name.startswith("rebase-recalc-"):
            _deferred.append(self)
            return None
        return real_start(self)

    threading.Thread.start = start  # type: ignore[method-assign]


_deferred: list[Any] = []


def take_deferred() -> list[Any]:
    taken = list(_deferred)
    _deferred.clear()
    return taken


def _freeze_zip() -> None:
    """`ZipFile.write(path)` stamps each member with the source file's mtime; openpyxl spools a worksheet through a temp file."""
    import zipfile

    real = zipfile.ZipInfo.from_file.__func__

    def from_file(cls, filename, arcname=None, *, strict_timestamps=True):
        info = real(cls, filename, arcname, strict_timestamps=strict_timestamps)
        info.date_time = time.localtime(FROZEN_EPOCH)[:6]
        return info

    zipfile.ZipInfo.from_file = classmethod(from_file)  # type: ignore[method-assign]


def _freeze_git() -> None:
    """`git rev-parse HEAD` is read by the run commands for `code_commit`; the worktree HEAD moves with every commit."""
    import subprocess

    real_check_output = subprocess.check_output

    def check_output(args, *a, **kw):
        if isinstance(args, (list, tuple)) and list(args[:3]) == ["git", "rev-parse", "HEAD"]:
            text = "0000000000000000000000000000000000c0ffee\n"
            return text if kw.get("text") or kw.get("universal_newlines") else text.encode()
        return real_check_output(args, *a, **kw)

    subprocess.check_output = check_output  # type: ignore[assignment]
