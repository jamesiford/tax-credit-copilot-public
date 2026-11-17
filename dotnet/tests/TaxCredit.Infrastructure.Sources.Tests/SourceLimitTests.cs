using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class SourceLimitTests
{
    private sealed class Settings(Dictionary<string, string?> values) : IRuntimeConfiguration
    {
        public string? Get(string name) => values.GetValueOrDefault(name);
    }

    private static SourceLimits Parse(params (string Name, string? Value)[] values) =>
        SourceLimits.From(new Settings(values.ToDictionary(v => v.Name, v => v.Value)));

    [Fact]
    public void UnsetAndBlankSettingsKeepTheDefaultsAtOneMillionTwentyFiveAndFiveMillion()
    {
        Assert.Equal(new SourceLimits(1_000_000, 25, 5_000_000), Parse());
        Assert.Equal(SourceLimits.Default, Parse((SourceLimitSettings.MaxAccountRows, "  "), (SourceLimitSettings.PortfolioMaxRows, "")));
    }

    [Fact]
    public void ValidOverridesAreHonoured()
    {
        var limits = Parse((SourceLimitSettings.MaxAccountRows, " 2500000 "), (SourceLimitSettings.PortfolioMaxAccounts, "3"),
            (SourceLimitSettings.PortfolioMaxRows, "1000"));
        Assert.Equal(new SourceLimits(2_500_000, 3, 1000), limits);
        Assert.Equal(1000, Parse((SourceLimitSettings.MaxAccountRows, "1000")).MaxAccountRows);
    }

    [Theory]
    [InlineData("SOURCE_MAX_ACCOUNT_ROWS", "999")]
    [InlineData("SOURCE_MAX_ACCOUNT_ROWS", "0")]
    [InlineData("SOURCE_MAX_ACCOUNT_ROWS", "-5000")]
    [InlineData("SOURCE_MAX_ACCOUNT_ROWS", "1e6")]
    [InlineData("SOURCE_MAX_ACCOUNT_ROWS", "lots")]
    [InlineData("SOURCE_MAX_ACCOUNT_ROWS", "1000000.5")]
    [InlineData("SOURCE_PORTFOLIO_MAX_ACCOUNTS", "0")]
    [InlineData("SOURCE_PORTFOLIO_MAX_ACCOUNTS", "99999999999")]
    [InlineData("SOURCE_PORTFOLIO_MAX_ROWS", "10")]
    public void AnInvalidValueIsAStartupErrorThatNamesTheSetting(string name, string value)
    {
        var error = Assert.Throws<InvalidOperationException>(() => Parse((name, value)));
        Assert.StartsWith(name + " must be", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void TheRefusalNamesTheSettingAndTheLimit()
    {
        var refusal = new SourceTooLarge(1_000_000);
        Assert.Equal(1_000_000, refusal.Limit);
        Assert.Contains("SOURCE_MAX_ACCOUNT_ROWS", refusal.Remedy, StringComparison.Ordinal);
        Assert.Contains("1,000,000", refusal.Remedy, StringComparison.Ordinal);
        Assert.DoesNotContain("SOURCE_MAX_ACCOUNT_ROWS", new SourceTooLarge(5, bytes: true).Remedy, StringComparison.Ordinal);
    }

    [Fact]
    public void AReadStopsOneRowPastTheLimitInsteadOfMaterializingTheClient()
    {
        var tables = SourceTestData.MiniTables();
        var mapping = SourceMapping.Load();
        var payroll = mapping.Tables["Payroll"].Physical;
        var template = SourceTestData.Payroll(7, 1);
        var rows = Enumerable.Range(1, 5000).Select(i => (IReadOnlyDictionary<string, object?>)mapping.Tables["Payroll"].Fields
            .ToDictionary(f => f.Value.Column, f => f.Key == "payroll_id" ? (object?)(long)i : template.GetValueOrDefault(f.Key),
                StringComparer.Ordinal)).ToArray();
        tables[payroll] = rows;
        var (source, _, transport) = SourceTestData.Source(tables, limit: 1000);
        var refusal = Assert.Throws<SourceTooLarge>(() => source.LoadPayPeriods(7));
        Assert.Equal(1000, refusal.Limit);
        Assert.Equal(1001, transport.RowsSent - 4);
        Assert.Equal(transport.Queries.Count, transport.DisposedStreams);
    }

    [Fact]
    public void ABookOverTheAccountLimitIsRefusedBeforeAnyPayrollIsRead()
    {
        var (source, _, transport) = SourceTestData.Source(limits: new SourceLimits(1_000_000, 1, 5_000_000));
        var refusal = Assert.Throws<SourcePortfolioTooLarge>(() => source.LoadPortfolioPayPeriods());
        Assert.Equal(("accounts", 2L, 1L), (refusal.Measure, refusal.Observed, refusal.Limit));
        Assert.Contains("SOURCE_PORTFOLIO_MAX_ACCOUNTS", refusal.Remedy, StringComparison.Ordinal);
        Assert.Contains("Select fewer clients", refusal.Remedy, StringComparison.Ordinal);
        Assert.DoesNotContain(transport.Queries, q => q.Table == "Payroll");
    }

    [Fact]
    public void ARunningRowTotalOverTheLimitStopsBeforeThatAccountsPayrollIsRead()
    {
        var (source, _, transport) = SourceTestData.Source(limits: new SourceLimits(1_000_000, 25, 2));
        var refusal = Assert.Throws<SourcePortfolioTooLarge>(() => source.LoadPortfolioPayPeriods());
        Assert.Equal(("rows", 3L, 2L), (refusal.Measure, refusal.Observed, refusal.Limit));
        Assert.Contains("SOURCE_PORTFOLIO_MAX_ROWS", refusal.Remedy, StringComparison.Ordinal);
        var scans = transport.Queries.Where(q => q.Table == "Payroll" && q.Kind == "scan").ToArray();
        Assert.Equal(7L, Assert.Single(scans).Parameters[0]);
        Assert.Equal(2, transport.Queries.Count(q => q.Kind == "scope"));
    }

    [Fact]
    public void TheFirstAccountAloneOverTheRowLimitReadsNoPayrollAtAll()
    {
        var (source, _, transport) = SourceTestData.Source(limits: new SourceLimits(1_000_000, 25, 1));
        Assert.Throws<SourcePortfolioTooLarge>(() => source.LoadPortfolioPayPeriods());
        Assert.DoesNotContain(transport.Queries, q => q.Table == "Payroll" && q.Kind == "scan");
    }

    [Fact]
    public void ASmallBookLoadsExactlyAsItDidWithoutLimits()
    {
        var unlimited = SourceTestData.Source().Source.LoadPortfolioPayPeriods();
        var bounded = SourceTestData.Source(limits: new SourceLimits(1_000_000, 2, 3)).Source.LoadPortfolioPayPeriods();
        Assert.Equal(unlimited.Keys.Order(), bounded.Keys.Order());
        Assert.All(unlimited, pair => Assert.Equal(pair.Value.Count, bounded[pair.Key].Count));
        Assert.Equal(2, bounded.Count);
    }
}
