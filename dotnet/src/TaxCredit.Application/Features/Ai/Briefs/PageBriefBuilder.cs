using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>Missing scope refuses before asking any application collaborator to read.</summary>
public sealed class PageBriefBuilder(IPageFactSource facts, IPageScope scope)
{
    /// <summary>Builds only from trusted page payloads, never from reader-provided numbers.</summary>
    public async ValueTask<PageBrief> BuildAsync(SummaryQuery query, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(query);
        if (query.Page == "portfolio")
        {
            return PortfolioBrief.Build(await facts.PortfolioAsync(cancellationToken).ConfigureAwait(false));
        }
        if (query.ClientId is null) { throw new AiFactException($"a {query.Page} summary needs client_id"); }
        var name = scope.ClientName(query.ClientId.Value);
        if (query.Page == "client")
        {
            return ClientBrief.Build(await facts.ClientAsync(query, cancellationToken).ConfigureAwait(false),
                name, scope.PlaceholderYears(query.State.ToUpperInvariant()));
        }
        if (query.TaxYear is null) { throw new AiFactException($"a {query.Page} summary needs tax_year"); }
        if (query.Page == "unit" && string.IsNullOrEmpty(query.WorksiteId)) { throw new AiFactException("a unit summary needs worksite_id"); }
        if (query.Page == "employee" && string.IsNullOrEmpty(query.RecordToken)) { throw new AiFactException("an employee summary needs record_token"); }
        var placeholder = scope.PlaceholderYears(query.State.ToUpperInvariant()).Contains(query.TaxYear.Value);
        return query.Page switch
        {
            "unit" => UnitBrief.Build(await facts.UnitAsync(query, cancellationToken).ConfigureAwait(false), name, query.Month, placeholder),
            "employee" => EmployeeBrief.Build(await facts.EmployeeAsync(query, cancellationToken).ConfigureAwait(false), placeholder),
            _ => throw new AiFactException("unknown summary page")
        };
    }
}
