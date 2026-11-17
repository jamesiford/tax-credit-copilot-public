using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Features.Framework;

/// <summary>A liveness read independent of payroll, credentials or model availability.</summary>
public sealed record GetHealthQuery : IQuery<IReadOnlyDictionary<string, object?>>;

/// <summary>Returns the startup status without running dependencies on the request path.</summary>
public sealed class GetHealthHandler(IHostStatus status) : IRequestHandler<GetHealthQuery, IReadOnlyDictionary<string, object?>>
{
    /// <inheritdoc />
    public ValueTask<IReadOnlyDictionary<string, object?>> Handle(GetHealthQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(status.Health);
}
