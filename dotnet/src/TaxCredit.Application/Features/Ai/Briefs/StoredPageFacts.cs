using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>Missing sibling projections are explicit integration dependencies, not empty calculated answers.</summary>
public interface IAiPageCollaborator
{
    /// <summary>Names the canonical projection owned by this binding: portfolio, unit or employee.</summary>
    string Page { get; }

    /// <summary>Supplies the same shaped payload as the named page's inward application read.</summary>
    ValueTask<JsonObject> ReadAsync(SummaryQuery query, CancellationToken cancellationToken);
}

/// <summary>Uses the W1 stored client grid directly; other page owners provide their canonical projection.</summary>
public sealed class StoredPageFacts(IGoldReadPort gold, ClientRunResolver resolver,
    IEnumerable<IAiPageCollaborator> collaborators) : IPageFactSource
{
    /// <inheritdoc />
    public ValueTask<JsonObject> PortfolioAsync(CancellationToken cancellationToken) =>
        CollaboratorAsync(new("portfolio"), cancellationToken);

    /// <inheritdoc />
    public ValueTask<JsonObject> ClientAsync(SummaryQuery query, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var client = query.ClientId ?? throw new AiFactException("a client summary needs client_id");
        var page = gold.UnitPage(client, query.Method, programCode: Program(query), limit: 5000);
        return ValueTask.FromResult(JsonSerializer.SerializeToNode(page)!.AsObject());
    }

    /// <inheritdoc />
    public ValueTask<JsonObject> UnitAsync(SummaryQuery query, CancellationToken cancellationToken) =>
        CollaboratorAsync(query, cancellationToken);

    /// <inheritdoc />
    public ValueTask<JsonObject> EmployeeAsync(SummaryQuery query, CancellationToken cancellationToken) =>
        CollaboratorAsync(query, cancellationToken);

    private string? Program(SummaryQuery query)
    {
        var run = gold.LatestRun(query.ClientId!.Value);
        if (run is null) { return null; }
        var year = query.TaxYear ?? Convert.ToInt32(run["tax_year"], CultureInfo.InvariantCulture);
        return resolver.ResolveStatute(query.ClientId, query.State, year, requireProgram: true).ProgramCode;
    }

    private ValueTask<JsonObject> CollaboratorAsync(SummaryQuery query, CancellationToken cancellationToken)
    {
        var source = collaborators.SingleOrDefault(c => c.Page == query.Page);
        if (source is null)
        {
            var dependency = query.Page == "portfolio" ? "ClaimsArtifactsRules.PortfolioPage" : $"ReadsCalc.{query.Page}Page";
            throw new AiFactException($"The figures for this summary are unavailable: {dependency} is not bound.", dependency);
        }
        return source.ReadAsync(query, cancellationToken);
    }
}
