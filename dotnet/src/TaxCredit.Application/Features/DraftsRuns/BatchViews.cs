using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Features.DraftsRuns;

internal static class BatchViews
{
    private static readonly string[] TerminalCounts = ["succeeded", "skipped", "failed", "cancelled"];
    internal static PyDict Batch(RunBatch batch, bool replay = false)
    {
        var counts = new PyDict();
        foreach (var name in new[] { "total", "queued", "running", "succeeded", "skipped", "failed", "cancelled" })
        {
            counts.Add(name, batch.Counts.TryGetValue("items_" + name, out var count) ? count : 0L);
        }
        var done = TerminalCounts.Sum(k => FeatureValues.Integer(counts, k));
        return new PyDict().Add("batch_id", batch.BatchId).Add("kind", batch.Kind.Value()).Add("scope_kind", batch.ScopeKind.Value())
            .Add("scope_spec", batch.ScopeSpec).Add("program_code", batch.ProgramCode).Add("tax_years", batch.TaxYears.Cast<object?>().ToList())
            .Add("force", batch.Force).Add("skip_unchanged", batch.SkipUnchanged).Add("include_code_commit", batch.IncludeCodeCommit)
            .Add("refresh_once", batch.RefreshOnce).Add("status", batch.Status.Value()).Add("cancel_requested", batch.CancelRequested)
            .Add("counts", counts).Add("progress", new PyDict().Add("done", done).Add("total", counts["total"]))
            .Add("requested_by", batch.RequestedBy).Add("requested_at", Iso(batch.RequestedAt)).Add("started_at", Iso(batch.StartedAt))
            .Add("finished_at", Iso(batch.FinishedAt)).Add("idempotency_key", batch.IdempotencyKey).Add("dry_run_summary", batch.DryRunSummary)
            .Add("idempotent_replay", replay).Add("degraded", new List<object?>()).Add("cancelled_now", null).Add("requeued", null);
    }

    internal static PyDict Item(RunBatchItem item) => new PyDict().Add("item_id", item.ItemId).Add("batch_id", item.BatchId)
        .Add("seq", item.Seq).Add("client_id", item.ClientId).Add("program_code", item.ProgramCode).Add("tax_year", item.TaxYear)
        .Add("status", item.Status.Value()).Add("attempts", item.Attempts).Add("run_id", item.RunId).Add("skip_reason", item.SkipReason)
        .Add("error_dependency", item.ErrorDependency).Add("error_message", item.ErrorMessage).Add("not_before", Iso(item.NotBefore))
        .Add("started_at", Iso(item.StartedAt)).Add("finished_at", Iso(item.FinishedAt));

    internal static string? Iso(PyDateTime? value) => value?.IsoFormat().Replace("+00:00", "Z", StringComparison.Ordinal);
}
