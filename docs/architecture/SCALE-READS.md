# Scale-efficient source reads

Principles: **read once, read only what is needed, never recompute what has not changed.** A request-path read that scales with a
whole table is a defect. Design volume: about 9.3 billion payroll rows, about 1.1 billion employment rows, about 363 million
addresses, about 9,000 accounts with a heavy skew (about a million payroll rows per account on average).

## What a request reads now

| Read | Before | Now |
| --- | --- | --- |
| Tenant tables (`Account`, `Entity`, `Location`, `PayCode`, `Payroll`) | filtered on the tenant column | same; Delta partition pruning on the tenant column |
| `Address`, `StateCountyZip`, `Employment`, `EntityFiscalYearRules` | **read in full**, filtered in Python | read by the keys the account references: a range filter on the key (row-group statistics skip what cannot match) then a semi-join in Arrow. Never in full |
| Columns | every column | only the columns the engine's path needs (`"engine": false` in the source mapping marks the rest) |
| An unknown account | every table read in full, and again on the next request | one tiny tenant-filtered `Account` read, then remembered for a short time |
| Repeat requests | an unbounded process-lifetime dict | a bounded LRU cache (`SOURCE_CACHE_MB`, `SOURCE_CACHE_ACCOUNTS`) keyed by account and the Payroll Delta version |
| Concurrent requests for one account | each paid for its own read | single-flight: one read, shared |
| An enormous account | loaded until the process ran out of memory | refused with a typed error beyond `SOURCE_MAX_ACCOUNT_ROWS`, before it is converted to Python objects |
| The portfolio page's engagement scopes | one read per client (N+1) | a few batched reads (500 clients each) |

## Change detection

The dataset cache is keyed by `(account, Payroll Delta version)`. The version is re-checked at most every
`SOURCE_VERSION_CHECK_SECONDS` (default 300; opening a Delta log can cost tens of seconds on a slow capacity). A new version makes the
next request for that account read it again and drops the superseded entry; other accounts stay cached. Detection is by table
version: any new Payroll version marks every account stale. Per-account detection needs the Change Data Feed (or a per-account
high-water mark) on the source and is the next step.

## Silver (optional, off by default)

`scripts/fabric/build-silver.py` builds `tcc_silver_pay_period`: the engine's rows (employee x pay period, with the worksite's state
and county, the unit id, the FEIN, hours, wages, pay date and pay code, all joined) in one Delta table partitioned by the tenant column,
recording the source version on every row. `SOURCE_SILVER=auto` reads one account's partition and falls back to the raw path for an
account with none; `require` refuses instead; `off` (the default) changes nothing.

Silver is **unaware of the app-owned lookups**: the pay code is stored as the customer wrote it and the canonical category, the
unmapped-code accounting and the `strict` policy are applied at read time ([APP-OWNED-LOOKUPS.md](APP-OWNED-LOOKUPS.md)). An override
authored tomorrow takes effect without a rebuild. A test proves the Silver rows equal the raw rows account for account, and that the
assessment gives the same figures.

A refresh replaces one account's partition (a predicate write) and is a no-op for an account already built from the current version.
The script is the reference implementation of that logic and has been run on local lakes; at the design volume it is a Spark job in a
Fabric notebook or pipeline built from the same logic.

## What is observable

Every Delta read and every cache decision is counted (`data/source/read_stats.py`): table, rows, bytes, columns, seconds, whether a filter
was applied, the Delta version, cache hits / misses / negative hits / evictions / single-flight waits. `/api/ready` reports them under
`source_schema.reads`. `scripts/fabric/benchmark-source-reads.py` measures a small account, the largest account, the portfolio view and a
repeat unknown id on a synthetic lake, reporting time, peak memory and rows and bytes read; run it before and after a change.

A test fails if a Delta table is read anywhere but the one filtered, projected scan, and if a request for one account reads a whole
`Employment`, `Address` or `Payroll` table.

## Not done (needs the target environment or a decision)

- The claims coverage read (`portfolio_coverage`) still loads every claim and filters in Python: pushing the program, year, outcome, scope
  and paging filters into SQL and paging in the database is the next step. It scales with claims, not payroll.
- The portfolio footprint still uses the guarded payroll `GROUP BY` (`PORTFOLIO_FOOTPRINT_MODE`); the replacement is an account-level
  aggregate written by the Silver job, which needs the job to run at scale.
- Columnar hot path (Arrow end to end through the engine): the projection still builds Python rows per account. A benchmark at scale decides
  whether DuckDB or Polars is justified.
- Measured only on synthetic local lakes. Latency, throughput and cost on the real lakehouse and capacity are Live checks.
