# Source lakehouse layout guidance

Recommendations for a lakehouse that feeds this application at about 9 billion payroll rows. **Nothing here is applied by the application**:
it only reads. The assumptions are stated so they can be checked; where one is wrong the advice changes.

## Assumptions

- The reads are by account: one account's payroll (and the dimension rows it references), never a scan of the table.
- `Payroll` carries the tenant column and a pay-period end date; accounts are heavily skewed (many small, a few with tens of millions of rows).
- The lake is Delta on OneLake, read through the Delta log (and, for aggregates, the SQL analytics endpoint).
- Source data changes in batches (loads), not per request.

## Payroll

- **Partition or cluster on `(account, pay period end)`.** The tenant column is what every request filters on. Physical partitioning on a column
  with about 9,000 values is acceptable for Delta; liquid clustering on `(account, pay period end)` is preferable where available because it adapts to
  skew and still prunes by year. Pruning by pay period end lets a client-year drill-through read one year.
- **Target file sizes of 128 MB to 1 GB.** Thousands of small files (one per load per account) make the Delta log and the listing the cost. Compact
  after each load (`OPTIMIZE`), and schedule it.
- **V-Order** on the written files (Fabric) for read-heavy workloads.
- **Statistics on the columns the app filters and joins on** (account, pay period end, employee id, location id): the row-group range filters
  the reader pushes down (`>=` and `<=` on a key) are only as good as the statistics.
- **Skewed accounts.** An account with tens of millions of rows should not sit in one file group; cluster so its files are split by pay period end.
  The application refuses an account over `SOURCE_MAX_ACCOUNT_ROWS` rather than load it, so a very large account is read by year (drill-through) or from
  the pre-aggregated Silver table.
- Keep `PaycheckDate`/`PayDate` as a `date`, money as `decimal(18,2)`, and the tenant column non-null: a null in a filter column defeats pruning.

## Dimensions

- **`Location`** has the tenant column: partition or cluster on it. **`Address`** and **`StateCountyZip`** have none, so the app reads them by key. Sort or
  cluster `Address` on `AddressId` so the range filter on a handful of ids skips almost every row group; same for `StateCountyZip` on its key.
- **`Employment`** (about a billion rows) is read by employee id for one account. Cluster on `EmployeeId`. If employee ids are not contiguous per account,
  a range filter prunes little and the semi-join reads more than it needs: an account-keyed copy (or an `AccountId` column on `Employment`) removes the problem.
- Small lookups need nothing.

## Maintenance

- `OPTIMIZE` after loads; `VACUUM` with a retention that keeps the versions the app's cache keys can reference (a few days).
- Enable the Change Data Feed on `Payroll` if per-account refresh of derived tables is wanted: it replaces "any new version marks every account stale".
- Record per load which accounts changed (a small `load_manifest` table). It makes incremental Silver refresh and cache invalidation exact.

## What to measure at the real scale

Per account size class (small, median, very large): the bytes and files a read touches, the time to open the Delta log, and the time for the keyed reads of
`Address` and `Employment`. `scripts/fabric/benchmark-source-reads.py` produces the same measurements on a synthetic lake for comparison.
