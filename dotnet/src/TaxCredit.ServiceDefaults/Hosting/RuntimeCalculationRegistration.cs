using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure;
using TaxCredit.Infrastructure.Persistence;
using TaxCredit.Infrastructure.Rules;
using TaxCredit.Infrastructure.Sources;

namespace TaxCredit.ServiceDefaults.Hosting;

internal static class RuntimeCalculationRegistration
{
    internal static void AddRuntimeCalculation(this IServiceCollection services, RuntimeConfiguration settings, RuntimePaths paths)
    {
        var options = new RulePackOptions
        {
            RulesDirectory = paths.Rules,
            IngestedConfigDirectory = Path.Combine(paths.Repository, "backend", "data", "rules_ingested")
        };
        services.AddRulePackSource(options);
        services.AddScoped<Application.Features.ClaimsArtifactsRules.Rules.IRuleFileMetadata, RuntimeRuleFileMetadata>();
        services.AddTaxCreditProgramWages(Path.Combine(paths.Repository, "backend", "data", "payroll.csv"),
            code => new RuleLibrary(new JsonRulePackSource(options)).LoadRegistry().Get(code)?.State
                ?? throw new InvalidOperationException("Unknown wage program."));
        services.RemoveAll<RuleLibrary>();
        services.AddScoped(p => new RuleLibrary(p.GetRequiredService<IRulePackSource>(),
            p.GetService<IIngestedOneZeroSource>(), p.GetRequiredService<IProgramWageSource>()));
        services.AddScoped(p => new ProgramDefaults(p.GetRequiredService<RuleLibrary>(),
            id => p.GetRequiredService<Application.Ports.Sources.ISourceCatalogue>().PayrollScope(id ?? 1001).States));
        services.AddScoped<FiscalSource>();
        services.AddScoped<ClientRunResolver>();
        services.AddScoped<RunFingerprint>();
        services.AddScoped<IGoldWriter, ObservedGoldWriter>();
        services.AddSingleton<RunIdentityScope>();
        services.AddScoped<RunItemExecution>();
        services.AddSingleton(new DesignationRegistry([], [
            new SourceDesignation(2001, "GA_GA-013", [
                Designation(2020, "T1"), Designation(2021, "T1 B40"), Designation(2022, "T1")])],
            [Designation(2020, "T1")], () => settings.Get("DATA_CLASSIFICATION") == "synthetic"));
        services.AddScoped(p =>
        {
            var clock = p.GetRequiredService<IClock>();
            var ids = p.GetRequiredService<IIdSource>();
            return new ClientCalculationConfig(settings.Get("GIT_COMMIT") ?? (settings.Get("TCC_CONTRACT_HOOKS") == "1"
                    ? "0000000000000000000000000000000000c0ffee" : "working-tree"),
                AssumptionFiles.Read(Path.Combine(paths.Rules, "methodology")), GoldWriter.Section9QueryCount,
                () => DateOnly.FromDateTime(clock.UtcNow.UtcDateTime), () => Instant(clock),
                () => p.GetRequiredService<RunIdentityScope>().Current ?? ids.NewId().ToString("N"));
        });
        services.AddScoped(p => new ClientAssessment(p.GetRequiredService<RuleLibrary>(), p.GetRequiredService<FiscalSource>(),
            p.GetRequiredService<ClientCalculationConfig>().Today, p.GetRequiredService<ClientCalculationConfig>().UtcNow,
            () => p.GetRequiredService<IIdSource>().NewId().ToString()));
        services.AddScoped<ClientCalculationParts>();
        services.AddScoped<ClientCalculation>();
        services.AddScoped<Application.Features.ReadsCalc.Portfolio.IPortfolioReferenceData, PortfolioReferenceData>();
    }

    internal static PyDateTime Instant(IClock clock) => PyDateTime.FromIsoFormat(clock.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'+00:00'",
        System.Globalization.CultureInfo.InvariantCulture));

    private static PyDict Designation(long year, string name) =>
        new PyDict().Add("year", year).Add("tier", 1L).Add("designation", name).Add("min_new_jobs", 2L);
}
