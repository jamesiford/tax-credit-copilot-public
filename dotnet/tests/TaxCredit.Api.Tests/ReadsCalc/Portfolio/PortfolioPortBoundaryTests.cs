using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Api.Tests.ReadsCalc.Portfolio;

public sealed class PortfolioPortBoundaryTests
{
    [Fact]
    public async Task Discovery_prices_each_program_of_one_state_and_trend_resolves_the_explicit_pack()
    {
        await using var original = await TestHost.Start(services: PortfolioTestData.Register);
        var source = original.App.Services.GetRequiredService<IRulePackSource>();
        await using var host = await TestHost.Start(services: services =>
        {
            PortfolioTestData.Register(services);
            services.AddSingleton<IRulePackSource>(new AdditionalProgram(source));
        });
        using var scope = host.App.Services.CreateScope();
        var tiles = scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>().BuildPortfolio(2025);
        Assert.Equal(66500L, tiles.Single(t => (string)t["code"]! == "GA_JTC")["annual_credit_usd"]);
        Assert.Equal(19000L, tiles.Single(t => (string)t["code"]! == "GA_READS_TEST")["annual_credit_usd"]);
        var trend = scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>().Execute(new("GA", ProgramCode: "GA_READS_TEST"));
        Assert.Equal("GA_READS_TEST", trend["program_code"]);
        Assert.Equal(new System.Numerics.BigInteger(23750), ((PyDict)trend["totals"]!)["annual_credit_usd"]);
    }

    [Fact]
    public async Task Strict_fiscal_failure_is_not_swallowed_as_a_declined_year()
    {
        await using var host = await TestHost.Start(services: services =>
        {
            PortfolioTestData.Register(services);
            services.AddSingleton<IFiscalRuleSource, MissingFiscalRules>();
        }, configuration: new Dictionary<string, string?> { ["FIXTURE_ACCOUNT_ID"] = "1001" });
        using var scope = host.App.Services.CreateScope();
        Assert.Throws<FiscalRulesMissing>(() => scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>()
            .Execute(new("GA", 1001)));
    }

    [Fact]
    public async Task Latest_year_ignores_a_thin_tail_and_empty_configured_data_uses_the_host_clock()
    {
        var rows = Enumerable.Repeat(PayRow.Of(new PyDict().Add("Pay_Date", "2024-12-15")), 4)
            .Append(PayRow.Of(new PyDict().Add("Pay_Date", "2025-01-03"))).ToList();
        var empty = false;
        await using var host = await TestHost.Start(services: services =>
        {
            PortfolioTestData.Register(services);
            services.AddSingleton<IPayrollSource>(new PortfolioPayroll(_ => empty ? [] : rows));
        });
        using var scope = host.App.Services.CreateScope();
        Assert.Equal(2024, scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>().LatestTaxYear());
        empty = true;
        Assert.Equal(scope.ServiceProvider.GetRequiredService<IClock>().UtcNow.Year - 1,
            scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>().LatestTaxYear());
    }

    private sealed class MissingFiscalRules : IFiscalRuleSource
    {
        public bool HoldsClientRules => true;
        public IReadOnlyList<FiscalRule>? RulesWithOverrides(long accountId) => throw new FiscalRulesMissing();
    }
}

internal sealed class AdditionalProgram(IRulePackSource source) : IRulePackSource
{
    public string RulesDirectory => source.RulesDirectory;
    public string RegistryFile => source.RegistryFile;
    public bool Exists(string relativePath) => source.Exists(Map(relativePath));
    public bool IsFile(string relativePath) => source.IsFile(Map(relativePath));
    public bool IsDirectory(string relativePath) => source.IsDirectory(Map(relativePath));
    public IReadOnlyList<string> ListJsonStems(string relativeFolder) => source.ListJsonStems(Map(relativeFolder));
    public long? RegistryStamp() => source.RegistryStamp();

    public string ReadText(string relativePath)
    {
        var text = source.ReadText(Map(relativePath));
        if (!relativePath.StartsWith("ga_reads_test", StringComparison.Ordinal))
        {
            return text;
        }
        var pack = JsonNode.Parse(text)!;
        pack["credit"]!["code"] = "GA_READS_TEST";
        pack["benefit"]!["amount_per_qualifying_job_usd"] = 1000;
        return pack.ToJsonString();
    }

    public string ReadRegistryText()
    {
        var manifest = JsonNode.Parse(source.ReadRegistryText())!;
        var entries = manifest["programs"]!.AsArray();
        var entry = entries.Single(p => p!["code"]!.GetValue<string>() == "GA_JTC")!.DeepClone();
        entry["code"] = "GA_READS_TEST";
        entry["pack_file"] = "ga_reads_test.json";
        entries.Add(entry);
        return manifest.ToJsonString();
    }

    private static string Map(string path) => path.Replace("ga_reads_test", "ga_jtc", StringComparison.Ordinal);
}
