using System.Numerics;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Working material requires writer entitlement, but no invented author identity.</summary>
public sealed record ListDraftsQuery(string? Status, int Limit, BigInteger Offset) : IQuery<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class ListDraftsHandler(IProgramDraftRepository repository) : IRequestHandler<ListDraftsQuery, object>
{
    public ValueTask<object> Handle(ListDraftsQuery request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var (items, total) = repository.ListPage(request.Status, request.Limit, request.Offset);
        return ValueTask.FromResult<object>(new PyDict().Add("items", items.Select(d => (object?)DraftViews.Summary(d)).ToList())
            .Add("total", total).Add("limit", (long)request.Limit).Add("offset", request.Offset));
    }
}

/// <summary>Reads saved documents, not a reconstruction from an export.</summary>
public sealed record GetDraftQuery(string DraftId) : IQuery<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class GetDraftHandler(DraftLifecycle lifecycle, IProgramDraftRepository repository) : IRequestHandler<GetDraftQuery, object>
{
    public ValueTask<object> Handle(GetDraftQuery request, CancellationToken cancellationToken) => ValueTask.FromResult<object>(
        DraftViews.Detail(lifecycle.Load(request.DraftId)).Set("events", repository.Events(request.DraftId).Select(e => (object?)DraftViews.Event(e)).ToList()));
}
