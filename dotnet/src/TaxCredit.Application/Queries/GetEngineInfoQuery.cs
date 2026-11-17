using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Queries;

/// <summary>Reports which engine build is serving; the smallest end-to-end use case through the pipeline.</summary>
public sealed record GetEngineInfoQuery : IQuery<EngineInfo>;

/// <summary>The engine identity.</summary>
/// <param name="Name">Product name.</param>
/// <param name="Oracle">What the engine is certified against.</param>
public sealed record EngineInfo(string Name, string Oracle);

/// <summary>Handles <see cref="GetEngineInfoQuery"/>.</summary>
public sealed class GetEngineInfoHandler : IRequestHandler<GetEngineInfoQuery, EngineInfo>
{
    /// <inheritdoc />
    public ValueTask<EngineInfo> Handle(GetEngineInfoQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(new EngineInfo("TaxCredit .NET spike", "CPython 3.14 reference engine"));
}
