using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Cancellation leaves leased/running work to its existing publication owner.</summary>
public sealed record CancelBatchCommand(string BatchId) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class CancelBatchHandler(BatchAccess access, IRunBatchRepository repository, IClock clock) : IRequestHandler<CancelBatchCommand, object>
{
    public async ValueTask<object> Handle(CancelBatchCommand request, CancellationToken cancellationToken)
    {
        await access.RequireAll(request.BatchId, cancellationToken).ConfigureAwait(false);
        var count = repository.Cancel(request.BatchId, FeatureValues.Now(clock));
        return BatchViews.Batch(repository.Get(request.BatchId)!).Set("cancelled_now", count);
    }
}

/// <summary>Retries failed items only; cancelled and successful work are not repeated.</summary>
public sealed record RetryBatchCommand(string BatchId) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class RetryBatchHandler(BatchAccess access, IRunBatchRepository repository, IClock clock) : IRequestHandler<RetryBatchCommand, object>
{
    public async ValueTask<object> Handle(RetryBatchCommand request, CancellationToken cancellationToken)
    {
        await access.RequireAll(request.BatchId, cancellationToken).ConfigureAwait(false);
        var count = repository.RetryFailed(request.BatchId, FeatureValues.Now(clock));
        return BatchViews.Batch(repository.Get(request.BatchId)!).Set("requeued", count);
    }
}
