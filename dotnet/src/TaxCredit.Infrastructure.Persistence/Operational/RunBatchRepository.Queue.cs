using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

public sealed partial class RunBatchRepository
{
    private const string Owned = " WHERE {tenant} AND item_id = ? AND lease_owner = ? "
        + "AND status IN ('leased', 'running') AND lease_expires_at > ?";

    /// <inheritdoc />
    public IReadOnlyList<RunBatchItem> Claim(string owner, int limit, int leaseSeconds, PyDateTime now)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(owner);
        PageBounds(limit, 0);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(leaseSeconds);
        return database.Transact(session =>
        {
            var clock = OpsRow.Clock(session, now);
            var sql = "SELECT " + string.Join(", ", RunBatchRows.ItemColumns.Select(column => "i." + column))
                + " FROM tcc_ops.run_batch_item i JOIN tcc_ops.run_batch b ON b.batch_id = i.batch_id "
                + "WHERE i.status = 'queued' AND b.cancel_requested = 0 AND (i.not_before IS NULL OR i.not_before <= ?) "
                + "AND NOT EXISTS (SELECT 1 FROM tcc_ops.run_batch_item x WHERE x.client_id = i.client_id "
                + "AND x.status IN ('leased', 'running') AND x.lease_expires_at > ?) ORDER BY b.requested_at, i.seq, i.item_id";
            var candidates = session.QueryExempt(SqlExemption.Worker, session.Dialect.Page(sql, Math.Min(10000, limit * 20 + 20), 0), clock, clock);
            var taken = new List<RunBatchItem>();
            var clients = new HashSet<long>();
            foreach (var candidate in candidates.Select(RunBatchRows.Item))
            {
                if (taken.Count == limit)
                {
                    break;
                }

                if (!clients.Add(candidate.ClientId))
                {
                    continue;
                }

                var expires = OpsRow.AddSeconds(now, leaseSeconds);
                var won = session.Execute(candidate.ClientId, "UPDATE tcc_ops.run_batch_item "
                    + "SET status = 'leased', lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?, attempts = attempts + 1 "
                    + "WHERE {tenant} AND item_id = ? AND status = 'queued'", owner, OpsRow.Clock(session, expires), clock, candidate.ItemId);
                if (won == 1)
                {
                    taken.Add(candidate with
                    {
                        Status = ItemStatus.Leased,
                        LeaseOwner = owner,
                        LeaseExpiresAt = expires,
                        HeartbeatAt = OpsRow.ParseInstant(OpsRow.Clock(now)),
                        Attempts = candidate.Attempts + 1
                    });
                }
            }

            return (IReadOnlyList<RunBatchItem>)taken;
        });
    }

    /// <inheritdoc />
    public bool Heartbeat(long clientId, string itemId, string owner, int leaseSeconds, PyDateTime now)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(leaseSeconds);
        return database.Transact(session => session.Execute(clientId, "UPDATE tcc_ops.run_batch_item SET heartbeat_at = ?, lease_expires_at = ?"
            + Owned, OpsRow.Clock(session, now), OpsRow.Clock(session, OpsRow.AddSeconds(now, leaseSeconds)), itemId, owner, OpsRow.Clock(session, now)) == 1);
    }

    /// <inheritdoc />
    public bool MarkRunning(long clientId, string itemId, string owner, long? taxYear, string? programCode, PyDateTime now) =>
        database.Transact(session => session.Execute(clientId, "UPDATE tcc_ops.run_batch_item SET status = 'running', started_at = ?, tax_year = ?, program_code = ?"
            + Owned + " AND status = 'leased'", OpsRow.Clock(session, now), taxYear, programCode, itemId, owner, OpsRow.Clock(session, now)) == 1);

    /// <inheritdoc />
    public bool Finish(long clientId, string itemId, string owner, PyDateTime now, ItemResult result, string batchId)
    {
        ArgumentNullException.ThrowIfNull(result);
        if (!RunStateMachine.TerminalItems.Contains(result.Status) || result.Status == ItemStatus.Cancelled)
        {
            throw new ArgumentException("A worker must finish with a non-cancelled terminal result.", nameof(result));
        }

        return database.Transact(session =>
        {
            var kept = session.Execute(clientId, "UPDATE tcc_ops.run_batch_item SET status = ?, finished_at = ?, run_id = ?, "
                + "skip_reason = ?, error_dependency = ?, error_message = ?, tax_year = COALESCE(?, tax_year), lease_owner = NULL, lease_expires_at = NULL"
                + Owned + " AND batch_id = ?", result.Status.Value(), OpsRow.Clock(session, now), result.RunId, result.SkipReason, result.ErrorDependency,
                Truncate(result.ErrorMessage), result.TaxYear, itemId, owner, OpsRow.Clock(session, now), batchId) == 1;
            if (kept)
            {
                RefreshIn(session, batchId, now);
            }

            return kept;
        });
    }

    /// <inheritdoc />
    public bool Requeue(long clientId, string itemId, string owner, PyDateTime now, PyDateTime notBefore, string? dependency, string? message) =>
        database.Transact(session => session.Execute(clientId, "UPDATE tcc_ops.run_batch_item SET status = 'queued', not_before = ?, "
            + "error_dependency = ?, error_message = ?, lease_owner = NULL, lease_expires_at = NULL"
            + Owned, OpsRow.Clock(session, notBefore), dependency, Truncate(message), itemId, owner, OpsRow.Clock(session, now)) == 1);

    /// <inheritdoc />
    public bool Release(long clientId, string itemId, string owner, PyDateTime now) =>
        database.Transact(session => session.Execute(clientId, "UPDATE tcc_ops.run_batch_item SET status = 'queued', attempts = attempts - 1, "
            + "lease_owner = NULL, lease_expires_at = NULL" + Owned, itemId, owner, OpsRow.Clock(session, now)) == 1);

    /// <inheritdoc />
    public IReadOnlyList<string> ReapExpired(PyDateTime now, int maxAttempts)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxAttempts);
        return database.Transact(session =>
        {
            var clock = OpsRow.Clock(session, now);
            var lapsed = session.QueryExempt(SqlExemption.Worker, RunBatchRows.ItemSelect
                + " WHERE status IN ('leased', 'running') AND lease_expires_at <= ?", clock).Select(RunBatchRows.Item).ToArray();
            foreach (var item in lapsed)
            {
                var spent = item.Attempts >= maxAttempts;
                session.Execute(item.ClientId, "UPDATE tcc_ops.run_batch_item SET status = ?, lease_owner = NULL, lease_expires_at = NULL, "
                    + "error_dependency = 'worker', error_message = 'the worker stopped before finishing this item', finished_at = ? "
                    + "WHERE {tenant} AND item_id = ? AND status IN ('leased', 'running') AND lease_expires_at <= ?",
                    spent ? "failed" : "queued", spent ? clock : null, item.ItemId, clock);
            }

            var batchIds = lapsed.Select(item => item.BatchId).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
            foreach (var batchId in batchIds)
            {
                RefreshIn(session, batchId, now);
            }

            return (IReadOnlyList<string>)batchIds;
        });
    }

    /// <inheritdoc />
    public QueueHealth QueueHealth(PyDateTime now) => database.Transact(session =>
    {
        var queued = new OpsRow(session.QueryExempt(SqlExemption.Worker, "SELECT COUNT(*) AS n, MIN(b.requested_at) AS oldest "
            + "FROM tcc_ops.run_batch_item i JOIN tcc_ops.run_batch b ON b.batch_id = i.batch_id WHERE i.status = 'queued' AND b.cancel_requested = 0")[0]);
        var live = new OpsRow(session.QueryExempt(SqlExemption.Worker, "SELECT COUNT(*) AS n, MAX(heartbeat_at) AS last "
            + "FROM tcc_ops.run_batch_item WHERE status IN ('leased', 'running') AND lease_expires_at > ?", OpsRow.Clock(session, now))[0]);
        return new QueueHealth(queued.Long("n"), queued.Instant("oldest"), live.Long("n"), live.Instant("last"));
    });

    private static string? Truncate(string? message) => message is { Length: > 1000 } ? message[..1000] : message;
}
