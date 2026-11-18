using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Queue completion, accepted Gold, manifests and assessed claims share the runner's database transaction.</summary>
public sealed class RunPublication(PersistenceDatabase database, IRunBatchRepository queue, IRunManifestRepository manifests) : IRunPublication
{
    /// <inheritdoc />
    public string Identity(RunBatchItem item, string owner, PyDateTime now, Func<string> newId)
    {
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(newId);
        return database.Transact(session =>
        {
            Own(item, owner, now);
            var rows = session.Query(item.ClientId, "SELECT run_id FROM tcc_ops.run_work_identity WHERE {tenant} AND item_id = ?", item.ItemId);
            if (rows.Count > 0) { return (string)rows.Single()["run_id"]!; }
            var runId = newId();
            session.Insert(item.ClientId, "tcc_ops.run_work_identity", ["client_id", "item_id", "run_id"], [[item.ClientId, item.ItemId, runId]]);
            return runId;
        });
    }

    /// <inheritdoc />
    public void Publish(RunBatchItem item, string owner, string? runId, Func<ItemResult> calculate,
        Func<PyDateTime> now, CancellationToken cancellationToken, int leaseSeconds = 600)
    {
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(calculate);
        ArgumentNullException.ThrowIfNull(now);
        using var span = RunSpans.Start("publish");
        try
        {
            database.Transact(session =>
            {
                cancellationToken.ThrowIfCancellationRequested();
                // This writes the leased row in the same serializable transaction as the publication.
                // A competing native writer must conflict or wait, never publish under a stale read.
                if (!queue.Heartbeat(item.ClientId, item.ItemId, owner, leaseSeconds, now())) { throw new RunLeaseLost(); }
                var accepted = runId is null ? null : Accepted(item.ClientId, runId);
                var result = accepted is null ? calculate() : new ItemResult
                {
                    Status = ItemStatus.Succeeded,
                    RunId = accepted.RunId,
                    TaxYear = accepted.TaxYear,
                };
                cancellationToken.ThrowIfCancellationRequested();
                Own(item, owner, now());
                if (result.RunId is { } resultId && Accepted(item.ClientId, resultId) is { } manifest)
                {
                    session.Execute(item.ClientId, "UPDATE tcc_ops.run_batch_item SET program_code = ? WHERE {tenant} AND item_id = ? AND lease_owner = ?",
                        manifest.ProgramCode, item.ItemId, owner);
                }
                if (!queue.Finish(item.ClientId, item.ItemId, owner, now(), result, item.BatchId)) { throw new RunLeaseLost(); }
                return true;
            });
        }
        catch (AmbiguousCommitException)
        {
            var persisted = queue.GetItem(item.ClientId, item.ItemId);
            if (persisted is null || !RunStateMachine.TerminalItems.Contains(persisted.Status)) { throw; }
            if (persisted.RunId is { } accepted && Accepted(item.ClientId, accepted) is null) { throw; }
        }
    }

    private RunManifest? Accepted(long clientId, string runId)
    {
        var manifest = manifests.Get(runId);
        return manifest?.ClientId == clientId && manifest.RunStatus is "success" or "superseded" ? manifest : null;
    }

    private void Own(RunBatchItem item, string owner, PyDateTime now)
    {
        var current = queue.GetItem(item.ClientId, item.ItemId);
        if (current is null || current.LeaseOwner != owner || current.LeaseExpiresAt is null
            || string.CompareOrdinal(OpsRow.Clock(current.LeaseExpiresAt.Value), OpsRow.Clock(now)) <= 0
            || !RunStateMachine.ActiveItems.Contains(current.Status))
        {
            throw new RunLeaseLost();
        }
    }
}
