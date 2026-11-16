using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

/// <summary>Registers scoped view assembly without owning HTTP or other feature groups.</summary>
public static class PortfolioRegistration
{
    /// <summary>Uses the host's source, rule, fiscal, designation and Gold ports; reference data is an outer binding.</summary>
    public static IServiceCollection AddReadsCalcPortfolio(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.TryAddScoped<ReadsPortfolioService>();
        services.TryAddScoped<ReadsDiscoveryService>();
        services.TryAddScoped<ReadsStoredPortfolioBriefs>();
        services.TryAddScoped<ReadsUnitTrendService>();
        return services;
    }
}

/// <summary>Facts absent from the pay-period feed must not be inferred from first appearance.</summary>
public interface IPortfolioReferenceData
{
    /// <summary>Genuine hire dates in the reference payroll source, not a client's pay-period first appearances.</summary>
    long CountFederalNewHires(long taxYear);

    /// <summary>Legacy display metadata, with null meaning the registry holds no site.</summary>
    PortfolioWorksite? Worksite(string unitId);
}

/// <summary>Display metadata only: it never changes eligibility or credit.</summary>
/// <param name="Name">The human-readable worksite name.</param>
/// <param name="County">Registry county, used only when payroll has none.</param>
/// <param name="City">Registry city.</param>
public sealed record PortfolioWorksite(string Name, string County = "", string City = "");
