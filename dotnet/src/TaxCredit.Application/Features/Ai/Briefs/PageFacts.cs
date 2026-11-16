using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>Page owners supply their existing application payload, not a second calculation or an HTTP self-call.</summary>
public interface IPageFactSource
{
    /// <summary>Portfolio priority page, unfiltered by tax year, limit 200 and offset zero.</summary>
    ValueTask<JsonObject> PortfolioAsync(CancellationToken cancellationToken);

    /// <summary>Client unit page, all years, requested method, limit 5000 and offset zero.</summary>
    ValueTask<JsonObject> ClientAsync(SummaryQuery query, CancellationToken cancellationToken);

    /// <summary>Unit detail with unfiltered cohorts, the requested month, floors and canonical hours lever.</summary>
    ValueTask<JsonObject> UnitAsync(SummaryQuery query, CancellationToken cancellationToken);

    /// <summary>Employee drill with both methods, consumed periods and allocation.</summary>
    ValueTask<JsonObject> EmployeeAsync(SummaryQuery query, CancellationToken cancellationToken);
}

/// <summary>Metadata is resolved independently of the payroll population.</summary>
public interface IPageScope
{
    /// <summary>The source book's display name, or an explicit account label.</summary>
    string ClientName(long clientId);

    /// <summary>Authored placeholder years of the selected state/program.</summary>
    IReadOnlyList<int> PlaceholderYears(string state);
}

/// <summary>The immutable facts a summary may describe.</summary>
public sealed record PageBrief(string Page, string Subject, string Headline,
    IReadOnlyList<string> Facts, IReadOnlyList<string> Caveats, JsonObject Data);
