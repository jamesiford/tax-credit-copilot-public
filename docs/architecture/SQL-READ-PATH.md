# The SQL-endpoint payroll read path (proposal and spike)

**Status: proposal. A spike exists behind `SOURCE_READ_MODE=sql`; the default (`onelake`) is unchanged and nothing adopts it.**
Recommendation at the end: *adopt later*, with the evidence and the live checks that would make it *adopt*.

## Why

The row-level payroll read (`FabricLakehouseReader.for_account` / `bcs_rows`, through `load_pay_periods`) opens Delta files
over OneLake. That needs a Fabric workspace role that can read files: **Contributor** (or Member or Admin). A **Viewer** can
only use the SQL analytics endpoint. Giving an application a write-capable role on a payroll workspace, to read, is a governance
smell. The existing SQL path (`source_sql.py`) answers only small aggregates (client scope, client book, fiscal windows); the
certified engine needs row grain.

Measured earlier and recorded in `source_sql.py`: the endpoint counted a 384,433-row account in about 169 ms where the OneLake
route took about 132 s cold. That is an aggregate against a cold file open; it is the reason to try, not a promise for row
streaming.

## What the spike is

`SOURCE_READ_MODE=onelake|sql` (default `onelake`, [ENV-VARS](ENV-VARS.md)). Both modes sit behind the one scan the reader
already has (`FabricLakehouseReader._scan`), which returns a list of dicts keyed by **logical** field name. In `sql` mode that
scan is `data/source/sql_scan.py`:

- **Query shapes.** One projected statement per read, the engine's columns only (never `SELECT *`):
  `SELECT [c1],[c2] FROM [lakehouse].[schema].[Table] WHERE [tenant] = ?` for a tenant read, and batched
  `WHERE [key] IN (?, ...)` lists for a keyed read of a table with no tenant column (`Address`, `Employment`,
  `StateCountyZip`, `EntityFiscalYearRules`), each batch of at most 900 ids (SQL Server's ceiling is 2,100 parameters). The
  OneLake path reads a key *range* and semi-joins; `IN` reads exactly the rows it needs.
- **Names and types come from the mapping.** Columns are discovered once per table per process from
  `INFORMATION_SCHEMA.COLUMNS`, then resolved by the same mapping as the Delta path
  ([SOURCE-MAPPING](SOURCE-MAPPING.md)), so a different table or column shape needs no code. A table with no columns is an
  absent table, raised as the `TableNotFoundError` the optional-table handling already catches.
- **Streaming and memory.** Rows come back with `fetchmany` (50,000 at a time) and become dicts as they arrive; the
  account-size guard (`SOURCE_MAX_ACCOUNT_ROWS`) stops the stream at the limit instead of after draining the table. Memory is
  the same as the OneLake path's, because the engine still takes lists of dicts. The cure for that is the Silver table
  (below), not this reader.
- **No storage token and no Delta handle.** In `sql` mode the reader never asks for a storage token and never opens a Delta
  table (a test proves it). The identity needs the SQL endpoint and `SELECT` only.
- **Not covered by the spike:** the Silver table (Delta only; `bcs_rows` reads the raw tables in `sql` mode, and
  `SOURCE_SILVER=require` is refused), `table_lineage` and the row estimate (diagnostics), and the writers.

## What is recorded for reproducibility, and what is not

A run must be reproducible: "which data did you read?" The OneLake path keys its cache and its provenance on the Payroll
table's **Delta version**. The SQL endpoint exposes no Delta version, so in `sql` mode the spike records none and cached
datasets are not invalidated by a reload until they age out. That is a real gap, not a detail. Options, in order of
preference: (1) read the **Silver** table over SQL and record the version it was built from (Silver already carries a built
version marker); (2) a content fingerprint taken in the same statement batch (row count and the latest modified date for
the account); (3) ask the platform for the endpoint's metadata sync state. **Metadata sync lag** matters too: the SQL
endpoint can trail the Delta tables by seconds to minutes after a load, so "the version read" and "the version loaded" can
differ.

## Parity: what was proved offline

The endpoint is **emulated** (`backend/tests/sql_endpoint_fake.py`: SQLite behind the ODBC types), so what is proved is what
this repository controls:

| Check | Result |
|---|---|
| Datasets from both modes, six generated accounts | identical |
| Engine rows (`source_to_bcs_rows`), values **and** order | identical |
| Min-Max and Pay Period results from both modes | identical |
| Engine result under shuffled row order (the endpoint promises no order) | unchanged |
| Statements: projected, filtered, batched under the parameter ceiling, streamed | pinned by tests |
| No storage token or Delta handle in `sql` mode | pinned by a test |
| Default mode unchanged | the whole existing suite passes with the new code present |

Spike benchmark (`scripts/fabric/spike-sql-read.py`, 40 accounts, 400,000 payroll rows, one cold read each). **Rows,
statements and payload are real; seconds and memory for `sql` measure the emulation, not Fabric.**

| Account | Payroll rows | OneLake: rows read / reads | SQL: rows read / statements |
|---|---|---|---|
| small | 1,880 | 1,988 / 8 | 1,983 / 18 |
| median | 4,030 | 4,241 / 8 | 4,238 / 18 |
| large (skewed) | 108,774 | 113,096 / 8 | 113,095 / 22 |

The statement count includes one column-discovery query per table on a cold process (about 10); later reads skip it. Peak
Python memory is equal in both modes (2.4, 5.1 and 136 MB), as expected.

## Re-certification plan

The certified figures (10,236 employees, 539 Min-Max, 656 Pay Period) are computed from the partner's reference extract by
code that does not read the lakehouse (`tools/reference_source.py`), so a read-mode switch cannot move them and they cannot
prove the SQL path. The proof for adoption is the **per-client** read, which reads the lakehouse:

1. Load the reference client into the lakehouse and run, with `TCC_FABRIC_TESTS=1`, the per-client agreement tests
   (`test_the_per_client_read_agrees_with_the_certified_figures` and the engine parity suites) once with
   `SOURCE_READ_MODE=onelake` and once with `sql`. Every figure must be identical.
2. For every account, compare the two modes' datasets (the spike script's parity check, pointed at the real lake).
3. Report any numeric difference by cause. Candidates to look for: decimal precision and scale; `char(n)` padding; the
   endpoint's **collation** (case sensitivity of ids and codes); datetime precision and time zone (Delta timestamps are UTC,
   `datetime2` is naive; payroll dates are `date`, which is unaffected); nulls; and the type spellings the endpoint reports.
4. Row order is **not** a candidate: the engine's answer is proved independent of it above.

## Security review

| | OneLake path (today) | SQL path |
|---|---|---|
| Workspace role | Contributor or higher (can read files, and also write them) | Viewer is enough to reach the endpoint |
| What the app can read | every file in the lakehouse the role covers | what T-SQL permissions allow: object-level `SELECT` on the named tables, and optionally row- and column-level security |
| Write access | held, unused by the reader | none |
| Grant | workspace role | `python scripts/grant-warehouse-sql.py --profile lakehouse` grants object-level `SELECT` on the source tables only, no schema grant, never the gateway identity |

What remains in the Contributor path: the **loader** (`data/source/load_fabric.py`, `build_lake`, Silver build), which writes
Delta files and so needs a role that can write. That identity is an operator or pipeline identity, not the app's. OneLake
data access roles can narrow file access further for the OneLake path; whether they apply to the SQL endpoint in your tenant
is a question for the platform team, not something to assume. Private link: the SQL endpoint host is a different name from the
blob host and has its own DNS check ([RUNBOOK](RUNBOOK-PRIVATE-LINK-AND-IDENTITY.md)).

## Failure modes

An absent optional table is "no rows", said once; an unreadable table is an outage (a timeout or a 403 raises), as on the
OneLake path. A statement timeout cancels on the server (`cursor.timeout`). A paused capacity makes every read fail the same
way as for OneLake. A metadata-sync lag shows as a stale dataset, not an error, which is why the version question above
matters.

## Recommendation: adopt later

**Evidence for.** The query shapes are exact and bounded; parity with the OneLake path is exact on every offline check; the
engine does not depend on row order; the identity needed is strictly weaker (Viewer plus `SELECT`); nothing in the default path
changes.

**Why not yet.** Nothing here measured the real endpoint: speed at 9 billion rows with partition pruning on the tenant column,
the type and collation behaviour, and the metadata-sync lag are all unknown, and the data version cannot be recorded. The row
engine is still list-of-dict, so memory is unchanged for the largest accounts.

**What makes it "adopt".** (1) The live checks below pass. (2) The version is recorded, preferably by reading **Silver** over
SQL, which is also the compact, prepared target for the largest accounts. (3) The per-client re-certification is identical in
both modes. Until then keep `onelake`, and keep the spike off.

## Live checks (not done)

1. `python scripts/fabric/spike-sql-read.py`'s parity and counts against the real lakehouse over the SQL endpoint, for a small,
   a median and the largest account: wall time, round trips, memory.
2. `INFORMATION_SCHEMA.COLUMNS` and bracketed quoted names against the real endpoint; the type spellings it reports.
3. Partition pruning on the tenant column: the statement's plan and the files touched for one account of a very large table.
4. The endpoint's collation and its effect on the keyed `IN` lists and on string ids.
5. Metadata sync lag after a load, and a way to read the version.
6. The per-client re-certification (above), with `TCC_FABRIC_TESTS=1`, in both modes.
