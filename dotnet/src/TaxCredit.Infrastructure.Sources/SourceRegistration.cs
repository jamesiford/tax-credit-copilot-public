using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources;

/// <summary>Host-owned composition supplies the library, transport, credentials and lookup reader; no environment is consulted here.</summary>
public static class SourceRegistration
{
    /// <summary>Registers the deferred annual-payroll wage port; the state resolver must not depend on a wage-enabled library.</summary>
    public static IServiceCollection AddTaxCreditProgramWages(this IServiceCollection services, string path,
        Func<string, string> stateForProgram)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton<TaxCredit.Domain.Programs.IProgramWageSource>(new ProgramWageSource(path, stateForProgram));
        return services;
    }

    /// <summary>Registers one SQL source instance behind both rich Application and certified Domain contracts.</summary>
    public static IServiceCollection AddTaxCreditSqlSources(this IServiceCollection services, SourceMapping mapping,
        LookupResolver lookups, string? schema = "tcc_source", long maximumRows = 1_000_000,
        bool allowFixtureFallback = false, IFiscalRuleReader? fixtureFallback = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton(mapping);
        services.AddSingleton(lookups);
        services.AddSingleton(p => new SourceScanner(p.GetRequiredService<IAnalyticsTransport>(), mapping, schema, maximumRows));
        services.AddSingleton<PayrollProjector>();
        services.AddSingleton<IFiscalRuleReader, SqlFiscalRuleReader>();
        services.AddSingleton(p => new FiscalRuleAdapter(p.GetRequiredService<TaxCredit.Domain.Programs.RuleLibrary>(),
            p.GetRequiredService<IFiscalRuleReader>(), lookups, allowFixtureFallback: allowFixtureFallback,
            fixtureFallback: fixtureFallback));
        services.AddSingleton<IFiscalRuleSource>(p => p.GetRequiredService<FiscalRuleAdapter>());
        services.AddSingleton<SqlClientSource>();
        services.AddSingleton<IClientPayrollSource>(p => p.GetRequiredService<SqlClientSource>());
        services.AddSingleton<IPayrollSource>(p => p.GetRequiredService<IClientPayrollSource>());
        services.AddSingleton<ISourceReader>(p => p.GetRequiredService<SqlClientSource>());
        services.AddSingleton<ISourceCatalogue>(p => p.GetRequiredService<SqlClientSource>());
        services.AddSingleton<ISourceFingerprintReader>(p => new SourceFingerprintReader(p.GetRequiredService<SourceScanner>()));
        return services;
    }

    /// <summary>CSV registration never resolves any analytics service. HoldsClientRules remains false.</summary>
    public static IServiceCollection AddTaxCreditCsvSources(this IServiceCollection services, string path, long? fixtureAccountId)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton(p => new FiscalRuleAdapter(p.GetRequiredService<TaxCredit.Domain.Programs.RuleLibrary>(),
            new NoFixtureFiscalReader(), new LookupResolver(), holdsClientRules: false));
        services.AddSingleton<IFiscalRuleSource>(p => p.GetRequiredService<FiscalRuleAdapter>());
        services.AddSingleton(p => new CsvClientSource(path, fixtureAccountId, p.GetRequiredService<FiscalRuleAdapter>()));
        services.AddSingleton<IClientPayrollSource>(p => p.GetRequiredService<CsvClientSource>());
        services.AddSingleton<IPayrollSource>(p => p.GetRequiredService<IClientPayrollSource>());
        services.AddSingleton<ISourceReader>(p => p.GetRequiredService<CsvClientSource>());
        services.AddSingleton<ISourceCatalogue>(p => p.GetRequiredService<CsvClientSource>());
        return services;
    }

    private sealed class NoFixtureFiscalReader : IFiscalRuleReader
    {
        public bool IsConfigured => false;
        public IReadOnlyList<FiscalRule>? Read(long accountId) => null;
    }
}
