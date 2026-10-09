"""`RunManifestRepository` over the Microsoft Fabric Warehouse. [ADR-002]

The production adapter for calculation provenance. Three things about it are
non-obvious and cost real time if rediscovered.

**The AAD token is a connection ATTRIBUTE, not a connection-string field.** The
driver reads it from `SQL_COPT_SS_ACCESS_TOKEN` (1256) as a length-prefixed
UTF-16-LE blob. There is no `Authentication=` string form that accepts an
already-acquired token, so `attrs_before` is the only route. The scope is
`https://database.windows.net/.default` — the SQL data plane — not the Fabric or
storage scope used by the OneLake reader in `data/source/from_fabric.py`. Those
are different audiences and a token for one is rejected by the other.

**The SQL stays portable T-SQL.** Fabric Warehouse implements a subset of SQL
Server T-SQL and this schema is deliberately deployable on both, so nothing here
uses Fabric-only syntax. Plain parameterised `INSERT` and `SELECT`, no `MERGE`,
no `IDENTITY`, no table hints. Keeping that true is what makes the target
swappable rather than a one-way door.

**The warehouse does not enforce keys.** Fabric accepts `PRIMARY KEY ... NOT
ENFORCED` and will happily store the same `run_id` twice. `record` therefore
checks for an existing row first. That is a narrow guard, not a transaction: two
concurrent writers can still both pass the check. Runs are triggered one client
at a time by an operator, so the race is not reachable today — when it becomes
reachable the fix is a uniqueness sweep after the write, not a lock the
warehouse cannot give us.

Authentication is `DefaultAzureCredential`, so the same code runs under a
developer's `az login` and under the container's managed identity, with no
branch and no secret in configuration.
"""
from __future__ import annotations

import os
import struct
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from config import GOLD_SCHEMA, OPS_SCHEMA  # noqa: F401 - re-exported for the adapters
from domain.warehouse import RunManifest
from infrastructure.persistence.tenant_sql import TenantScopedQuery, tenant_exempt

#: Statements with no tenant: a liveness probe, and lookups by a globally unique run_id.
_KEEPALIVE = tenant_exempt("connection keepalive probe touches no table")
_RUN_BY_ID = tenant_exempt("run_manifest lookup by globally unique run_id")

_TOKEN_SCOPE = "https://database.windows.net/.default"

#: SQL_COPT_SS_ACCESS_TOKEN. Defined by msodbcsql, not exported by pyodbc.
_SQL_COPT_SS_ACCESS_TOKEN = 1256

_DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
_DEFAULT_CONNECT_TIMEOUT = 90

#: Refresh this far before expiry, so a long request cannot straddle it.
_TOKEN_REFRESH_MARGIN_S = 300

#: SQLSTATEs that mean the connection attempt failed in transport, not that the
#: request was wrong. `08001` covers Fabric's prelogin refusal under load.
_TRANSIENT_CONNECT_STATES = frozenset({"08001", "08S01", "08003", "HYT00", "01000"})
#: Long enough for a capacity to finish whatever refused the first attempt,
#: short enough that a page still feels like it is loading.
_RECONNECT_PAUSE_S = 1.0

#: How long a run may sit `running` before it is presumed dead. The longest real
#: run observed is a full client replay at ~150s, so an hour leaves two orders of
#: magnitude of headroom. Reaping a run that is somehow still alive is
#: self-correcting: `_mark_complete` sets it back to `success` when it lands.
#: The reader and the reaper must agree on this, so it is defined once here
#: rather than in either of them.
STRANDED_RUN_MINUTES = int(os.getenv("TCC_STRANDED_RUN_MINUTES", "60"))


def _close_quietly(connection: Any) -> None:
    try:
        connection.close()
    except Exception:  # noqa: BLE001 - closing a dead link is not an error
        pass


def _end_transaction(connection: Any) -> bool:
    """Close the implicit read transaction. False means the link is unusable.

    pyodbc connects with autocommit OFF, so the first SELECT opens a transaction
    that nothing on a read path ever ends. Fabric Warehouse reads under snapshot
    isolation, so that transaction pins the snapshot it started with -- and once
    connections are pooled and kept alive, the snapshot is pinned for the life of
    the process. A completed run then keeps reading as `running` and a superseded
    one keeps reading as live, on a warehouse that has long since moved on.

    Rolling back is safe because writes do not come from the pool: `GoldWriter`
    holds its own connection and commits explicitly.
    """
    try:
        connection.rollback()
        return True
    except Exception:  # noqa: BLE001 - a link that cannot roll back is not reusable
        return False


#: A connection is expensive to CREATE and cheap to reuse. Measured against this
#: warehouse: six threads opening at once cost 6.1-6.8s EACH, while borrowing an
#: already-open link costs 122ms. A page fires three or four requests at once,
#: so opening per request means a connection storm on every navigation — which
#: is a page that loads in half a second for one person and nine seconds for the
#: next, with no pattern they can see.
#:
#: The pool is PROCESS-wide, not thread-local. Keyed by nothing: one warehouse
#: per process. Thread-local parking looks equivalent and is not — FastAPI's
#: threadpool has forty threads, so every one of them builds its own link and
#: the storm happens anyway, against a server that has a connection limit.
_POOL_LOCK = threading.Lock()
_POOL: list[tuple[Any, float]] = []

#: Small enough to stay well inside Fabric's limit, large enough for the three
#: or four concurrent reads one page makes.
_POOL_MAX_IDLE = 4

#: The ODBC pool's idle timeout is 60s by default, and measurement matches it:
#: a connection is still hot after 30s idle (120ms) and dead after 90s (3,216ms
#: — a full handshake). Four minutes therefore handed out corpses, which is why
#: the read path's reconnect retry was firing on ordinary page loads. Sitting
#: under the real timeout makes that retry a safety net again rather than a
#: routine code path. `KEEPALIVE_INTERVAL_S` should keep links well under this.
_POOL_MAX_AGE_S = 45

#: The credential and its token are PROCESS-wide, not per instance. Several
#: components build their own `FabricWarehouseConnection` — the gold reader, the
#: manifest repository, the scope router — and a per-instance cache meant each
#: of them paid the 1.1s `az account get-access-token` again.
_TOKEN_LOCK = threading.Lock()
_SHARED_CREDENTIAL: Any = None
_SHARED_TOKEN: tuple[bytes, int] | None = None

#: Column order is the DDL's. The insert and the row mapper both read it, so the
#: two cannot drift into disagreeing about position.
_MANIFEST_COLUMNS = (
    "run_id",
    "client_id",
    "entity_id",
    "program_code",
    "tax_year",
    "fiscal_year_begin",
    "fiscal_year_end",
    "source_snapshot_id",
    "step1_assumption_set_id",
    "step1_assumption_sha256",
    "onezero_assumption_set_id",
    "onezero_assumption_sha256",
    "rule_pack_version",
    "code_commit",
    "calculation_id",
    "run_started_at",
    "run_completed_at",
    "run_status",
    "superseded_by_run_id",
    "triggered_by",
)


class WarehouseNotConfigured(RuntimeError):
    """Raised when the adapter has no server or database to talk to.

    Deliberately not a silent fallback. A warehouse adapter that quietly wrote
    somewhere else would look like it worked and lose every provenance record.
    """


class FabricWarehouseConnection:
    """Everything needed to open one authenticated ODBC connection.

    Separate from the repository because every table in `tcc_gold` and
    `tcc_ops` will need exactly this and none of them should re-derive the
    token dance.
    """

    def __init__(
        self,
        *,
        server: str | None = None,
        database: str | None = None,
        driver: str | None = None,
        connect_timeout: int | None = None,
        credential: Any = None,
    ) -> None:
        self.server = (server or os.getenv("WAREHOUSE_SERVER") or "").strip()
        self.database = (database or os.getenv("WAREHOUSE_DATABASE") or "").strip()
        self.driver = (driver or os.getenv("WAREHOUSE_ODBC_DRIVER") or _DEFAULT_DRIVER).strip()
        self.connect_timeout = int(
            connect_timeout
            if connect_timeout is not None
            else os.getenv("WAREHOUSE_CONNECT_TIMEOUT", _DEFAULT_CONNECT_TIMEOUT)
        )
        self._credential = credential
        #: An INJECTED credential is never shared — a test's fake must not leak
        #: into another test, nor into the process-wide cache.
        self._token: tuple[bytes, int] | None = None
        self._token_lock = threading.Lock()
        #: The connection a `scope()` is sharing, per THREAD — endpoints run on
        #: FastAPI's threadpool, so a module-level connection would be handed to
        #: two requests at once.
        self._scoped = threading.local()

    def require_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("WAREHOUSE_SERVER", self.server),
                ("WAREHOUSE_DATABASE", self.database),
            )
            if not value
        ]
        if missing:
            raise WarehouseNotConfigured(
                f"{', '.join(missing)} not set. The warehouse adapter cannot guess "
                f"where to write run provenance, and defaulting to a local file "
                f"would persist audit records somewhere nobody is looking."
            )

    def connection_string(self) -> str:
        """A connection string with no credential in it. The token travels separately."""
        self.require_configuration()
        return (
            f"Driver={{{self.driver}}};"
            f"Server={self.server},1433;"
            f"Database={self.database};"
            f"Encrypt=Yes;TrustServerCertificate=No;"
            f"Connection Timeout={self.connect_timeout};"
        )

    def _get_credential(self) -> Any:
        """The credential, built once per process.

        Imported lazily so importing this module does not require
        `azure.identity` — the memory adapter must be selectable without it.
        """
        global _SHARED_CREDENTIAL
        if self._credential is not None:
            return self._credential
        if _SHARED_CREDENTIAL is None:
            from azure.identity import DefaultAzureCredential

            _SHARED_CREDENTIAL = DefaultAzureCredential()
        return _SHARED_CREDENTIAL

    def _access_token_attribute(self) -> bytes:
        """The packed bearer token, cached until it is near expiry.

        `DefaultAzureCredential.get_token` does NOT cache: four calls on one
        instance measured 1240/1058/1102/1117 ms, because on a developer
        machine the chain resolves to `AzureCliCredential`, which spawns
        `az account get-access-token` every time. Six queries a page meant six
        subprocesses — about 6.6 seconds before a single row was read.

        A credential that reports no expiry is refetched every time, which is
        the old behaviour: better slow than holding a token we cannot age out.
        """
        global _SHARED_TOKEN
        injected = self._credential is not None
        lock = self._token_lock if injected else _TOKEN_LOCK
        now = time.time()

        cached = self._token if injected else _SHARED_TOKEN
        if cached is not None and cached[1] - _TOKEN_REFRESH_MARGIN_S > now:
            return cached[0]

        with lock:
            # Re-check: another thread may have refreshed while we waited.
            cached = self._token if injected else _SHARED_TOKEN
            if cached is not None and cached[1] - _TOKEN_REFRESH_MARGIN_S > now:
                return cached[0]
            token = self._get_credential().get_token(_TOKEN_SCOPE)
            raw = token.token.encode("utf-16-le")
            packed = struct.pack(f"<I{len(raw)}s", len(raw), raw)
            entry = (packed, int(getattr(token, "expires_on", 0) or 0))
            if injected:
                self._token = entry
            else:
                _SHARED_TOKEN = entry
            return packed

    def open(self) -> Any:
        """A raw connection the caller owns and must close.

        `connect()` is the context-managed form and is right for a short read.
        A bulk write needs to survive the server closing the link mid-run, which
        means reopening — so it needs the connection itself, not a scope.

        Retried once on a transport failure. Fabric refuses connections under
        load — `08001` prelogin failure, `HYT00` login timeout — and a blip on
        the very first packet is not a reason to 500 a page that would have
        rendered a moment later. A second failure is reported: retrying past
        that would turn a real outage into a hang.
        """
        import pyodbc

        try:
            return self._open_once()
        except pyodbc.Error as exc:
            state = exc.args[0] if exc.args else ""
            if state not in _TRANSIENT_CONNECT_STATES:
                raise
            time.sleep(_RECONNECT_PAUSE_S)
            return self._open_once()

    def _open_once(self) -> Any:
        import pyodbc

        return pyodbc.connect(
            self.connection_string(),
            attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: self._access_token_attribute()},
        )

    def acquire(self) -> Any:
        """A connection from the pool, or a new one when the pool is empty."""
        now = time.time()
        while True:
            with _POOL_LOCK:
                if not _POOL:
                    break
                connection, opened_at = _POOL.pop()
            if now - opened_at <= _POOL_MAX_AGE_S:
                return connection
            _close_quietly(connection)
        return self.open()

    def release(self, connection: Any, *, reusable: bool = True) -> None:
        """Return a connection to the pool, or close it if it is suspect."""
        if not reusable:
            _close_quietly(connection)
            return
        if not _end_transaction(connection):
            _close_quietly(connection)
            return
        with _POOL_LOCK:
            if len(_POOL) < _POOL_MAX_IDLE:
                _POOL.append((connection, time.time()))
                return
        _close_quietly(connection)

    def prewarm(self, count: int = _POOL_MAX_IDLE) -> int:
        """Fill the pool before the first request, one connection at a time.

        Opening serially is the point: it is the CONCURRENT opens that cost
        6-7s each. Paying for them one at a time at startup, where nobody is
        waiting, is what keeps the first page load off that cliff.
        """
        opened = 0
        for _ in range(count):
            try:
                self.release(self.open())
                opened += 1
            except Exception:  # noqa: BLE001 - a cold capacity must not block startup
                break
        return opened

    def keepalive(self) -> int:
        """Touch every pooled connection so the ODBC pool never times it out.

        Nothing else holds the link open. `prewarm` runs once at startup, the
        connection dies sixty seconds later, and the next page pays a 3.2s
        handshake — which is the whole of the "sometimes 600ms, sometimes five
        seconds" symptom. Clicking through pages keeps it alive by accident;
        pausing to talk kills it.

        Returns the number of connections still alive. A connection that fails
        the touch is dropped here rather than handed to a request.
        """
        with _POOL_LOCK:
            borrowed, _POOL[:] = list(_POOL), []

        alive: list[tuple[Any, float]] = []
        for connection, opened_at in borrowed:
            try:
                cursor = connection.cursor()
                _KEEPALIVE.execute(cursor, "SELECT 1")
                cursor.fetchall()
                cursor.close()
            except Exception:  # noqa: BLE001 - a dead link is the thing we are looking for
                _close_quietly(connection)
                continue
            # The touch is itself a read, so it opens a transaction of its own.
            # Leaving it open would pin a snapshot every 30 seconds forever.
            if not _end_transaction(connection):
                _close_quietly(connection)
                continue
            # The age is what `acquire` judges reuse on, and a touched
            # connection is as good as a new one, so the clock restarts.
            alive.append((connection, time.time()))

        with _POOL_LOCK:
            _POOL[:] = (alive + _POOL)[:_POOL_MAX_IDLE]
        return len(alive)

    @contextmanager
    def scope(self) -> Iterator[Any]:
        """Run several reads on ONE pooled connection.

        Every reader method opens its own, which is right for a single query and
        wrong for a page: one drill page opened six. Fabric eventually answered
        with "resource limitation (memory or maximum allowed connections) on the
        server" and dropped the link, so this is a correctness problem before it
        is a speed one.
        """
        if getattr(self._scoped, "connection", None) is not None:
            yield self._scoped.connection  # nested scope; the outer one owns it
            return

        connection = self.acquire()
        self._scoped.connection = connection
        failed = False
        try:
            yield connection
        except Exception:
            failed = True
            raise
        finally:
            live = getattr(self._scoped, "connection", None)
            self._scoped.connection = None
            if live is not None:
                self.release(live, reusable=not failed)

    def invalidate(self) -> None:
        """Discard this thread's connection after a link failure.

        The next statement takes a fresh one from the pool. Called by the read
        path when a pooled connection turns out to have been closed by the
        server.
        """
        scoped = getattr(self._scoped, "connection", None)
        if scoped is not None:
            _close_quietly(scoped)
            self._scoped.connection = None

    @contextmanager
    def connect(self) -> Iterator[Any]:
        """One pooled connection for a single read.

        Inside a `scope()` this hands back the shared connection and does NOT
        release it — the scope owns its lifetime. That is what lets all fourteen
        reader methods stay as they are.

        Outside a scope it BORROWS from the pool rather than opening its own.
        Opening here is what made `/api/v2/clients/{id}/runs/latest` build a
        fresh connection on every request, warm or cold, while `/units` built
        none: the manifest repository never enters a scope, so it was paying a
        full handshake to read one row.
        """
        scoped = getattr(self._scoped, "connection", None)
        if scoped is not None:
            yield scoped
            return

        connection = self.acquire()
        failed = False
        try:
            yield connection
        except Exception:
            failed = True
            raise
        finally:
            self.release(connection, reusable=not failed)


def _row_to_manifest(row: Any) -> RunManifest:
    values = dict(zip(_MANIFEST_COLUMNS, row))
    return RunManifest(**values)


class FabricRunManifestRepository:
    """`RunManifestRepository` backed by `tcc_ops.run_manifest`.

    The table is expected to exist — `docs/data/schema/tcc-schema.fabric.sql`
    declares it, so creating it here would put schema in two places that could
    disagree.
    """

    #: The counterpart flag on the in-memory adapter is False.
    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    @property
    def connection(self) -> FabricWarehouseConnection:
        return self._connection

    def record(self, manifest: RunManifest) -> RunManifest:
        if self.get(manifest.run_id) is not None:
            raise ValueError(
                f"run_id={manifest.run_id!r} is already recorded. The warehouse "
                f"does not enforce the primary key, so a second insert would "
                f"silently duplicate the run rather than failing."
            )

        values = [getattr(manifest, column) for column in _MANIFEST_COLUMNS]

        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(manifest.client_id).insert(
                    cursor, f"{OPS_SCHEMA}.run_manifest", _MANIFEST_COLUMNS, [values]
                )
                connection.commit()
            finally:
                cursor.close()
        return manifest

    def get(self, run_id: str) -> RunManifest | None:
        statement = (
            f"SELECT {', '.join(_MANIFEST_COLUMNS)} "
            f"FROM {OPS_SCHEMA}.run_manifest WHERE run_id = ?"
        )
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                _RUN_BY_ID.execute(cursor, statement, [run_id])
                row = cursor.fetchone()
            finally:
                # `fetchone` leaves the statement ACTIVE; closing releases it
                # before the link goes back to the pool.
                cursor.close()
        return _row_to_manifest(row) if row is not None else None

    def count(self) -> int:
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                _RUN_BY_ID.execute(cursor, f"SELECT COUNT(*) FROM {OPS_SCHEMA}.run_manifest")
                return int(cursor.fetchone()[0])
            finally:
                cursor.close()

    def latest(self, client_id: int, *, program_code: str | None = None) -> RunManifest | None:
        statement = (
            f"SELECT TOP 1 {', '.join(_MANIFEST_COLUMNS)} "
            f"FROM {OPS_SCHEMA}.run_manifest "
            "WHERE {tenant} AND run_status = 'success' "
            "AND superseded_by_run_id IS NULL"
        )
        values: list[Any] = []
        if program_code:
            statement += " AND program_code = ?"
            values.append(program_code)
        statement += " ORDER BY run_started_at DESC"

        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(cursor, statement, values)
                row = cursor.fetchone()
            finally:
                cursor.close()
        return _row_to_manifest(row) if row is not None else None


_OVERRIDE_COLUMNS = (
    "override_id", "run_id", "client_id", "scope", "target_key", "field_changed",
    "value_before", "value_after", "reason_code", "justification_text",
    "created_by", "created_at", "approved_by", "approved_at",
)


class FabricManualOverrideRepository:
    """`ManualOverrideRepository` backed by `tcc_ops.manual_override`.

    The table exists (DDL 4.2). Append-only by construction: there is no update
    or delete here, because a human adjustment to a filed figure has to stay
    visible after it is reversed.
    """

    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def record(self, override: Any) -> Any:
        values = [getattr(override, column) for column in _OVERRIDE_COLUMNS]
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(override.client_id).insert(
                    cursor, f"{OPS_SCHEMA}.manual_override", _OVERRIDE_COLUMNS, [values]
                )
                connection.commit()
            finally:
                cursor.close()
        return override

    def _rows(self, client_id: int) -> list[Any]:
        from domain.warehouse import ManualOverride

        statement = (
            f"SELECT {', '.join(_OVERRIDE_COLUMNS)} FROM {OPS_SCHEMA}.manual_override "
            "WHERE {tenant} ORDER BY created_at, override_id"
        )
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(cursor, statement)
                rows = cursor.fetchall()
            finally:
                cursor.close()
        return [ManualOverride(**dict(zip(_OVERRIDE_COLUMNS, row))) for row in rows]

    def base_years(self, client_id: int, program_code: str) -> dict[str, int]:
        from infrastructure.persistence.memory_overrides import base_years_from

        return base_years_from(self._rows(client_id), client_id, program_code)

    def history(self, client_id: int) -> list[Any]:
        return self._rows(client_id)
