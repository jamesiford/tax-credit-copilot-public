using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Features.Framework;

/// <summary>A read of settled startup checks, not another dependency probe.</summary>
public sealed record GetReadinessQuery : IQuery<IReadOnlyDictionary<string, object?>>;

/// <summary>Reports the checks known to the host; a missing check is not silently green.</summary>
public sealed class GetReadinessHandler(IHostStatus status) : IRequestHandler<GetReadinessQuery, IReadOnlyDictionary<string, object?>>
{
    /// <inheritdoc />
    public ValueTask<IReadOnlyDictionary<string, object?>> Handle(GetReadinessQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(status.Readiness);
}
