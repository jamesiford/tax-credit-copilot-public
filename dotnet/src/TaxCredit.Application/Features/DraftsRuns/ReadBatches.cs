using System.Globalization;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Reads one authorized batch and its queue liveness.</summary>
public sealed record GetBatchQuery(string BatchId) : IQuery<object>;

internal sealed class GetBatchHandler(BatchAccess access, IRunBatchRepository repository, IClock clock,
    IRuntimeConfiguration configuration) : IRequestHandler<GetBatchQuery, object>
{
    public async ValueTask<object> Handle(GetBatchQuery request, CancellationToken cancellationToken)
    {
        var (batch, _) = await access.Read(request.BatchId, cancellationToken).ConfigureAwait(false);
        var view = BatchViews.Batch(batch);
        var health = repository.QueueHealth(FeatureValues.Now(clock));
        var threshold = int.TryParse(configuration.Get("RUN_STALE_WORKER_SECONDS"), CultureInfo.InvariantCulture, out var seconds) ? seconds : 60;
        if (health.Queued > 0 && health.LiveLeases == 0 && health.OldestQueuedAt is { } oldest
            && (clock.UtcNow - DateTimeOffset.Parse(oldest.IsoFormat(), CultureInfo.InvariantCulture)).TotalSeconds >= threshold)
        {
            view.Set("degraded", new List<object?> { new PyDict().Add("dependency", "run_worker")
                .Add("impact", "queued runs are not progressing").Add("remedy", "Start TaxCredit.Worker with the same durable store configuration.") });
        }
        return view;
    }
}

/// <summary>Pages after authorization and status filtering, retaining honest visible totals.</summary>
public sealed record ListBatchesQuery(int Limit = 25, long Offset = 0, string? Status = null) : IQuery<object>;

internal sealed class ListBatchesHandler(BatchAccess access, IRunBatchRepository repository) : IRequestHandler<ListBatchesQuery, object>
{
    public async ValueTask<object> Handle(ListBatchesQuery request, CancellationToken cancellationToken)
    {
        var visible = new List<object?>();
        var start = 0;
        while (true)
        {
            var (batches, total) = repository.ListBatches(200, start);
            foreach (var batch in batches)
            {
                try
                {
                    var (mine, _) = await access.Read(batch.BatchId, cancellationToken).ConfigureAwait(false);
                    if (request.Status is null || mine.Status.Value() == request.Status) { visible.Add(BatchViews.Batch(mine)); }
                }
                catch (DraftsRunsRefusalException refusal) when (refusal.Status == 404) { }
            }
            start += batches.Count;
            if (batches.Count == 0 || start >= total) { break; }
        }
        return Page(visible.Skip((int)Math.Min(request.Offset, int.MaxValue)).Take(request.Limit).ToList(), visible.Count, request.Limit, request.Offset);
    }

    internal static PyDict Page(List<object?> items, long total, int limit, long offset) =>
        new PyDict().Add("items", items).Add("total", total).Add("limit", (long)limit).Add("offset", offset);
}

/// <summary>Item filters narrow only the visible page, not another client's counters.</summary>
public sealed record ListBatchItemsQuery(string BatchId, string? Status = null, int Limit = 50, long Offset = 0) : IQuery<object>;

internal sealed class ListBatchItemsHandler(BatchAccess access) : IRequestHandler<ListBatchItemsQuery, object>
{
    public async ValueTask<object> Handle(ListBatchItemsQuery request, CancellationToken cancellationToken)
    {
        var (_, items) = await access.Read(request.BatchId, cancellationToken).ConfigureAwait(false);
        var wanted = items.Where(i => request.Status is null || i.Status.Value() == request.Status).ToArray();
        return ListBatchesHandler.Page(wanted.Skip((int)Math.Min(request.Offset, int.MaxValue)).Take(request.Limit)
            .Select(i => (object?)BatchViews.Item(i)).ToList(), wanted.Length, request.Limit, request.Offset);
    }
}
