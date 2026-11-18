using Azure.Identity;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Persistence;
using TaxCredit.Infrastructure.Sources;
using TaxCredit.Infrastructure.Sources.Cache;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.ServiceDefaults.Hosting;

internal static class RuntimeSourceRegistration
{
    internal static void AddRuntimeSources(this IServiceCollection services, RuntimeConfiguration settings, RuntimePaths paths)
    {
        var mapping = SourceMapping.Load();
        services.AddSingleton(mapping);
        services.AddSingleton<SeedAnalytics>();
        services.AddScoped<ISourceLookupReader, PersistenceLookups>();
        services.AddTaxCreditSqlSources(mapping, new LookupResolver());
        services.AddTaxCreditCsvSources(paths.Csv, 1001);
        foreach (var type in new[] { typeof(LookupResolver), typeof(IAnalyticsTransport), typeof(SourceScanner),
            typeof(PayrollProjector), typeof(IFiscalRuleReader), typeof(FiscalRuleAdapter), typeof(IFiscalRuleSource),
            typeof(CsvClientSource), typeof(SqlClientSource), typeof(IClientPayrollSource), typeof(IPayrollSource),
            typeof(ISourceReader), typeof(ISourceCatalogue), typeof(ISourceFingerprintReader) })
        {
            services.RemoveAll(type);
        }
        services.AddScoped(p => Lookups(p, settings, paths));
        services.AddScoped<IAnalyticsTransport>(p => settings.Get("TCC_CONTRACT_HOOKS") == "1"
            ? p.GetRequiredService<SeedAnalytics>().Transport : new SqlAnalyticsTransport(new AnalyticsConnectionFactory(
                new AnalyticsConnectionOptions(settings.Get("SOURCE_SQL_SERVER") ?? "", settings.Get("SOURCE_SQL_DATABASE") ?? ""),
                new EntraAnalyticsTokenProvider(p.GetRequiredService<DefaultAzureCredential>()), p.GetRequiredService<TimeProvider>())));
        var limits = SourceLimits.From(settings);
        services.AddSingleton(limits);
        services.AddScoped(p => new SourceScanner(p.GetRequiredService<IAnalyticsTransport>(), mapping,
            settings.Get("SOURCE_SCHEMA") ?? "tcc_source", limits.MaxAccountRows));
        services.AddScoped<PayrollProjector>();
        services.AddScoped<IFiscalRuleReader, SqlFiscalRuleReader>();
        services.AddScoped(p => new FiscalRuleAdapter(p.GetRequiredService<RuleLibrary>(),
            IsCsv(settings) ? new NoSourceFiscal() : p.GetRequiredService<IFiscalRuleReader>(),
            p.GetRequiredService<LookupResolver>(), holdsClientRules: !IsCsv(settings)));
        services.AddScoped<IFiscalRuleSource>(p => p.GetRequiredService<FiscalRuleAdapter>());
        services.AddScoped(p => new CsvClientSource(settings.Get("PAYROLL_PATH") ?? paths.Csv, 1001, p.GetRequiredService<FiscalRuleAdapter>()));
        services.AddSingleton(p => new FootprintGuard(settings, p.GetRequiredService<TimeProvider>()));
        var cacheOptions = ProjectionCacheOptions.From(settings);
        services.AddSingleton(cacheOptions);
        services.RemoveAll<ClientProjectionCache>();
        if (cacheOptions.Enabled)
        {
            services.AddSingleton(p => new ClientProjectionCache(cacheOptions, p.GetRequiredService<TimeProvider>()));
        }
        services.AddScoped(p => new SqlClientSource(p.GetRequiredService<SourceScanner>(), p.GetRequiredService<PayrollProjector>(),
            p.GetRequiredService<FiscalRuleAdapter>(), p.GetRequiredService<FootprintGuard>(), p.GetRequiredService<SourceLimits>(),
            p.GetService<ClientProjectionCache>()));
        services.AddScoped(p => new ScopedPayrollMemo(p.GetRequiredService<IClientPayrollSource>(),
            IsCsv(settings) || !cacheOptions.Enabled ? null : p.GetRequiredService<SqlClientSource>()));
        services.AddScoped<IPayrollFreshness>(p => IsCsv(settings) ? NoPayrollFreshness.Instance : p.GetRequiredService<ScopedPayrollMemo>());
        if (cacheOptions.Enabled)
        {
            services.RemoveAll<IClientCalculationRunner>();
            services.AddTransient<IClientCalculationRunner>(p => new FreshSourceRunner(
                ActivatorUtilities.CreateInstance<PersistedClientCalculation>(p), p.GetRequiredService<IPayrollFreshness>()));
        }
        services.AddScoped<IClientPayrollSource>(p => IsCsv(settings) ? p.GetRequiredService<CsvClientSource>() : p.GetRequiredService<SqlClientSource>());
        services.AddScoped<IPayrollSource>(p => p.GetRequiredService<ScopedPayrollMemo>());
        services.AddScoped<ISourceReader>(p => (ISourceReader)p.GetRequiredService<IClientPayrollSource>());
        services.AddScoped<ISourceCatalogue>(p => (ISourceCatalogue)p.GetRequiredService<IClientPayrollSource>());
        services.AddScoped<ISourceFingerprintReader>(p => IsCsv(settings)
            ? new CsvFingerprint(p.GetRequiredService<IClientPayrollSource>(), settings.Get("PAYROLL_PATH") ?? paths.Csv)
            : new SourceFingerprintReader(p.GetRequiredService<SourceScanner>()));
    }

    private static bool IsCsv(RuntimeConfiguration settings) => settings.Get("DATA_SOURCE") switch
    {
        "csv" => true,
        "lakehouse" or "flex" => false,
        _ => throw new InvalidOperationException("Unsupported DATA_SOURCE; use csv or lakehouse SQL."),
    };

    private static LookupResolver Lookups(IServiceProvider provider, RuntimeConfiguration settings, RuntimePaths paths) =>
        new(provider.GetRequiredService<ISourceLookupReader>(), LookupResolver.LoadSeed(Path.Combine(paths.Rules, "lookups")),
            new SourceLookupOptions(settings.Get("DATA_CLASSIFICATION") != "synthetic", settings.Get("PAY_CODE_POLICY"),
                settings.Get("FISCAL_RULES_POLICY") ?? "assume"), provider.GetRequiredService<TimeProvider>());

    private sealed class NoSourceFiscal : IFiscalRuleReader
    {
        public bool IsConfigured => false;
        public IReadOnlyList<FiscalRule>? Read(long accountId) => null;
    }
}

internal sealed class PersistenceLookups(ILookupReader reader) : ISourceLookupReader
{
    public IReadOnlyList<SourceLookupEntry> Entries(string lookup, long accountId) =>
        reader.Entries(lookup, accountId).Select(e => new SourceLookupEntry(e.Lookup, e.ClientId, e.KeyKind, e.Key,
            Value(e.ValueJson), e.Inferred, e.EffectiveFrom, e.EffectiveTo)).ToArray();

    private static string Value(string json)
    {
        using var doc = System.Text.Json.JsonDocument.Parse(json);
        return doc.RootElement.ValueKind == System.Text.Json.JsonValueKind.String ? doc.RootElement.GetString()! : doc.RootElement.GetRawText();
    }
}
