"""The Gold writer: batched inserts, supersession, and the validation sweep.

Sits beside `fabric_warehouse.py` and reuses its connection. Three things here
are load-bearing.

**Batching is bounded by the ODBC parameter ceiling, not by taste.** A
statement may carry 2100 parameters, so a 19-column table takes 110 rows per
`INSERT`, not 1000. Exceeding it fails with `COUNT field incorrect or syntax
error`, which reads like malformed SQL and is not. Measured on this F2 capacity:
`fast_executemany` managed 5.5 rows/s, and parameterised multi-row batching 133
rows/s — a 24x difference that decides whether a run takes minutes or hours.

**The values stay parameterised.** Inlining them as SQL literals measured ~4x
faster again, and this table holds job titles and pay codes read from a customer
lakehouse. A 4x speedup is not worth building a string-concatenation injection
path through untrusted payroll [OWASP A03].

**Supersession is by run, not by row.** A rerun marks the prior rows
`is_current = 0` and inserts new ones; nothing is ever updated in place, because
a superseded figure may already sit on a filed return. Only `unit_year_master`
and `unit_credit_installment` carry `is_current` — the employee-grain tables
carry `run_id` alone and take their currency from the manifest, which is the
schema's design and not an omission here.

Fabric enforces no keys, so `validate` runs section 9 of the DDL at the end of
every write. It is not a manual step someone remembers.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Sequence

from infrastructure.persistence.fabric_warehouse import (
    GOLD_SCHEMA,
    OPS_SCHEMA,
    STRANDED_RUN_MINUTES,
    FabricWarehouseConnection,
)
from infrastructure.persistence.tenant_sql import TenantScopedQuery, tenant_exempt

logger = logging.getLogger(__name__)

#: The two statements that legitimately span clients. Logged on every use.
_REAPER = tenant_exempt("stranded-run reaper sweeps every client's manifests")
_VALIDATION = tenant_exempt("DDL section 9 validation checks invariants across all clients")

#: One run writes at a time in this process. See `GoldWriter.write_run`.
_WRITE_LOCK = threading.Lock()

#: SQL Server / Fabric accept at most 2100 parameters in one statement.
_MAX_PARAMETERS = 2100

#: Tables carrying `is_current`. The rest take currency from the manifest.
_VERSIONED_TABLES = ("unit_year_master", "unit_credit_installment")

_WRITE_ATTEMPTS = 5
_RETRY_BACKOFF_SECONDS = 2

#: SQLSTATEs that mean "the link went away", not "the data was wrong".
_TRANSIENT_SQLSTATES = ("08S01", "08001", "08003", "08006", "HYT00", "HY000")


def _is_transient(exc: Exception) -> bool:
    state = (exc.args[0] if exc.args else "") or ""
    return str(state) in _TRANSIENT_SQLSTATES


def _batch_size(column_count: int) -> int:
    return max(1, min(500, (_MAX_PARAMETERS - 10) // max(1, column_count)))


class GoldWriteFailed(RuntimeError):
    """A write or its validation did not hold. The run is not usable."""


class GoldWriter:
    """Writes one run's rows to `tcc_gold` and `tcc_ops`."""

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()
        self._live: Any = None
        #: The client whose run is being written. Every statement in a write is
        #: scoped to it through `tenant_sql`.
        self._client_id: int | None = None

    def _scoped(self) -> TenantScopedQuery:
        if self._client_id is None:
            raise GoldWriteFailed("no client in scope; a Gold write is always one client's run")
        return TenantScopedQuery(self._client_id)

    @property
    def connection(self) -> FabricWarehouseConnection:
        return self._connection

    # ------------------------------------------------- connection management

    def _live_connection(self) -> Any:
        if self._live is None:
            self._live = self._connection.open()
        return self._live

    def _drop_connection(self) -> None:
        if self._live is not None:
            try:
                self._live.close()
            except Exception:  # the link is already gone; closing is best effort
                pass
            self._live = None

    def _execute(self, statement: Callable[[Any], Any]) -> None:
        """Run one statement, reopening the connection if the link has dropped.

        `statement(cursor)` issues the SQL through `tenant_sql`, so this method
        never builds or executes a statement itself.

        A bulk write holds the link for minutes and Fabric will close it: the
        symptom is `TCP Provider: An existing connection was forcibly closed`
        (10054) part way through. Retrying on the SAME connection cannot work,
        so each attempt reconnects. Backoff is there because the closures cluster
        — an immediate retry usually meets the same condition.
        """
        import pyodbc

        last: Exception | None = None
        for attempt in range(_WRITE_ATTEMPTS):
            try:
                cursor = self._live_connection().cursor()
                statement(cursor)
                self._live.commit()
                return
            except (pyodbc.OperationalError, pyodbc.Error) as exc:
                if not _is_transient(exc):
                    raise
                last = exc
                self._drop_connection()
                if attempt < _WRITE_ATTEMPTS - 1:
                    delay = _RETRY_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(
                        "warehouse link dropped (attempt %s/%s), reconnecting in %ss: %s",
                        attempt + 1, _WRITE_ATTEMPTS, delay, str(exc)[:120],
                    )
                    time.sleep(delay)
        raise GoldWriteFailed(
            f"warehouse link failed {_WRITE_ATTEMPTS} times: {last}"
        ) from last

    # ------------------------------------------------------------- primitives

    def _insert(self, table: str, columns: Sequence[str], rows: Sequence[tuple]) -> int:
        if not rows:
            return 0

        scoped = self._scoped()
        size = _batch_size(len(columns))

        written = 0
        for start in range(0, len(rows), size):
            batch = rows[start: start + size]
            self._execute(lambda cursor, batch=batch: scoped.insert(cursor, table, columns, batch, multirow=True))
            written += len(batch)
        return written

    def _supersede(self, client_id: int, program_code: str) -> None:
        """Retire the prior current rows for this client-programme.

        Scoped to the client because a run recomputes that client's whole unit
        series — a base year is only meaningful across the years around it, so
        superseding a single year would leave a mixed-run series behind.
        """
        scoped = TenantScopedQuery(client_id)
        for table in _VERSIONED_TABLES:
            sql = (
                f"UPDATE {GOLD_SCHEMA}.{table} SET is_current = 0 "
                "WHERE {tenant} AND program_code = ? AND is_current = 1"
            )
            self._execute(lambda cursor, sql=sql: scoped.execute(cursor, sql, [program_code]))

    def _supersede_manifests(self, client_id: int, program_code: str, run_id: str) -> None:
        sql = (
            f"UPDATE {OPS_SCHEMA}.run_manifest "
            "SET run_status = 'superseded', superseded_by_run_id = ? "
            "WHERE {tenant} AND program_code = ? AND run_status = 'success' "
            "AND run_id <> ?"
        )
        scoped = TenantScopedQuery(client_id)
        self._execute(lambda cursor: scoped.execute(cursor, sql, [run_id, program_code, run_id]))

    def _mark_failed(self, run_id: str) -> None:
        """Record that the run did not finish. Always on a FRESH connection.

        The first version of this reused the connection the write had just died
        on, so the marker failed too and left a partial run wearing a `success`
        manifest — the one state worse than an outright failure, because nothing
        downstream can tell it from a complete run.
        """
        self._drop_connection()
        try:
            scoped = self._scoped()
            sql = f"UPDATE {OPS_SCHEMA}.run_manifest SET run_status = 'failed' " "WHERE {tenant} AND run_id = ?"
            self._execute(lambda cursor: scoped.execute(cursor, sql, [run_id]))
        except Exception:
            logger.exception(
                "run %s failed AND could not be marked failed; the manifest still "
                "claims success and must be corrected by hand", run_id,
            )

    def _mark_complete(self, run_id: str, completed_at: Any) -> None:
        """Stamp the run finished. Until this lands the run reads as in flight."""
        scoped = self._scoped()
        sql = (
            f"UPDATE {OPS_SCHEMA}.run_manifest "
            "SET run_status = 'success', run_completed_at = ? WHERE {tenant} AND run_id = ?"
        )
        self._execute(lambda cursor: scoped.execute(cursor, sql, [completed_at, run_id]))

    def reap_stranded_runs(self, older_than_minutes: int | None = None) -> int:
        """Mark long-abandoned `running` manifests failed. Returns the row count.

        `write_run` already marks its own failure when the write RAISES. These
        rows come from the case it cannot cover: the process died outright, so
        no handler ran. Only a later sweep can close them.

        `run_completed_at` is deliberately left NULL. The run never completed,
        and inventing a completion time to satisfy a reader would put a fact in
        the audit record that never happened. `run_status` alone clears it,
        because every reader filters on the status too.

        Not a delete: a failed run is a real audit record, and the manifest is
        append-only apart from its own status transitions.
        """
        minutes = STRANDED_RUN_MINUTES if older_than_minutes is None else older_than_minutes
        # SYSUTCDATETIME because run_started_at is written as naive UTC.
        sql = (
            f"UPDATE {OPS_SCHEMA}.run_manifest "
            f"SET run_status = 'failed' "
            f"WHERE run_status = 'running' AND run_completed_at IS NULL "
            f"AND run_started_at < DATEADD(minute, ?, SYSUTCDATETIME())"
        )
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                _REAPER.execute(cursor, sql, [-abs(minutes)])
                reaped = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                connection.commit()
            finally:
                cursor.close()
        if reaped:
            logger.info(
                "reaped %s run(s) left running for more than %s minutes", reaped, minutes
            )
        return reaped

    # ------------------------------------------------------------------ write

    def write_run(self, payload: dict[str, Any]) -> dict[str, int]:
        """Write one run, and leave the store honest if it does not finish.

        Serialised per process. The writer holds ONE live connection, so two
        runs writing at once interleaved statements on it: one run's manifest
        insert was lost to the other's reconnect, leaving current Gold rows
        with no manifest (validation 9.7) while the client's latest run pointed
        at rows that were no longer current. Writes are allowed to be slow.
        """
        with _WRITE_LOCK:
            return self._write_run(payload)

    def _write_run(self, payload: dict[str, Any]) -> dict[str, int]:
        """Write one run, and leave the store honest if it does not finish.

        Fabric has no multi-statement transaction across these tables that would
        survive a process death, so the order matters: the manifest lands FIRST
        so no Gold row is ever orphaned (validation 9.7), and supersession of the
        prior run happens LAST so a failure mid-write leaves the previous run
        current rather than leaving the client with nothing.
        """
        from tools import gold_projection as gp

        client_id = payload["client_id"]
        program_code = payload["program_code"]
        run_id = payload["run_id"]
        self._client_id = client_id

        counts: dict[str, int] = {}
        try:
            counts["run_manifest"] = self._insert(
                f"{OPS_SCHEMA}.run_manifest",
                payload["run_manifest_columns"], [payload["run_manifest_row"]],
            )

            for table, columns, rows in (
                ("employee_period_fact", gp.EMPLOYEE_PERIOD_FACT_COLUMNS, payload["employee_period_fact"]),
                ("employee_eligibility", gp.EMPLOYEE_ELIGIBILITY_COLUMNS, payload["employee_eligibility"]),
                ("onezero_matrix", gp.ONEZERO_MATRIX_COLUMNS, payload["onezero_matrix"]),
                ("unit_month_summary", gp.UNIT_MONTH_SUMMARY_COLUMNS, payload["unit_month_summary"]),
                ("run_method_summary", gp.RUN_METHOD_SUMMARY_COLUMNS, payload["run_method_summary"]),
            ):
                counts[table] = self._insert(f"{GOLD_SCHEMA}.{table}", columns, rows)
                logger.info("run %s wrote %s rows to %s", run_id, counts[table], table)

            # The versioned pair: retire the old, then insert the new.
            self._supersede(client_id, program_code)

            for table, columns, rows in (
                ("unit_year_master", gp.UNIT_YEAR_MASTER_COLUMNS, payload["unit_year_master"]),
                ("unit_credit_installment", gp.UNIT_CREDIT_INSTALLMENT_COLUMNS, payload["unit_credit_installment"]),
            ):
                counts[table] = self._insert(f"{GOLD_SCHEMA}.{table}", columns, rows)
                logger.info("run %s wrote %s rows to %s", run_id, counts[table], table)

            self._supersede_manifests(client_id, program_code, run_id)

            # Last: the run is complete only once every row is down. Until this
            # stamp lands the manifest reads as in flight, which is the honest
            # description of a write still in progress.
            self._mark_complete(run_id, payload["run_completed_at"])
        except Exception:
            logger.exception("run %s failed mid-write; marking the manifest failed", run_id)
            self._mark_failed(run_id)
            raise
        finally:
            self._drop_connection()

        return counts

    # ------------------------------------------------------------- validation

    def validate(self) -> list[dict[str, Any]]:
        """Section 9 of the DDL. Every query must return zero rows.

        Run inside the run. Fabric accepts a duplicate `is_current = 1` row
        silently, so these queries are the only thing between a rerun and a
        double-counted total.
        """
        violations: list[dict[str, Any]] = []
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                for name, sql in SECTION_9_QUERIES:
                    _VALIDATION.execute(cursor, sql)
                    rows = cursor.fetchall()
                    if rows:
                        violations.append({
                            "query": name,
                            "rows": [tuple(r) for r in rows[:10]],
                            "row_count": len(rows),
                        })
            finally:
                cursor.close()
        return violations


#: Section 9 of `docs/data/schema/tcc-schema.fabric.sql`, verbatim in intent.
#: Named so a failure says which invariant broke, not just "validation failed".
SECTION_9_QUERIES: tuple[tuple[str, str], ...] = (
    ("9.1 one live claim per cell", f"""
        SELECT client_id, program_code, tax_year, COUNT(*) AS live_rows
        FROM {OPS_SCHEMA}.program_claim WHERE effective_to IS NULL
        GROUP BY client_id, program_code, tax_year HAVING COUNT(*) > 1
    """),
    ("9.2 one live engagement per client-program", f"""
        SELECT client_id, program_code, COUNT(*) AS live_rows
        FROM {OPS_SCHEMA}.program_engagement WHERE effective_to IS NULL
        GROUP BY client_id, program_code HAVING COUNT(*) > 1
    """),
    ("9.3 one live resolution per finding", f"""
        SELECT client_id, finding_id, COUNT(*) AS live_rows
        FROM {OPS_SCHEMA}.agent_finding_resolution WHERE superseded_at IS NULL
        GROUP BY client_id, finding_id HAVING COUNT(*) > 1
    """),
    ("9.4 one current row per unit-year-method", f"""
        SELECT client_id, worksite_id, program_code, method, tax_year, COUNT(*) AS current_rows
        FROM {GOLD_SCHEMA}.unit_year_master WHERE is_current = 1
        GROUP BY client_id, worksite_id, program_code, method, tax_year HAVING COUNT(*) > 1
    """),
    ("9.4b one current installment per window-year", f"""
        SELECT client_id, worksite_id, program_code, method, creation_year, tax_year,
               COUNT(*) AS current_rows
        FROM {GOLD_SCHEMA}.unit_credit_installment WHERE is_current = 1
        GROUP BY client_id, worksite_id, program_code, method, creation_year, tax_year
        HAVING COUNT(*) > 1
    """),
    ("9.4c installment arithmetic holds", f"""
        SELECT client_id, worksite_id, creation_year, tax_year,
               tranche_jobs, jobs_maintained, per_job_usd, claimable_usd
        FROM {GOLD_SCHEMA}.unit_credit_installment
        WHERE is_current = 1
          AND (   tax_year < creation_year
               OR jobs_maintained > tranche_jobs
               OR ABS(claimable_usd - ROUND(jobs_maintained * per_job_usd, 0)) > 0.51 )
    """),
    ("9.4d annual credit equals jobs x rate", f"""
        SELECT client_id, worksite_id, tax_year, method,
               eligible_jobs, per_job_usd, annual_credit_usd
        FROM {GOLD_SCHEMA}.unit_year_master
        WHERE is_current = 1 AND eligible_jobs IS NOT NULL AND per_job_usd IS NOT NULL
          AND ABS(annual_credit_usd - ROUND(eligible_jobs * per_job_usd, 0)) > 0.51
    """),
    ("9.4e new jobs within net-new", f"""
        SELECT client_id, worksite_id, tax_year, method,
               net_new_vs_base, new_jobs_created, high_water_mark
        FROM {GOLD_SCHEMA}.unit_year_master
        WHERE is_current = 1 AND new_jobs_created > net_new_vs_base + 0.01
    """),
    ("9.5 declined claims carry a reason", f"""
        SELECT claim_id, client_id, program_code, tax_year
        FROM {OPS_SCHEMA}.program_claim
        WHERE status = 'declined'
          AND (decline_reason IS NULL OR LTRIM(RTRIM(decline_reason)) = '')
    """),
    ("9.6a program_claim.status in domain", f"""
        SELECT DISTINCT status FROM {OPS_SCHEMA}.program_claim
        WHERE status NOT IN ('not_assessed','assessed','proposed','declined',
                             'claimed','certified','amended')
    """),
    ("9.6b program_claim.provenance in domain", f"""
        SELECT DISTINCT provenance FROM {OPS_SCHEMA}.program_claim
        WHERE provenance NOT IN ('computed','filed_by_us','client_asserted',
                                 'inherited','authority_confirmed')
    """),
    ("9.6c program_engagement.scope in domain", f"""
        SELECT DISTINCT scope FROM {OPS_SCHEMA}.program_engagement
        WHERE scope NOT IN ('in_scope','out_of_scope','prospective')
    """),
    ("9.6d finding resolution in domain", f"""
        SELECT DISTINCT resolution FROM {OPS_SCHEMA}.agent_finding_resolution
        WHERE resolution NOT IN ('accept','assign','drop','flag')
    """),
    ("9.6e eligibility method in domain", f"""
        SELECT DISTINCT method FROM {GOLD_SCHEMA}.employee_eligibility
        WHERE method NOT IN ('min_max','pay_period')
    """),
    ("9.6f unit_year_master.status in domain", f"""
        SELECT DISTINCT status FROM {GOLD_SCHEMA}.unit_year_master
        WHERE status NOT IN ('base','above_minimum','below_minimum','partial','no_data',
                             'before_base','in_progress')
    """),
    ("9.6g threshold_source in domain", f"""
        SELECT DISTINCT threshold_source FROM {GOLD_SCHEMA}.unit_year_master
        WHERE threshold_source IS NOT NULL
          AND threshold_source NOT IN ('designation','rule_pack')
    """),
    ("9.6h tier_source in domain", f"""
        SELECT DISTINCT tier_source FROM {GOLD_SCHEMA}.unit_year_master
        WHERE tier_source IS NOT NULL AND tier_source NOT IN ('prototype','unassigned')
    """),
    ("9.7 no orphaned run references", f"""
        SELECT DISTINCT g.run_id
        FROM {GOLD_SCHEMA}.unit_month_summary g
        LEFT JOIN {OPS_SCHEMA}.run_manifest r ON r.run_id = g.run_id
        WHERE r.run_id IS NULL
    """),
    ("9.8 average headcount is total / 12", f"""
        SELECT client_id, tax_year, method, worksite_id, total, average_headcount
        FROM {GOLD_SCHEMA}.unit_month_summary
        WHERE ABS(average_headcount - (total / 12.0)) > 0.01
    """),
    ("9.9 no model wrote a figure", f"""
        SELECT action_id, agent_name, occurred_at
        FROM {OPS_SCHEMA}.agent_action_audit
        WHERE is_deterministic_path = 0 AND run_id IS NOT NULL
    """),
)
