using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Portfolio;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>Summary pages dispatch the same application queries as their interactive page.</summary>
public sealed class CanonicalPageReads(string page, IMediator mediator) : IAiPageCollaborator
{
    /// <inheritdoc />
    public string Page => page;

    /// <inheritdoc />
    public async ValueTask<JsonObject> ReadAsync(SummaryQuery query, CancellationToken cancellationToken)
    {
        IRequest<object> request = Page switch
        {
            "portfolio" => Portfolio(),
            "unit" => new StoredReadQuery("unit", Arguments(query)),
            "employee" => new StoredReadQuery("drill", Arguments(query)),
            _ => throw new AiFactException("Unknown summary page."),
        };
        return Object(await mediator.Send(request, cancellationToken).ConfigureAwait(false));
    }

    internal static GetPortfolio Portfolio() =>
        new(null, null, null, null, null, null, "priority", "asc", 200, 0);

    internal static JsonObject Object(object value) =>
        JsonSerializer.SerializeToNode(FeatureValues.Wire(value))!.AsObject();

    private static ReadArguments Arguments(SummaryQuery query) => new(new Dictionary<string, string?>(StringComparer.Ordinal)
    {
        ["client_id"] = query.ClientId?.ToString(CultureInfo.InvariantCulture),
        ["account_id"] = query.ClientId?.ToString(CultureInfo.InvariantCulture),
        ["year"] = query.TaxYear?.ToString(CultureInfo.InvariantCulture),
        ["tax_year"] = query.TaxYear?.ToString(CultureInfo.InvariantCulture),
        ["unit_id"] = query.WorksiteId,
        ["record_token"] = query.RecordToken,
        ["month"] = query.Month?.ToString(CultureInfo.InvariantCulture),
        ["state"] = query.State,
        ["method"] = query.Method,
    });
}
