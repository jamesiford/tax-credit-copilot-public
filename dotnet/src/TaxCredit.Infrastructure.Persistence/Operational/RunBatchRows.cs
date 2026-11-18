using System.Globalization;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

internal static class RunBatchRows
{
    internal const string BatchTable = "{ops.run_batch}";
    internal const string ItemTable = "{ops.run_batch_item}";
    internal static readonly string[] BatchColumns =
    [
        "batch_id", "kind", "scope_kind", "scope_spec", "program_code", "tax_years", "force_run", "include_code_commit",
        "refresh_once", "status", "cancel_requested", "items_total", "items_queued", "items_running", "items_succeeded",
        "items_skipped", "items_failed", "items_cancelled", "requested_by", "requested_at", "started_at", "finished_at",
        "idempotency_key", "dry_run_summary",
    ];
    internal static readonly string[] ItemColumns =
    [
        "item_id", "batch_id", "seq", "client_id", "program_code", "tax_year", "status", "attempts", "lease_owner",
        "lease_expires_at", "heartbeat_at", "not_before", "run_id", "skip_reason", "error_dependency", "error_message", "started_at", "finished_at",
    ];
    internal static readonly string[] CounterColumns =
    [
        "items_total", "items_queued", "items_running", "items_succeeded", "items_skipped", "items_failed", "items_cancelled",
    ];

    internal static string BatchSelect => "SELECT " + string.Join(", ", BatchColumns) + " FROM " + BatchTable;
    internal static string ItemSelect => "SELECT " + string.Join(", ", ItemColumns) + " FROM " + ItemTable;

    internal static object?[] BatchValues(SqlSession session, RunBatch batch, IReadOnlyDictionary<string, long> counts)
    {
        var spec = new PyDict();
        foreach (var pair in batch.ScopeSpec)
        {
            spec.Add(pair.Key, pair.Value);
        }

        if (batch.SkipUnchanged)
        {
            spec.Set("skip_unchanged", true);
        }

        return
        [
            batch.BatchId, batch.Kind.Value(), batch.ScopeKind.Value(), PyJson.Dumps(spec, sortKeys: true, compact: false), batch.ProgramCode,
            batch.TaxYears.Count == 0 ? null : PyJson.Dumps(batch.TaxYears.Select(y => (object?)y).ToList()), batch.Force, batch.IncludeCodeCommit, batch.RefreshOnce,
            batch.Status.Value(), batch.CancelRequested, counts["items_total"], counts["items_queued"], counts["items_running"],
            counts["items_succeeded"], counts["items_skipped"], counts["items_failed"], counts["items_cancelled"],
            batch.RequestedBy, OpsRow.Clock(session, batch.RequestedAt), OpsRow.Clock(session, batch.StartedAt),
            OpsRow.Clock(session, batch.FinishedAt), batch.IdempotencyKey, PyJson.Dumps(batch.DryRunSummary),
        ];
    }

    internal static object?[] ItemValues(SqlSession session, RunBatchItem item) =>
    [
        item.ItemId, item.BatchId, item.Seq, item.ClientId, item.ProgramCode, item.TaxYear, item.Status.Value(), item.Attempts,
        item.LeaseOwner, OpsRow.Clock(session, item.LeaseExpiresAt), OpsRow.Clock(session, item.HeartbeatAt), OpsRow.Clock(session, item.NotBefore), item.RunId, item.SkipReason,
        item.ErrorDependency, item.ErrorMessage, OpsRow.Clock(session, item.StartedAt), OpsRow.Clock(session, item.FinishedAt),
    ];

    internal static RunBatch Batch(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        var spec = r.Document("scope_spec") ?? new PyDict();
        return new RunBatch
        {
            BatchId = r.Required("batch_id"),
            Kind = RunEnumExtensions.BatchKindFromValue(r.Required("kind")),
            ScopeKind = RunEnumExtensions.ScopeKindFromValue(r.Required("scope_kind")),
            ScopeSpec = spec,
            ProgramCode = r.Text("program_code"),
            TaxYears = r.Text("tax_years") is { } years
                ? ((List<object?>)PyJson.Loads(years)!).Select(value => Convert.ToInt64(value, CultureInfo.InvariantCulture)).ToArray() : [],
            Force = r.Bool("force_run"),
            IncludeCodeCommit = r.Bool("include_code_commit"),
            RefreshOnce = r.Bool("refresh_once"),
            SkipUnchanged = spec.TryGetValue("skip_unchanged", out var skip) && skip is true,
            Status = RunEnumExtensions.BatchStatusFromValue(r.Required("status")),
            CancelRequested = r.Bool("cancel_requested"),
            RequestedBy = r.Required("requested_by"),
            RequestedAt = r.Instant("requested_at")!.Value,
            StartedAt = r.Instant("started_at"),
            FinishedAt = r.Instant("finished_at"),
            IdempotencyKey = r.Text("idempotency_key"),
            DryRunSummary = r.Document("dry_run_summary") ?? new PyDict(),
            Counts = CountsDocument(CounterColumns.ToDictionary(column => column, r.Long, StringComparer.Ordinal)),
        };
    }

    internal static RunBatchItem Item(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new RunBatchItem
        {
            ItemId = r.Required("item_id"),
            BatchId = r.Required("batch_id"),
            ClientId = r.Long("client_id"),
            Seq = r.Long("seq"),
            ProgramCode = r.Text("program_code"),
            TaxYear = r.OptionalLong("tax_year"),
            Status = RunEnumExtensions.ItemStatusFromValue(r.Required("status")),
            Attempts = r.Long("attempts"),
            LeaseOwner = r.Text("lease_owner"),
            LeaseExpiresAt = r.Instant("lease_expires_at"),
            HeartbeatAt = r.Instant("heartbeat_at"),
            NotBefore = r.Instant("not_before"),
            RunId = r.Text("run_id"),
            SkipReason = r.Text("skip_reason"),
            ErrorDependency = r.Text("error_dependency"),
            ErrorMessage = r.Text("error_message"),
            StartedAt = r.Instant("started_at"),
            FinishedAt = r.Instant("finished_at"),
        };
    }

    internal static Dictionary<string, long> Counters(IReadOnlyDictionary<string, long> statuses)
    {
        var counts = CounterColumns.ToDictionary(key => key, _ => 0L, StringComparer.Ordinal);
        foreach (var pair in statuses)
        {
            var counter = pair.Key switch
            {
                "queued" => "items_queued",
                "leased" or "running" => "items_running",
                "succeeded" => "items_succeeded",
                "skipped_unchanged" or "skipped_no_payroll" => "items_skipped",
                "failed" => "items_failed",
                "cancelled" => "items_cancelled",
                _ => throw new InvalidDataException("Unknown queue item status."),
            };
            counts[counter] += pair.Value;
            counts["items_total"] += pair.Value;
        }

        return counts;
    }

    internal static PyDict CountsDocument(IReadOnlyDictionary<string, long> counts)
    {
        var document = new PyDict();
        foreach (var pair in counts)
        {
            document.Add(pair.Key, pair.Value);
        }

        return document;
    }

}
