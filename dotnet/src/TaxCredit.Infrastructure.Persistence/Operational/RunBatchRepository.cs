using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Transactional batch store shared by independent workers; queue authority is the database, not an in-process mutex.</summary>
public sealed partial class RunBatchRepository(PersistenceDatabase database) : IRunBatchRepository
{
    /// <summary>Indicates accepted batches are persisted.</summary>
    public bool IsDurable { get; } = true;

    /// <inheritdoc />
    public RunBatch Create(RunBatch batch, IReadOnlyList<RunBatchItem> items)
    {
        ArgumentNullException.ThrowIfNull(batch);
        ArgumentNullException.ThrowIfNull(items);
        if (items.Any(item => item.BatchId != batch.BatchId || item.Status != ItemStatus.Queued || item.Attempts != 0
                || item.LeaseOwner is not null) || items.Select(item => item.ItemId).Distinct(StringComparer.Ordinal).Count() != items.Count)
        {
            throw new ArgumentException("New batch items must be distinct, untouched queued work belonging to the batch.", nameof(items));
        }

        return database.Transact(session =>
        {
            if (batch.IdempotencyKey is { } key && FindByKeyIn(session, key, batch.RequestedBy) is { } existing)
            {
                return existing;
            }

            if (GetIn(session, batch.BatchId) is not null)
            {
                throw new InvalidOperationException("The batch identity is already recorded.");
            }

            foreach (var chunk in items.Chunk(1000))
            {
                var placeholders = string.Join(", ", chunk.Select(_ => "?"));
                if (session.QueryExempt(SqlExemption.Worker, "SELECT item_id FROM {ops.run_batch_item} WHERE item_id IN (" + placeholders + ")",
                    chunk.Select(item => (object?)item.ItemId).ToArray()).Count != 0)
                {
                    throw new InvalidOperationException("A queue item identity is already recorded.");
                }
            }

            var counts = RunBatchRows.Counters(items.GroupBy(item => item.Status.Value()).ToDictionary(g => g.Key, g => (long)g.Count(), StringComparer.Ordinal));
            InsertGlobal(session, RunBatchRows.BatchTable, RunBatchRows.BatchColumns, RunBatchRows.BatchValues(session, batch, counts));
            foreach (var group in items.GroupBy(item => item.ClientId))
            {
                session.Insert(group.Key, RunBatchRows.ItemTable, RunBatchRows.ItemColumns, group.Select(item => RunBatchRows.ItemValues(session, item)).ToArray());
            }

            return RefreshIn(session, batch.BatchId, batch.RequestedAt);
        });
    }

    /// <inheritdoc />
    public RunBatch? Get(string batchId)
    {
        using var session = database.Open();
        return GetIn(session, batchId);
    }

    /// <inheritdoc />
    public RunBatch? FindByKey(string key, string requestedBy)
    {
        using var session = database.Open();
        return FindByKeyIn(session, key, requestedBy);
    }

    /// <inheritdoc />
    public RunBatch? FindOpenIdentical(string kind, string specJson, string requestedBy)
    {
        using var session = database.Open();
        var canonical = PyJson.Dumps(PyJson.Loads(specJson), sortKeys: true, compact: false);
        return session.QueryExempt(SqlExemption.Worker, RunBatchRows.BatchSelect
            + " WHERE kind = ? AND scope_spec = ? AND requested_by = ? AND status IN ('queued', 'running') ORDER BY requested_at, batch_id",
            kind, canonical, requestedBy).Select(RunBatchRows.Batch).FirstOrDefault();
    }

    /// <inheritdoc />
    public (IReadOnlyList<RunBatch> Items, long Total) ListBatches(int limit, int offset, string? status = null)
    {
        PageBounds(limit, offset);
        return database.Transact(session =>
        {
            var where = string.IsNullOrEmpty(status) ? "" : " WHERE status = ?";
            object?[] args = string.IsNullOrEmpty(status) ? [] : [status];
            var total = new OpsRow(session.QueryExempt(SqlExemption.Worker, "SELECT COUNT(*) AS n FROM " + RunBatchRows.BatchTable + where, args)[0]).Long("n");
            var rows = session.QueryExempt(SqlExemption.Worker,
                session.Dialect.Page(RunBatchRows.BatchSelect + where + " ORDER BY requested_at DESC, batch_id", limit, offset), args);
            return ((IReadOnlyList<RunBatch>)rows.Select(RunBatchRows.Batch).ToArray(), total);
        });
    }

    /// <inheritdoc />
    public (IReadOnlyList<RunBatchItem> Items, long Total) ListItems(string batchId, string? status, int limit, int offset)
    {
        PageBounds(limit, offset);
        return database.Transact(session =>
        {
            var where = " WHERE batch_id = ?" + (string.IsNullOrEmpty(status) ? "" : " AND status = ?");
            object?[] args = string.IsNullOrEmpty(status) ? [batchId] : [batchId, status];
            var total = new OpsRow(session.QueryExempt(SqlExemption.Worker, "SELECT COUNT(*) AS n FROM " + RunBatchRows.ItemTable + where, args)[0]).Long("n");
            var rows = session.QueryExempt(SqlExemption.Worker,
                session.Dialect.Page(RunBatchRows.ItemSelect + where + " ORDER BY seq, item_id", limit, offset), args);
            return ((IReadOnlyList<RunBatchItem>)rows.Select(RunBatchRows.Item).ToArray(), total);
        });
    }

    /// <inheritdoc />
    public RunBatchItem? GetItem(long clientId, string itemId)
    {
        using var session = database.Open();
        return session.Query(clientId, RunBatchRows.ItemSelect + " WHERE {tenant} AND item_id = ?", itemId).Select(RunBatchRows.Item).SingleOrDefault();
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, long> StatusCounts(string batchId)
    {
        using var session = database.Open();
        return CountsIn(session, batchId);
    }

    /// <inheritdoc />
    public RunBatch Refresh(string batchId, PyDateTime now) => database.Transact(session => RefreshIn(session, batchId, now));

    /// <inheritdoc />
    public long Cancel(string batchId, PyDateTime now) => database.Transact(session =>
    {
        session.ExecuteExempt(SqlExemption.Worker, "UPDATE " + RunBatchRows.BatchTable + " SET cancel_requested = 1 WHERE batch_id = ?", batchId);
        var count = session.ExecuteExempt(SqlExemption.Worker, "UPDATE " + RunBatchRows.ItemTable
            + " SET status = 'cancelled', finished_at = ? WHERE batch_id = ? AND status = 'queued'", OpsRow.Clock(session, now), batchId);
        RefreshIn(session, batchId, now);
        return (long)count;
    });

    /// <inheritdoc />
    public long RetryFailed(string batchId, PyDateTime now) => database.Transact(session =>
    {
        var count = session.ExecuteExempt(SqlExemption.Worker, "UPDATE " + RunBatchRows.ItemTable
            + " SET status = 'queued', attempts = 0, not_before = NULL, error_dependency = NULL, error_message = NULL, "
            + "finished_at = NULL, lease_owner = NULL, lease_expires_at = NULL WHERE batch_id = ? AND status = 'failed'", batchId);
        if (count > 0)
        {
            session.ExecuteExempt(SqlExemption.Worker, "UPDATE " + RunBatchRows.BatchTable
                + " SET cancel_requested = 0, finished_at = NULL WHERE batch_id = ?", batchId);
        }

        RefreshIn(session, batchId, now);
        return (long)count;
    });

    private static RunBatch? GetIn(SqlSession session, string batchId) =>
        session.QueryExempt(SqlExemption.Worker, RunBatchRows.BatchSelect + " WHERE batch_id = ?", batchId).Select(RunBatchRows.Batch).SingleOrDefault();

    private static RunBatch? FindByKeyIn(SqlSession session, string key, string requestedBy) =>
        session.QueryExempt(SqlExemption.Worker, RunBatchRows.BatchSelect + " WHERE idempotency_key = ? AND requested_by = ? ORDER BY requested_at, batch_id",
            key, requestedBy).Select(RunBatchRows.Batch).FirstOrDefault();

    private static Dictionary<string, long> CountsIn(SqlSession session, string batchId) =>
        session.QueryExempt(SqlExemption.Worker, "SELECT status, COUNT(*) AS n FROM " + RunBatchRows.ItemTable + " WHERE batch_id = ? GROUP BY status", batchId)
            .Select(row => new OpsRow(row)).ToDictionary(row => row.Required("status"), row => row.Long("n"), StringComparer.Ordinal);

    private static RunBatch RefreshIn(SqlSession session, string batchId, PyDateTime now)
    {
        var batch = GetIn(session, batchId) ?? throw new KeyNotFoundException("The batch does not exist.");
        var statuses = CountsIn(session, batchId);
        var status = RunStateMachine.BatchStatusOf(statuses, batch.CancelRequested);
        var counters = RunBatchRows.Counters(statuses);
        var done = status is BatchStatus.Succeeded or BatchStatus.Partial or BatchStatus.Failed or BatchStatus.Cancelled;
        var normalized = OpsRow.ParseInstant(OpsRow.Clock(now))!.Value;
        var started = batch.StartedAt ?? (status != BatchStatus.Queued ? normalized : (PyDateTime?)null);
        var finished = done ? batch.FinishedAt ?? normalized : (PyDateTime?)null;
        var args = new List<object?> { status.Value() };
        args.AddRange(RunBatchRows.CounterColumns.Select(column => (object?)counters[column]));
        args.AddRange([OpsRow.Clock(session, started), OpsRow.Clock(session, finished), batchId]);
        session.ExecuteExempt(SqlExemption.Worker, "UPDATE " + RunBatchRows.BatchTable + " SET status = ?, "
            + string.Join(", ", RunBatchRows.CounterColumns.Select(column => column + " = ?"))
            + ", started_at = ?, finished_at = ? WHERE batch_id = ?", args.ToArray());
        return batch with { Status = status, Counts = RunBatchRows.CountsDocument(counters), StartedAt = started, FinishedAt = finished };
    }

    private static void InsertGlobal(SqlSession session, string table, IReadOnlyList<string> columns, object?[] values) =>
        session.ExecuteExempt(SqlExemption.Worker, "INSERT INTO " + table + " (" + string.Join(", ", columns)
            + ") VALUES (" + string.Join(", ", columns.Select(_ => "?")) + ")", values);

    private static void PageBounds(int limit, int offset)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(limit);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(limit, 1000);
        ArgumentOutOfRangeException.ThrowIfNegative(offset);
    }
}
