using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>A dry run is a query and cannot accidentally enqueue work.</summary>
public sealed record PreviewBatchQuery(JsonElement? Body) : IQuery<object>;

internal sealed class PreviewBatchHandler(BatchPlanner planner) : IRequestHandler<PreviewBatchQuery, object>
{
    public async ValueTask<object> Handle(PreviewBatchQuery request, CancellationToken cancellationToken)
    {
        var plan = await planner.Plan(BatchRequest.Parse(FeatureValues.Document(request.Body)), cancellationToken).ConfigureAwait(false);
        return new PyDict().Add("dry_run", true).Add("preview", plan.Summary);
    }
}

/// <summary>Accepts durable work; the ordinary Worker and drain execute the existing publication protocol.</summary>
public sealed record StartBatchCommand(JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class StartBatchHandler(BatchPlanner planner, IRunBatchRepository repository, BatchAccess access,
    IClock clock, IIdSource ids, IApiPrincipalAccessor principals) : IRequestHandler<StartBatchCommand, object>
{
    public async ValueTask<object> Handle(StartBatchCommand command, CancellationToken cancellationToken)
    {
        var body = FeatureValues.Document(command.Body);
        var request = BatchRequest.Parse(body);
        var actor = FeatureValues.Actor(principals, body);
        if (!string.IsNullOrEmpty(request.IdempotencyKey) && repository.FindByKey(request.IdempotencyKey, actor) is { } earlier)
        {
            await access.RequireAll(earlier.BatchId, cancellationToken).ConfigureAwait(false);
            return BatchViews.Batch(earlier, replay: true);
        }
        var plan = await planner.Plan(request, cancellationToken).ConfigureAwait(false);
        var count = plan.Pairs.Count * Math.Max(1, request.TaxYears.Count);
        CheckSize(request, count);
        var spec = BatchPlanner.Spec(request, plan);
        if (repository.FindOpenIdentical(request.Kind.Value(), PyJson.Dumps(spec, sortKeys: true, compact: false), actor) is { } twin)
        {
            return BatchViews.Batch(twin, replay: true);
        }
        var summary = new PyDict();
        foreach (var pair in plan.Summary.Where(p => p.Key != "first_items")) { summary.Add(pair.Key, pair.Value); }
        var batch = new RunBatch
        {
            BatchId = ids.NewId().ToString("N"),
            Kind = request.Kind,
            ScopeKind = request.Scope,
            ScopeSpec = spec,
            RequestedBy = actor,
            RequestedAt = FeatureValues.Now(clock),
            ProgramCode = request.ProgramCode,
            TaxYears = request.TaxYears,
            Force = request.Force,
            SkipUnchanged = request.SkipUnchanged,
            IncludeCodeCommit = request.IncludeCodeCommit,
            RefreshOnce = request.RefreshOnce,
            IdempotencyKey = request.IdempotencyKey,
            DryRunSummary = summary,
        };
        var items = new List<RunBatchItem>();
        var years = request.TaxYears.Count > 0 ? request.TaxYears.Select(y => (long?)y).ToArray() : [null];
        foreach (var pair in plan.Pairs)
        {
            foreach (var year in years)
            {
                items.Add(new RunBatchItem
                {
                    ItemId = ids.NewId().ToString("N"),
                    BatchId = batch.BatchId,
                    Seq = items.Count,
                    ClientId = pair.Client,
                    ProgramCode = pair.Program,
                    TaxYear = year
                });
            }
        }
        var accepted = repository.Create(batch, items);
        return BatchViews.Batch(accepted, replay: accepted.BatchId != batch.BatchId);
    }

    private void CheckSize(BatchRequest request, int count)
    {
        if (count > planner.MaxItems && !(request.Scope == ScopeKind.All && request.OverrideSizeLimit))
        {
            throw BatchRequest.Refuse("batch_too_large", $"The request selects {count} items, over the limit of {planner.MaxItems}.",
                request.Scope == ScopeKind.All ? "Narrow the selection, or set override_size_limit to run everything." : "Narrow the selection, or raise RUN_BATCH_MAX_ITEMS.", 413);
        }
        if (count > planner.ConfirmAbove && request.ConfirmItems != count)
        {
            throw BatchRequest.Refuse("confirmation_required", $"This starts {count} items, above {planner.ConfirmAbove}, so it needs confirmation.",
                $"Preview it, then send confirm_items={count} to start it.", 409);
        }
    }
}
